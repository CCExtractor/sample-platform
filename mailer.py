import requests


class Mailer:
    """
    Sends a mail through the Mailgun API
    """

    auth = None
    api_url = None
    sender = None

    def __init__(self, domain, api_key, sender_name):
        """
        Constructor for the Mailer class

        :param domain: Domain name of the sender
        :type domain: str
        :param api_key: API key of the Mailgun API
        :type api_key: str
        :param sender_name: name of the person sending the email
        :type sender_name: str
        """
        self.auth = ("api", api_key)
        self.api_url = "https://api.mailgun.net/v3/%s" % domain
        self.sender = "%s <noreply@%s>" % (sender_name, domain)

    def send_simple_message(self, data):
        """
        Sends a message 

        :param data: A dict consisting of the data for email
        :type data: dict
        :return: A Response object
        :rtype: requests.Response
        """
        data['from'] = self.sender
        return requests.post("%s/messages" % self.api_url, auth=self.auth,
                             data=data)
