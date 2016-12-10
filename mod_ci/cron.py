#!/usr/bin/python
import sys
from os import path

# Need to append server root path to ensure we can import the necessary files.
sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

# noinspection PyPep8
from mod_ci.controllers import start_ci_vm
# noinspection PyPep8
from run import config, log
# noinspection PyPep8
from database import create_session
# noinspection PyPep8
from github import GitHub

log.info('Running cron.py CI scheduler')
# Create session
db = create_session(config['DATABASE_URI'])
gh = GitHub(access_token=config['GITHUB_TOKEN'])
repository = gh.repos(config['GITHUB_OWNER'])(config['GITHUB_REPOSITORY'])
# Kick off start_ci_vm
start_ci_vm(db, repository)
