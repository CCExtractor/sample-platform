"""Celery application factory and configuration for Sample Platform."""

import os

from celery import Celery
from celery.schedules import crontab

# Load configuration - use empty dict for testing when config.py doesn't exist
try:
    from config_parser import parse_config
    config = parse_config('config')
except Exception:
    # In test environment, config.py may not exist
    config = {}


def make_celery(app=None):
    """
    Create a Celery application configured for the Sample Platform.

    :param app: Optional Flask application for context binding
    :return: Configured Celery application
    """
    celery_app = Celery(
        'sample_platform',
        broker=config.get('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
        backend=config.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0'),
        include=['mod_ci.tasks']
    )

    # Apply configuration from config.py
    celery_app.conf.update(
        task_serializer=config.get('CELERY_TASK_SERIALIZER', 'json'),
        result_serializer=config.get('CELERY_RESULT_SERIALIZER', 'json'),
        accept_content=config.get('CELERY_ACCEPT_CONTENT', ['json']),
        timezone=config.get('CELERY_TIMEZONE', 'UTC'),
        enable_utc=config.get('CELERY_ENABLE_UTC', True),
        task_acks_late=config.get('CELERY_TASK_ACKS_LATE', True),
        worker_prefetch_multiplier=config.get('CELERY_WORKER_PREFETCH_MULTIPLIER', 1),
        task_reject_on_worker_lost=config.get('CELERY_TASK_REJECT_ON_WORKER_LOST', True),
        task_soft_time_limit=config.get('CELERY_TASK_SOFT_TIME_LIMIT', 3600),
        task_time_limit=config.get('CELERY_TASK_TIME_LIMIT', 3900),
    )

    # Beat schedule for periodic tasks
    celery_app.conf.beat_schedule = {
        'check-expired-instances-every-5-minutes': {
            'task': 'mod_ci.tasks.check_expired_instances_task',
            'schedule': crontab(minute='*/5'),
            'options': {'queue': 'maintenance'}
        },
        'process-pending-tests-every-minute': {
            'task': 'mod_ci.tasks.process_pending_tests_task',
            'schedule': crontab(minute='*'),
            'options': {'queue': 'default'}
        },
    }

    # Queue routing
    celery_app.conf.task_routes = {
        'mod_ci.tasks.start_test_task': {'queue': 'test_execution'},
        'mod_ci.tasks.check_expired_instances_task': {'queue': 'maintenance'},
        'mod_ci.tasks.process_pending_tests_task': {'queue': 'default'},
    }

    # If Flask app is provided, bind tasks to its context
    if app is not None:
        class ContextTask(celery_app.Task):
            """Task base class that maintains Flask application context."""

            def __call__(self, *args, **kwargs):
                with app.app_context():
                    return self.run(*args, **kwargs)

        celery_app.Task = ContextTask

    return celery_app


# Create the default celery instance (used by worker when started standalone)
celery = make_celery()
