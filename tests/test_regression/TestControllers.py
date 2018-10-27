from tests.base import BaseTestCase
from mod_auth.models import Role
from mod_regression.models import RegressionTest


class TestControllers(BaseTestCase):
    def test_root(self):
        response = self.app.test_client().get('/regression/')
        self.assertEqual(response.status_code, 200)
        self.assert_template_used('regression/index.html')

    def test_specific_regression_test_loads(self):
        response = self.app.test_client().get('/regression/test/1/view')
        self.assertEqual(response.status_code, 200)
        self.assert_template_used('regression/test_view.html')
        regression_test = RegressionTest.query.filter(RegressionTest.id == 1).first()
        self.assertIn(regression_test.command, str(response.data))

    def test_regression_test_status_toggle(self):
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.admin)
        with self.app.test_client() as c:
            response = c.post(
                '/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            regression_test = RegressionTest.query.filter(RegressionTest.id == 1).first()
            response = c.get('/regression/test/1/toggle')
            self.assertEqual(response.status_code, 200)
            self.assertEqual('success', response.json['status'])
            if regression_test.active == 1:
                self.assertEqual('False', response.json['active'])
            else:
                self.assertEqual('True', response.json['active'])

    def test_delete_if_will_abort_due_to_lack_of_permission(self):
        """
        This will test if it will abort on lack of permission
        :return:
        """
        response = self.app.test_client().get('/regression/test/9432/delete')
        self.assertEqual(response.status_code, 500)

    def test_delete_if_will_throw_404(self):
        """
        Check if it will throw an error 404
        :return:
        """
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.admin)
        with self.app.test_client() as c:
            response = c.post(
                '/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            responseRegression = self.app.test_client().get('/regression/test/9432/delete')
            self.assertEqual(responseRegression.status_code, 404)