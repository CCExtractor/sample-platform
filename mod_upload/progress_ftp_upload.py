#!/usr/bin/python
import sys
from os import path

file_path = str(sys.argv[1])
# Need to append server root path to ensure we can import the necessary files.
sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))


from mod_upload.controllers import upload_ftp
from database import create_session
from run import config, log
from mod_upload.models import QueuedSample
from mod_sample.models import Sample

if __name__ == '__main__':
    db = create_session(config['DATABASE_URI'])
    log.info("In the progree ftp upload")
    upload_ftp(db,file_path)
