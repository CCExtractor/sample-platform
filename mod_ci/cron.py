#!/usr/bin/python3
"""handle cron logic for CI platform."""

import fcntl
import sys
import tempfile
from os import path

# Need to append server root path to ensure we can import the necessary files.
sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

LOCK_FILE = path.join(tempfile.gettempdir(), 'sample-platform-cron.lock')


def cron(testing=False):
    """Script to run from cron for Sampleplatform."""
    from flask import current_app
    from github import Auth, Github

    from database import create_session
    from mod_ci.controllers import TestPlatform, gcp_instance, start_platforms
    from run import config, log

    # Cron starts a run every 10 minutes, but a run working through a backlog can take longer.
    # Overlapping runs ran the server out of memory, so only one runs at a time. The lock is
    # released when the process exits, even if it is killed.
    lock = open(LOCK_FILE, 'w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log.warning('Previous cron run is still in progress, skipping this one.')
        lock.close()
        return

    log.info('Run the cron for kicking off CI platform(s).')
    github_token = config['GITHUB_TOKEN']
    if not github_token:
        log.error('GITHUB_TOKEN not configured, cannot run CI cron')
        return
    gh = Github(auth=Auth.Token(github_token))
    repository = gh.get_repo(f"{config['GITHUB_OWNER']}/{config['GITHUB_REPOSITORY']}")

    if testing is True:
        # Create a database session
        db = create_session(config['DATABASE_URI'])
        gcp_instance(current_app._get_current_object(), db, TestPlatform.linux, repository, None)
    else:
        start_platforms(repository)


cron()
