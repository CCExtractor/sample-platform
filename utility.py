"""provide common utility attributes such as root path."""

import datetime
from os import path

import werkzeug
from flask import redirect


def serve_file_download(file_name, file_folder, file_sub_folder='') -> werkzeug.wrappers.response.Response:
    """
    Serve file download by redirecting using Signed Download URLs.

    :param file_name: name of the file
    :type file_name: str
    :param file_folder: name of the folder
    :type file_folder: str
    :param file_sub_folder: sub folder of the original folder
    :type file_sub_folder: str
    :return: response, the file download
    :rtype: werkzeug.wrappers.response.Responsee
    """
    from run import config, storage_client_bucket

    file_path = path.join(file_folder, file_sub_folder, file_name)
    blob = storage_client_bucket.blob(file_path)
    blob.content_disposition = f'attachment; filename="{file_name}"'
    blob.patch()
    url = blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(minutes=config.get('GCS_SIGNED_URL_EXPIRY_LIMIT', '')),
        method="GET",
    )
    return redirect(url)
