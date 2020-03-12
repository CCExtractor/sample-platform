"""provide common utility attributes such as root path."""

from os import path
from typing import Any

from flask import make_response

ROOT_DIR = path.dirname(path.abspath(__file__))


def serve_file_download(file_name, file_folder, x_accel_folder,
                        file_sub_folder='', content_type='application/octet-stream') -> Any:
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

    file_path = path.join(config.get('SAMPLE_REPOSITORY', ''), file_folder, file_sub_folder, file_name)
    response = make_response()
    response.headers['Content-Description'] = 'File Transfer'
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Content-Type'] = content_type
    response.headers['Content-Disposition'] = f'attachment; filename={file_name}'
    response.headers['Content-Length'] = path.getsize(file_path)
    response.headers['X-Accel-Redirect'] = '/' + path.join(x_accel_folder, file_sub_folder, file_name)

    return response
