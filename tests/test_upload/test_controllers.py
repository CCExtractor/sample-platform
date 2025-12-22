import base64
from importlib import reload
from io import BytesIO
from unittest import mock

from flask import g, url_for

from mod_auth.models import Role
from mod_sample.models import Issue, Sample
from mod_upload.models import QueuedSample
from tests.base import BaseTestCase, MockResponse


class TestControllers(BaseTestCase):
    """Test upload-related cases."""

    def test_root(self):
        """Test the access of the upload index page."""
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.user)
        with self.app.test_client() as c:
            response = c.post('/account/login', data=self.create_login_form_data(
                self.user.email, self.user.password))
            response = c.get('/upload/')
            self.assertEqual(response.status_code, 200)
            self.assert_template_used('upload/index.html')

    @mock.patch('os.rename')
    @mock.patch('mod_upload.controllers.create_hash_for_sample')
    @mock.patch('mod_upload.controllers.open')
    @mock.patch('werkzeug.datastructures.FileStorage.save')
    def test_upload(self, file_storage, mock_open, mock_hash, mock_rename):
        """Test sample uploading."""
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.user)
        with self.app.test_client() as c:
            response = c.post('/account/login', data=self.create_login_form_data(
                self.user.email, self.user.password))
            filename = 'hello_world.ts'
            filehash = 'hash_code'
            saved_filename = 'hash_code.ts'
            test_file = (BytesIO(b'test file contents'), filename)
            mock_hash.return_value = filehash
            response = c.post(url_for('upload.upload'),
                              content_type='multipart/form-data',
                              buffered=True,
                              data=dict(file=test_file),
                              follow_redirects=True)
            import os

            from run import config
            self.assertEqual(response.status_code, 200)
            temp_path = os.path.join(config.get(
                'SAMPLE_REPOSITORY', ''), 'TempFiles', filename)
            file_storage.assert_called_with(temp_path)
            queued_sample = QueuedSample.query.filter(
                QueuedSample.sha == filehash).first()
            self.assertEqual(queued_sample.filename, saved_filename)
            self.assertEqual(queued_sample.extension, '.ts')

    @mock.patch('github.Github')
    @mock.patch('requests.Session.post')
    @mock.patch('os.rename')
    def test_process(self, mock_rename, mock_post, mock_github):
        """Test sample upload process."""
        import mod_upload.controllers
        reload(mod_upload.controllers)
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.user)
        with self.app.test_client() as c:
            filename = 'hello_world.ts'
            filehash = 'hash_code'
            saved_filename = 'hash_code.ts'
            queued_sample = QueuedSample(filehash, '.ts',
                                         saved_filename, 2)
            g.db.add(queued_sample)
            g.db.commit()
            response = c.post('/account/login', data=self.create_login_form_data(
                self.user.email, self.user.password))
            mock_github.return_value.get_repo.return_value.get_contents = mock.MagicMock(return_value={
                "content": base64.b64encode("test".encode("ascii")).decode("ascii"),
                "encoding": 'base64'
            })
            mock_post.return_value = MockResponse({'number': 1, 'title': 'test', 'user': {'login': 'test'},
                                                   'created_at': '2023-03-08T13:25:00Z', 'state': 'open'}, 201)
            response = c.post(url_for('upload.process_id', upload_id=1),
                              data=dict(
                notes='test note',
                parameters='test parameters',
                platform='linux',
                version=1,
                report='y',
                IssueTitle='Issue Title',
                IssueBody='Issue Body',
                submit=True
            ))
            sample = Sample.query.filter(Sample.sha == filehash).first()
            self.assertNotEqual(sample, None)
            issue = Issue.query.filter(Issue.sample_id == sample.id).first()
            self.assertNotEqual(issue, None)
            self.assertEqual(response.status_code, 302)

    def test_ftp_filezilla(self):
        """Test the access of the ftp filezilla page."""
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.user)
        with self.app.test_client() as c:
            response = c.post('/account/login', data=self.create_login_form_data(
                self.user.email, self.user.password))
            response = c.get('/upload/ftp/filezilla')
            self.assert_template_used('upload/filezilla_template.xml')

    def test_ftp_index(self):
        """Test the access of the ftp index page."""
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.user)
        with self.app.test_client() as c:
            response = c.post('/account/login', data=self.create_login_form_data(
                self.user.email, self.user.password))
            response = c.get('/upload/ftp')
            self.assertEqual(response.status_code, 200)
            self.assert_template_used('upload/ftp_index.html')

    @mock.patch('os.rename')
    @mock.patch('magic.from_file')
    @mock.patch('mod_upload.controllers.create_hash_for_sample')
    @mock.patch('shutil.move')
    def test_upload_ftp(self, mock_shutil, mock_hash, mock_magic, mock_rename):
        """Test successful sample upload via ftp."""
        filehash = 'hash_code'
        mock_hash.return_value = filehash
        mock_magic.return_value = 'video/mp4'
        from mod_upload.controllers import upload_ftp
        upload_ftp(g.db, '/home/1/sample1.ts')
        queued_sample = QueuedSample.query.filter(
            QueuedSample.sha == filehash).first()
        self.assertEqual(queued_sample.filename, 'hash_code.ts')
        self.assertEqual(queued_sample.extension, '.ts')
        mock_shutil.assert_called_with('/home/1/sample1.ts', 'temp/TempFiles/sample1.ts')

    @mock.patch('os.remove')
    @mock.patch('os.rename')
    @mock.patch('magic.from_file')
    @mock.patch('mod_upload.controllers.create_hash_for_sample')
    @mock.patch('shutil.move')
    def test_upload_ftp_forbidden_mimetype(self, mock_shutil, mock_hash, mock_magic, mock_rename, mock_remove):
        """Test sample upload via ftp with forbidden mimetype."""
        filehash = 'hash_code'
        mock_hash.return_value = filehash
        mock_magic.return_value = 'application/javascript'
        from mod_upload.controllers import upload_ftp
        upload_ftp(g.db, '/home/1/sample1.js')
        queued_sample = QueuedSample.query.filter(
            QueuedSample.sha == filehash).first()
        self.assertEqual(queued_sample, None)

    @mock.patch('os.remove')
    @mock.patch('os.rename')
    @mock.patch('magic.from_file')
    @mock.patch('mod_upload.controllers.create_hash_for_sample')
    @mock.patch('shutil.move')
    def test_upload_ftp_forbidden_extension(self, mock_shutil, mock_hash, mock_magic, mock_rename, mock_remove):
        """Test sample upload via ftp with forbidden extension."""
        filehash = 'hash_code'
        mock_hash.return_value = filehash
        mock_magic.return_value = 'application/x-msdos-program'
        from mod_upload.controllers import upload_ftp
        upload_ftp(g.db, '/home/1/sample1.js')
        queued_sample = QueuedSample.query.filter(
            QueuedSample.sha == filehash).first()
        self.assertEqual(queued_sample, None)

    # TODO: The methods below are not working due to decorator login_required not being mocked
    # @mock.patch('mod_upload.controllers.login_required', side_effect=mock_decorator)
    # def test_link_id_confirm_invalid(self, mock_login):
    #     """
    #     Try to confirm link for invalid sample and queue.
    #     """
    #     from mod_upload.controllers import link_id_confirm, QueuedSampleNotFoundException

    #     with self.assertRaises(QueuedSampleNotFoundException):
    #         link_id_confirm(1000, 1000)

    # @mock.patch('mod_upload.controllers.redirect')
    # @mock.patch('mod_upload.controllers.login_required', side_effect=mock_decorator)
    # @mock.patch('mod_upload.controllers.QueuedSample')
    # @mock.patch('mod_upload.controllers.Sample')
    # def test_link_id_confirm(self, mock_sample, mock_queue, mock_login, mock_redirect):
    #     """
    #     Test confirm link for valid sample and queue.
    #     """
    #     from mod_upload.controllers import link_id_confirm

    #     mock_queue.query.filter.return_value.first.return_value.user_id = g.user
    #     mock_sample.query.filter.return_value.first.return_value.upload.user_id = g.user

    #     response = link_id_confirm(1, 1)

    #     self.assertEqual(response, mock_redirect())
    #     mock_queue.query.filter.assert_called_once_with(mock_queue.id == 1)
    #     mock_sample.query.filter.assert_called_once_with(mock_sample.id == 1)

    def test_create_hash_for_sample(self):
        """Test creating hash for temp file."""
        from tempfile import NamedTemporaryFile

        from mod_upload.controllers import create_hash_for_sample

        f = NamedTemporaryFile()

        resp = create_hash_for_sample(f.name)

        self.assertIsInstance(resp, str)

    @mock.patch('os.rename')
    @mock.patch('mod_upload.controllers.config', {
        'GITHUB_TOKEN': '', 'GITHUB_OWNER': 'test', 'GITHUB_REPOSITORY': 'test'})
    def test_process_empty_github_token(self, mock_rename):
        """Test process_id handles empty GitHub token when reporting issue."""
        import mod_upload.controllers
        reload(mod_upload.controllers)
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.user)
        with self.app.test_client() as c:
            filehash = 'test_hash_empty_token'
            saved_filename = 'test_hash_empty_token.ts'
            queued_sample = QueuedSample(filehash, '.ts', saved_filename, 2)
            g.db.add(queued_sample)
            g.db.commit()
            c.post('/account/login', data=self.create_login_form_data(
                self.user.email, self.user.password))

            response = c.post(
                url_for('upload.process_id', upload_id=queued_sample.id),
                data=dict(
                    notes='test note',
                    parameters='test parameters',
                    platform='linux',
                    version=1,
                    report='y',
                    IssueTitle='Issue Title',
                    IssueBody='Issue Body',
                    submit=True
                ), follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'token not configured', response.data)
