"""handles the mailing operations across the app."""

import traceback
from exceptions import FailedToSendMail
from typing import Dict

import requests
from requests.models import Response


class Mailer:
    """Send a mail through the Mailgun API."""

    auth = None
    api_url = None
    sender = None

    def __init__(self, domain: str, api_key: str, sender_name: str) -> None:
        """
        Initialize the Mailer class.

        :param domain: Domain name of the sender
        :type domain: str
        :param api_key: API key of the Mailgun API
        :type api_key: str
        :param sender_name: name of the person sending the email
        :type sender_name: str
        """
        self.auth = ("api", api_key)
        self.api_url = f"https://api.mailgun.net/v3/{domain}"
        self.sender = f"{sender_name} <noreply@{domain}>"

    def send_simple_message(self, data: Dict) -> Response:
        """
        Send a message.

        :param data: A dict consisting of the data for email
        :type data: dict
        :return: A Response object
        :rtype: requests.Response
        """
        data['from'] = self.sender
        try:
            return requests.post(f"{self.api_url}/messages", auth=self.auth, data=data)
        except (requests.HTTPError, requests.ConnectionError):
            traceback.print_exc()
            raise FailedToSendMail
