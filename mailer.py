"""handles the mailing operations across the app."""

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
        self.api_url = "https://api.mailgun.net/v3/{domain}".format(domain=domain)
        self.sender = "{sender} <noreply@{domain}>".format(sender=sender_name, domain=domain)

    def send_simple_message(self, data: Dict) -> Response:
        """
        Send a message.

        :param data: A dict consisting of the data for email
        :type data: dict
        :return: A Response object
        :rtype: requests.Response
        """
        data['from'] = self.sender
        return requests.post("{url}/messages".format(url=self.api_url), auth=self.auth, data=data)
