#!/usr/bin/python
"""Maintain logic to show upload progress."""

import sys
from os import path

# Need to append server root path to ensure we can import the necessary files.
sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))


def process(database, file_to_process):
    """
    Call ftp upload method.

    :param database: database
    :type database: database cursor
    :param file_to_process: path of file to upload
    :type file_to_process: str
    """
    from mod_upload.controllers import upload_ftp
    from run import log
    log.debug("Calling the FTP upload method from the controller!")
    upload_ftp(database, file_to_process)


if __name__ == '__main__':
    from database import create_session
    from run import config, log

    db = create_session(config['DATABASE_URI'])
    file_path = str(sys.argv[1])
    process(db, file_path)
