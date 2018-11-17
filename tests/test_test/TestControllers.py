from tests.base import BaseTestCase
from mod_test.models import Test, TestPlatform
from mod_regression.models import RegressionTest
from mod_auth.models import Role

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
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.tester)
        self.create_forktest("own-fork-commit", TestPlatform.linux, regression_tests=[2])
        self.complete_forktest(3, [2])
        response = self.app.test_client().get('/test/3')
        self.assertEqual(response.status_code, 200)
        self.assert_template_used('test/by_id.html')
        regression_tests = RegressionTest.query.all()
        self.assertIn(regression_tests[1].command, str(response.data))
        self.assertNotIn(regression_tests[0].command, str(response.data))

    def test_restart_with_permission(self):
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.tester)
        self.create_forktest("own-fork-commit", TestPlatform.linux, regression_tests=[2])
        self.complete_forktest(3, [2])
        with self.app.test_client() as c:
            response = c.post(
                '/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.get('/test/restart_test/3')
            test = Test.query.filter(Test.id == 3).first()
            self.assertEqual(test.finished, False)

    def test_restart_fails_on_no_permission(self):
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.user)
        with self.app.test_client() as c:
            response = c.post(
                '/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.get('/test/restart_test/1')
            self.assert403(response)

    def test_stop_with_permission(self):
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.tester)
        self.create_forktest("own-fork-commit", TestPlatform.linux, regression_tests=[2])
        with self.app.test_client() as c:
            response = c.post(
                '/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.get('/test/stop_test/3')
            test = Test.query.filter(Test.id == 3).first()
            self.assertEqual(test.finished, True)

    def test_stop_fails_on_no_permission(self):
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.user)
        with self.app.test_client() as c:
            response = c.post(
                '/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.get('/test/stop_test/1')
            self.assert403(response)

    def test_get_json_data_throw_not_found_error(self):
        """
        Test if get_json_data throws Error 404
        """
        response = self.app.test_client().get('/test/get_json_data/99999')
        self.assertEqual(response.json['status'], 'failure')
        self.assertEqual(response.json['error'], 'Test not found')

    def test_get_nonexistent_test(self):
        """
        Test if it'll return a 404 on a non existent test
        """
        response = self.app.test_client().get('/test/99999')
        self.assertEqual(response.status_code, 404)
        self.assert_template_used('test/test_not_found.html')

    def test_ccextractor_version_not_found(self):
        """
        Test View for CCExtractor Test if test won't be found
        """
        response = self.app.test_client().get('/test/ccextractor/0.8494')
        self.assertEqual(response.status_code, 404)
        self.assert_template_used('test/test_not_found.html')
