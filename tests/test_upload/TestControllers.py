from io import BytesIO
from flask import url_for
from mock import mock
from tests.base import BaseTestCase, MockRequests
from mod_auth.models import Role
from mod_upload.models import QueuedSample
from mod_sample.models import Sample, Issue
from flask import g
from importlib import reload


class TestControllers(BaseTestCase):

    def test_root(self):
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

    @mock.patch('requests.Session.post', side_effect=MockRequests)
    @mock.patch('os.rename')
    @mock.patch('git.Repo')
    def test_process(self, mock_repo, mock_rename, mock_post):
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
            from git import Repo
            Repo().git.show.return_value = 'issue template'
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
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.user)
        with self.app.test_client() as c:
            response = c.post('/account/login', data=self.create_login_form_data(
                self.user.email, self.user.password))
            response = c.get('/upload/ftp/filezilla')
            self.assert_template_used('upload/filezilla_template.xml')

    def test_ftp_index(self):
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.user)
        with self.app.test_client() as c:
            response = c.post('/account/login', data=self.create_login_form_data(
                self.user.email, self.user.password))
            response = c.get('/upload/ftp')
            self.assertEqual(response.status_code, 200)
            self.assert_template_used('upload/ftp_index.html')

    @mock.patch('os.remove')
    @mock.patch('os.rename')
    @mock.patch('magic.from_file')
    @mock.patch('mod_upload.controllers.create_hash_for_sample')
    @mock.patch('shutil.copy')
    def test_upload_ftp(self, mock_shutil, mock_hash, mock_magic, mock_rename, mock_remove):
        filehash = 'hash_code'
        mock_hash.return_value = filehash
        mock_magic.return_value = 'video/mp4'
        from mod_upload.controllers import upload_ftp
        upload_ftp(g.db, '/home/1/sample1.ts')
        queued_sample = QueuedSample.query.filter(
            QueuedSample.sha == filehash).first()
        self.assertEqual(queued_sample.filename, 'hash_code.ts')
        self.assertEqual(queued_sample.extension, '.ts')
        mock_remove.assert_called_with('/home/1/sample1.ts')

    @mock.patch('os.remove')
    @mock.patch('os.rename')
    @mock.patch('magic.from_file')
    @mock.patch('mod_upload.controllers.create_hash_for_sample')
    @mock.patch('shutil.copy')
    def test_upload_ftp_forbidden_mimetype(self, mock_shutil, mock_hash, mock_magic, mock_rename, mock_remove):
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
    @mock.patch('shutil.copy')
    def test_upload_ftp_forbidden_extension(self, mock_shutil, mock_hash, mock_magic, mock_rename, mock_remove):
        filehash = 'hash_code'
        mock_hash.return_value = filehash
        mock_magic.return_value = 'application/x-msdos-program'
        from mod_upload.controllers import upload_ftp
        upload_ftp(g.db, '/home/1/sample1.js')
        queued_sample = QueuedSample.query.filter(
            QueuedSample.sha == filehash).first()
        self.assertEqual(queued_sample, None)
