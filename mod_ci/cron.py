#!/usr/bin/python
import sys
from os import path

# Need to append server root path to ensure we can import the necessary files.
sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))


def cron():
    from mod_ci.controllers import start_all_platforms
    from run import config, log
    from database import create_session
    from github import GitHub

    log.info('Run the cron for kicking off CI platform(s).')
    # Create session
    db = create_session(config['DATABASE_URI'])
    gh = GitHub(access_token=config['GITHUB_TOKEN'])
    repository = gh.repos(config['GITHUB_OWNER'])(config['GITHUB_REPOSITORY'])

    start_platform(db, repository)

cron()
