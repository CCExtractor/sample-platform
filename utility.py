"""provide common utility attributes such as root path."""

import hashlib
import hmac
from datetime import datetime, timedelta
from functools import wraps
from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network
from os import path
from typing import Callable, List, Union

import requests
import werkzeug
from flask import abort, g, redirect, request

ROOT_DIR = path.dirname(path.abspath(__file__))


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
        expiration=timedelta(minutes=config.get('GCS_SIGNED_URL_EXPIRY_LIMIT', '')),
        method="GET",
    )
    return redirect(url)


def request_from_github(abort_code: int = 418) -> Callable:
    """Provide decorator to handle request from GitHub on the web hook."""
    def decorator(f):
        """Decorate the function to check if a request is a GitHub hook request."""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if request.method != 'POST':
                g.log.info(f"Request type {request.method} detected")

            request_ip = ip_address(f"{request.remote_addr}")
            if not is_github_web_hook_ip(request_ip):
                g.log.warning(f"Unauthorized attempt by IP {request_ip}")
                abort(abort_code)

            for header in ['X-GitHub-Event', 'X-GitHub-Delivery', 'X-Hub-Signature', 'User-Agent']:
                if header not in request.headers:
                    g.log.critical(f"{header} not in headers!")
                    abort(abort_code)

            ua = request.headers.get('User-Agent')
            if not ua.startswith('GitHub-Hookshot/'):
                g.log.critical("User-Agent does not begin with GitHub-Hookshot/!")
                abort(abort_code)

            if not request.is_json:
                g.log.critical("Request is not JSON!")
                abort(abort_code)

            return f(*args, **kwargs)
        return decorated_function
    return decorator


cached_web_hook_blocks: List[str] = []


def cache_has_expired() -> bool:
    """
    Check if the cache expired.

    :return: True if the cache was last updated more than one hour ago.
    :rtype: bool
    """
    cached_load_time = datetime(1970, 1, 1)
    return cached_load_time + timedelta(hours=1) < datetime.now()


def is_github_web_hook_ip(request_ip: Union[IPv4Address, IPv6Address]) -> bool:
    """
    Check if the given IP address is matching one provided by the API of GitHub.

    :param request_ip: The IP address the request came from.
    :type request_ip: IPAddress
    :return: True if the IP address is a valid GitHub Web Hook requester.
    :rtype: bool
    """
    for block in get_cached_web_hook_blocks():
        if request_ip in ip_network(block):
            return True
    return False


def get_cached_web_hook_blocks() -> List[str]:
    """
    Fetch the cached web hook blocks.

    :return: A list of ip blocks.
    :rtype: List[str]
    """
    global cached_web_hook_blocks
    from run import config

    if len(cached_web_hook_blocks) == 0 or cache_has_expired():
        client_id = config.get('GITHUB_CLIENT_ID', '')
        client_secret = config.get('GITHUB_CLIENT_KEY', '')
        meta_json = requests.get(
            f'https://api.github.com/meta', auth=(client_id, client_secret)).json()
        try:
            cached_web_hook_blocks = meta_json['hooks']
        except KeyError:
            g.log.critical(f"Failed to retrieve hook IP's from GitHub! API returned {meta_json}")

    return cached_web_hook_blocks


def is_valid_signature(x_hub_signature, data, private_key):
    """
    Re-check if the GitHub hook request got valid signature.

    :param x_hub_signature: Signature to check
    :type x_hub_signature: str
    :param data: Signature's data
    :type data: bytearray
    :param private_key: Signature's token
    :type private_key: str
    """
    hash_algorithm, github_signature = x_hub_signature.split('=', 1)
    algorithm = hashlib.__dict__.get(hash_algorithm)
    encoded_key = bytes(private_key, 'latin-1')
    mac = hmac.new(encoded_key, msg=data, digestmod=algorithm)
    return hmac.compare_digest(mac.hexdigest(), github_signature)
