#!/usr/bin/python
import os
import hashlib
import sys
import logging
import MySQLdb
logger = logging.getLogger(sys.argv[1])
# create File Handler and set level to debug
ch = logging.FileHandler('/home/ftp.log')
formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)
logger.setLevel(logging.DEBUG)

if __name__ == '__main__':
    logger.info(str(sys.argv[1]) + ' Uploaded')
    temp_path = str(sys.argv[1])
    hash_sha256 = hashlib.sha256()
    logger.debug('Checking hash value')
    with open(temp_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    file_hash = hash_sha256.hexdigest()
    db = MySQLdb.connect(host="localhost",    # your host, usually localhost
                         user="sample_platform",         # your username
                         passwd="",  # your password
                         db="sample_platform")        # name of the data base
    queued_sample = db.cursor()
    logger.debug('Checking queued_sample exist or not with same hash ')
    queued_sample.execute(
        ("select * from upload_queue where sha = '{hash}' LIMIT 1"
         ).format(hash=file_hash))
    sample = db.cursor()
    sample.execute(
        ("select * from sample where sha = '{hash}' LIMIT 1"
         ).format(hash=file_hash))
    logger.debug('Checking existence in the database')
    if sample.rowcount != 0 or queued_sample.rowcount != 0:
        # Remove existing file and notice user
        os.remove(temp_path)
        logger.error(
            temp_path + ' Sample with same hash already uploaded or queued')
    else:
        logger.debug('Adding to the database ' + str(sys.argv[1]))
        split_arr = temp_path.split('/')
        filename = split_arr[-1]
        user_id = split_arr[-2]
        filename, file_extension = os.path.splitext(filename)
        # final_path=/path/to/QueuedFiles/filename
        final_path = os.path.join(
            '/repository/', 'QueuedFiles',
            filename)
        logger.debug('Changing the path to ' + final_path)
        # Move to queued folder
        os.rename(temp_path, final_path)
        queued_sample = db.cursor()
        queued_sample.execute(('INSERT INTO upload_queue '
                               '(sha,extension,original_name,user_id)'
                               'VALUES ("{sha}","{extension}",'
                               '"{name}",{userid})').format(
            sha=file_hash, extension=file_extension,
            name=filename, userid=int(user_id)))
        db.commit()
