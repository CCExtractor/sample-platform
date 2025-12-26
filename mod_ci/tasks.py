"""Celery tasks for CI platform operations."""

from celery.exceptions import SoftTimeLimitExceeded
from celery.utils.log import get_task_logger
from github import Auth, Github, GithubException

from celery_app import celery

logger = get_task_logger(__name__)


@celery.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(GithubException,),
    retry_backoff=True,
    retry_backoff_max=300,
    acks_late=True
)
def start_test_task(self, test_id: int, bot_token: str):
    """
    Execute a single test by creating a GCP VM instance.

    This task wraps the existing start_test() function with Celery's
    retry mechanisms and proper error handling.

    :param test_id: The ID of the Test to execute
    :param bot_token: GitHub bot token for artifact download
    :return: Dict with status and message
    """
    # Import inside task to avoid circular imports and ensure fresh Flask context
    from database import create_session
    from mod_ci.controllers import (get_compute_service_object,
                                    mark_test_failed, start_test)
    from mod_ci.models import GcpInstance
    from mod_test.models import Test
    from run import app, config

    with app.app_context():
        db = create_session(config['DATABASE_URI'])

        try:
            # Fetch the test
            test = Test.query.get(test_id)
            if test is None:
                logger.error(f"Test {test_id} not found")
                return {'status': 'error', 'message': 'Test not found'}

            # Check if test is already finished
            if test.finished:
                logger.info(f"Test {test_id} already finished, skipping")
                return {'status': 'skipped', 'message': 'Test already finished'}

            # Check if test already has a GCP instance (prevent duplicates)
            existing_instance = GcpInstance.query.filter(
                GcpInstance.test_id == test_id
            ).first()
            if existing_instance is not None:
                logger.info(f"Test {test_id} already has GCP instance, skipping")
                return {'status': 'skipped', 'message': 'Test already has instance'}

            # Get GitHub repository
            gh = Github(auth=Auth.Token(bot_token))
            repository = gh.get_repo(
                f"{config['GITHUB_OWNER']}/{config['GITHUB_REPOSITORY']}"
            )

            # Execute the test
            compute = get_compute_service_object()
            start_test(compute, app, db, repository, test, bot_token)

            logger.info(f"Test {test_id} started successfully")
            return {'status': 'success', 'test_id': test_id}

        except SoftTimeLimitExceeded:
            logger.error(f"Test {test_id} exceeded time limit")
            try:
                test = Test.query.get(test_id)
                if test and not test.finished:
                    gh = Github(auth=Auth.Token(bot_token))
                    repository = gh.get_repo(
                        f"{config['GITHUB_OWNER']}/{config['GITHUB_REPOSITORY']}"
                    )
                    mark_test_failed(db, test, repository, "Task timed out")
            except Exception as mark_error:
                logger.error(f"Failed to mark test {test_id} as failed: {mark_error}")
            raise

        except Exception as e:
            logger.exception(f"Error starting test {test_id}: {e}")
            # Retry on transient failures
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e)
            # Final failure - mark test as failed
            try:
                test = Test.query.get(test_id)
                if test and not test.finished:
                    gh = Github(auth=Auth.Token(bot_token))
                    repository = gh.get_repo(
                        f"{config['GITHUB_OWNER']}/{config['GITHUB_REPOSITORY']}"
                    )
                    mark_test_failed(db, test, repository, f"Task failed: {str(e)[:100]}")
            except Exception as mark_error:
                logger.error(f"Failed to mark test {test_id} as failed: {mark_error}")
            raise

        finally:
            db.remove()


@celery.task(bind=True, acks_late=True)
def check_expired_instances_task(self):
    """
    Periodic task to clean up expired GCP instances.

    This wraps delete_expired_instances() for Celery scheduling.

    :return: Dict with status and message
    """
    from github import Auth, Github

    from database import create_session
    from mod_ci.controllers import (delete_expired_instances,
                                    get_compute_service_object)
    from run import app, config

    with app.app_context():
        db = create_session(config['DATABASE_URI'])

        try:
            vm_max_runtime = config.get('GCP_INSTANCE_MAX_RUNTIME', 120)
            zone = config.get('ZONE', '')
            project = config.get('PROJECT_NAME', '')

            if not zone or not project:
                logger.error('GCP zone or project not configured')
                return {'status': 'error', 'message': 'GCP not configured'}

            # Get GitHub repository
            github_token = config.get('GITHUB_TOKEN', '')
            if not github_token:
                logger.error('GitHub token not configured')
                return {'status': 'error', 'message': 'GitHub token missing'}

            gh = Github(auth=Auth.Token(github_token))
            repository = gh.get_repo(
                f"{config['GITHUB_OWNER']}/{config['GITHUB_REPOSITORY']}"
            )

            compute = get_compute_service_object()
            delete_expired_instances(
                compute, vm_max_runtime, project, zone, db, repository
            )

            logger.info('Expired instances check completed')
            return {'status': 'success'}

        except Exception as e:
            logger.exception(f"Error checking expired instances: {e}")
            return {'status': 'error', 'message': str(e)}

        finally:
            db.remove()


@celery.task(bind=True, acks_late=True)
def process_pending_tests_task(self):
    """
    Periodic task to find and queue pending tests for execution.

    This replaces the cron-based approach by finding pending tests
    and dispatching individual start_test_task for each.

    :return: Dict with status and count of queued tests
    """
    from database import create_session
    from mod_ci.models import GcpInstance, MaintenanceMode
    from mod_test.models import Test, TestPlatform, TestProgress, TestStatus
    from run import app, config

    with app.app_context():
        db = create_session(config['DATABASE_URI'])

        try:
            github_token = config.get('GITHUB_TOKEN', '')
            if not github_token:
                logger.error('GitHub token not configured')
                return {'status': 'error', 'message': 'GitHub token missing'}

            bot_token = github_token
            queued_count = 0

            # Find pending tests for each platform
            for platform in [TestPlatform.linux, TestPlatform.windows]:
                # Check maintenance mode
                maintenance_mode = MaintenanceMode.query.filter(
                    MaintenanceMode.platform == platform
                ).first()
                if maintenance_mode is not None and maintenance_mode.disabled:
                    logger.debug(f'[{platform.value}] In maintenance mode, skipping')
                    continue

                # Get tests with progress (finished or in progress)
                finished_tests = db.query(TestProgress.test_id).filter(
                    TestProgress.status.in_([TestStatus.canceled, TestStatus.completed])
                )

                # Get tests with GCP instances (currently running)
                running_tests = db.query(GcpInstance.test_id)

                # Find pending tests (limit to 5 per platform per run)
                pending_tests = Test.query.filter(
                    Test.id.notin_(finished_tests),
                    Test.id.notin_(running_tests),
                    Test.platform == platform
                ).order_by(Test.id.asc()).limit(5).all()

                for test in pending_tests:
                    # Queue each test as a separate task
                    start_test_task.apply_async(
                        args=[test.id, bot_token],
                        queue='test_execution',
                        countdown=1  # Small delay between tasks
                    )
                    queued_count += 1
                    logger.info(f'Queued test {test.id} for {platform.value}')

            return {'status': 'success', 'queued_count': queued_count}

        except Exception as e:
            logger.exception(f"Error processing pending tests: {e}")
            return {'status': 'error', 'message': str(e)}

        finally:
            db.remove()
