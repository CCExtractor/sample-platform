import requests


class Mailer:
    auth = None
    api_url = None
    sender = None

    def __init__(self, domain, api_key, sender_name):
        self.auth = ("api", api_key)
        self.api_url = "https://api.mailgun.net/v3/%s" % domain
        self.sender = "%s <noreply@%s>" % (sender_name, domain)

    def send_simple_message(self, data):
        data['from'] = self.sender
        return requests.post("%s/messages" % self.api_url, auth=self.auth,
                             data=data)
