from tests.base import BaseTestCase
from mod_test.models import TestPlatform
from mod_regression.models import RegressionTest


class TestControllers(BaseTestCase):
    def test_root(self):
        response = self.app.test_client().get('/test/')
        self.assertEqual(response.status_code, 200)
        self.assert_template_used('test/index.html')

    def test_specific_test_loads(self):
        response = self.app.test_client().get('/test/1')
        self.assertEqual(response.status_code, 200)
        self.assert_template_used('test/by_id.html')

    def test_customize_test_loads(self):
        self.create_forktest("own-fork-commit", TestPlatform.linux, regression_tests=[2])
        self.complete_forktest(3, [2])
        response = self.app.test_client().get('/test/3')
        self.assertEqual(response.status_code, 200)
        self.assert_template_used('test/by_id.html')
        regression_tests = RegressionTest.query.all()
        self.assertIn(regression_tests[1].command, str(response.data))
        self.assertNotIn(regression_tests[0].command, str(response.data))
