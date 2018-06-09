import unittest

from mock import mock

from mailer import Mailer


class TestMailer(unittest.TestCase):
    def test_that_init_works_correctly(self):
        domain = 'domain'
        api_key = 'APIKEY'
        sender_name = 'foo'
        auth = ("api", api_key)
        api_url = "https://api.mailgun.net/v3/%s" % domain
        sender = "%s <noreply@%s>" % (sender_name, domain)

        actual = Mailer(domain, api_key, sender_name)

        self.assertEqual(actual.api_url, api_url)
        self.assertEqual(actual.auth, auth)
        self.assertEqual(actual.sender, sender)

    def test_that_send_simple_message_creates_the_appropriate_request(self):
        domain = 'domain'
        api_key = 'APIKEY'
        sender_name = 'foo'

        mailer = Mailer(domain, api_key, sender_name)

        with mock.patch('requests.post') as mock_post:
            data = {'subject': 'foo'}
            mailer.send_simple_message(data)
            expected_data = data.copy()
            expected_data['from'] = mailer.sender

            mock_post.assert_called_once_with("%s/messages" % mailer.api_url,
                                              auth=mailer.auth,
                                              data=expected_data)
