#!/usr/bin/python
"""handle cron logic for CI platform."""

import sys
from os import path

from flask import current_app

# Need to append server root path to ensure we can import the necessary files.
sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))


def cron(testing=False):
    """Script to run from cron for Sampleplatform."""
    from mod_ci.controllers import start_platforms, kvm_processor, TestPlatform
    from run import config, log
    from database import create_session
    from github import GitHub

    log.info('Run the cron for kicking off CI platform(s).')
    # Create session
    db = create_session(config['DATABASE_URI'])
    gh = GitHub(access_token=config['GITHUB_TOKEN'])
    repository = gh.repos(config['GITHUB_OWNER'])(config['GITHUB_REPOSITORY'])

    if testing is True:
        kvm_processor(current_app._get_current_object(), db, config.get('KVM_LINUX_NAME', ''), TestPlatform.linux,
                      repository, None)
    else:
        start_platforms(db, repository)


cron()
