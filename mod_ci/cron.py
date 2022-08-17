#!/usr/bin/python
"""handle cron logic for CI platform."""

import sys
from os import path

# Need to append server root path to ensure we can import the necessary files.
sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))


def cron(testing=False):
    """Script to run from cron for Sampleplatform."""
    from flask import current_app
    from github import GitHub

    from database import create_session
    from mod_ci.controllers import TestPlatform, gcp_instance, start_platforms
    from run import config, log

    log.info('Run the cron for kicking off CI platform(s).')
    # Create session
    db = create_session(config['DATABASE_URI'])
    gh = GitHub(access_token=config['GITHUB_TOKEN'])
    repository = gh.repos(config['GITHUB_OWNER'])(config['GITHUB_REPOSITORY'])

    if testing is True:
        gcp_instance(db, TestPlatform.linux, None)
    else:
        start_platforms(db, repository)


cron()
