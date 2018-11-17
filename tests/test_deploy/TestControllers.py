from tests.base import BaseTestCase
import json

class TestControllers(BaseTestCase):

    def test_root(self):
        """
        Test the Root of mod_deploy
        """
        response = self.app.test_client().get('/deploy')
        self.assertEqual(response.status_code, 200)
        self.assertIn("OK", str(response.data))

    def test_headers_ping(self):
        """
        Test The View by sending a ping request
        """
        response = self.app.test_client().post('/deploy',
                headers={'X-GitHub-Event': 'ping'}
            )

        self.assertEqual(response.status_code, 418)
        self.assertIn("I\\\'m a teapot", str(response.data))

    def test_headers_invalid_event(self):
        """
        Test The View by sending an invalid event
        """
        response = self.app.test_client().post('/deploy',
                headers={'X-GitHub-Event': 'Banana'}
            )

        self.assertEqual(response.status_code, 418)
        self.assertIn("I\\\'m a teapot", str(response.data))
