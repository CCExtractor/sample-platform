#!/usr/bin/python
"""handle cron logic for CI platform."""

import sys
from os import path

# Need to append server root path to ensure we can import the necessary files.
sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))


def cron(testing=False):
    """Script to run from cron for Sampleplatform."""
    from flask import current_app
    from github import Auth, Github

    from database import create_session
    from mod_ci.controllers import TestPlatform, gcp_instance, start_platforms
    from run import config, log

    log.info('Run the cron for kicking off CI platform(s).')
    gh = Github(auth=Auth.Token(config['GITHUB_TOKEN']))
    repository = gh.get_repo(f"{config['GITHUB_OWNER']}/{config['GITHUB_REPOSITORY']}")

    if testing is True:
        # Create a database session
        db = create_session(config['DATABASE_URI'])
        gcp_instance(current_app._get_current_object(), db, TestPlatform.linux, repository, None)
    else:
        start_platforms(repository)


cron()
