"""provide common utility attributes such as root path."""

import datetime
from os import path

import werkzeug
from flask import redirect
from google.cloud import storage


def serve_file_download(file_name, file_folder, x_accel_folder,
                        file_sub_folder='', content_type='application/octet-stream') -> werkzeug.wrappers.response.Response:
    """
    Endpoint to serve file download.

    :param file_name: name of the file
    :type file_name: str
    :param file_folder: name of the folder
    :type file_folder: str
    :param x_accel_folder: location of the x-accel folder
    :type x_accel_folder: str
    :param file_sub_folder: sub folder of both the x-accel folder and the original folder
    :type file_sub_folder: str
    :param content_type: content type of the file, defaults to 'application/octet-stream'
    :type content_type: str, optional
    :return: response, the file download
    :rtype: Flask response
    """
    from run import config

    sa_file = path.join(config.get('INSTALL_FOLDER', ''), config.get('SERVICE_ACCOUNT_FILE', ''))
    file_path = path.join(file_folder, file_sub_folder, file_name)
    storage_client = storage.Client.from_service_account_json(sa_file)
    bucket = storage_client.bucket(config.get('GCS_BUCKET_NAME', ''))
    blob = bucket.blob(file_path)
    blob.content_disposition = f'attachment; filename="{file_name}"'
    blob.patch()
    url = blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(minutes=config.get('GCS_SIGNED_URL_EXPIRY_LIMIT', '')),
        method="GET",
    )
    return redirect(url)
