"""provide common utility attributes such as root path."""

from os import path
from typing import Any

from flask import make_response

ROOT_DIR = path.dirname(path.abspath(__file__))


def serve_file_download(file_name, file_folder, xaccel_folder,
                        subfolder='', content_type='application/octet-stream') -> Any:
    """
    Endpoint to serve file download.

    :param file_name: name of the file
    :type file_name: str
    :param content_type: content type of the file, defaults to 'application/octet-stream'
    :type content_type: str, optional
    :return: response, the file download
    :rtype: Flask response
    """
    from run import config

    file_path = path.join(config.get('SAMPLE_REPOSITORY', ''), file_folder, subfolder, file_name)
    response = make_response()
    response.headers['Content-Description'] = 'File Transfer'
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Content-Type'] = content_type
    response.headers['Content-Disposition'] = 'attachment; filename={name}'.format(name=file_name)
    response.headers['Content-Length'] = path.getsize(file_path)
    response.headers['X-Accel-Redirect'] = '/' + path.join(xaccel_folder, subfolder, file_name)

    return response
