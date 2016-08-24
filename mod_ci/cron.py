#!/usr/bin/python

from mod_ci.controllers import start_ci_vm
from run import config, log
from database import create_session

log.info('Running cron.py CI scheduler')
# Create session
db = create_session(config['DATABASE_URI'])
# Kick off start_ci_vm
start_ci_vm(db)
