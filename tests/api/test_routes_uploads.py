import hashlib
import io
import json
from unittest import mock

from flask import g

from mod_api.middleware.rate_limit import _rate_limit_store
from mod_auth.models import Role, User
from mod_sample.models import ExtraFile, ForbiddenExtension, Sample
from mod_upload.models import QueuedSample
from tests.api.base import ApiTestCase

CONTENT = b'\x00\x01two three four' * 64
SHA = hashlib.sha256(CONTENT).hexdigest()


class TestRoutesUploads(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.setup_run_data('upl')
        self.admin_id = self.admin.id
        self.user_id = self.user.id

        self.bystander = User('testother_upl', Role.user,
                              'upl_other@local.com',
                              User.generate_hash('otherpass123'))
        g.db.add(self.bystander)
        g.db.commit()

        _rate_limit_store.clear()

    def _admin(self, name):
        token = self.get_token('upl_admin@local.com', 'adminpass123', name,
                               scopes=['runs:read', 'runs:write'])
        return {'Authorization': f'Bearer {token}'}

    def _bystander(self, name):
        token = self.get_token('upl_other@local.com', 'otherpass123', name,
                               scopes=['runs:read', 'runs:write'])
        return {'Authorization': f'Bearer {token}'}

    def _upload(self, headers, name='clip.ts', content=CONTENT):
        return self.client.post(
            '/api/v1/samples/upload',
            data={'file': (io.BytesIO(content), name)},
            content_type='multipart/form-data',
            headers=headers)

    def _queue_row(self, user_id):
        queued = QueuedSample(SHA, '.ts', 'clip', user_id)
        g.db.add(queued)
        g.db.commit()
        return queued.id

    def test_upload_requires_a_file_part(self):
        res = self.client.post(
            '/api/v1/samples/upload',
            data={}, content_type='multipart/form-data',
            headers=self._admin('up1'))

        self.assertEqual(res.status_code, 400)

    @mock.patch('mod_api.routes.uploads.os.rename')
    @mock.patch('mod_api.routes.uploads.open', new_callable=mock.mock_open)
    def test_upload_queues_the_file(self, _open, _rename):
        res = self._upload(self._admin('up2'))

        self.assertEqual(res.status_code, 201)
        # The hash is both the duplicate check and the stored name, so it
        # has to be the digest of what was actually read off the stream.
        self.assertEqual(res.json['sha'], SHA)
        self.assertIsNotNone(
            QueuedSample.query.filter(QueuedSample.sha == SHA).first())

    def test_upload_rejects_an_unusable_file_name(self):
        # secure_filename empties this one, and an empty name used to
        # resolve to the TempFiles directory and fail on open().
        res = self._upload(self._admin('up2b'), name='...')

        self.assertEqual(res.status_code, 400)
        self.assertIsNone(
            QueuedSample.query.filter(QueuedSample.sha == SHA).first())

    @mock.patch('mod_api.routes.uploads.os.rename')
    @mock.patch('mod_api.routes.uploads.open', new_callable=mock.mock_open)
    def test_uploads_of_one_name_stage_to_separate_files(self, _open, _rename):
        # Same file name twice: the staging paths have to differ, or
        # concurrent uploads write into each other.
        first = self._upload(self._admin('up2c'), name='clash.ts')
        second = self._upload(self._bystander('up2d'), name='clash.ts',
                              content=CONTENT + b'different')

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)

        staged = [call.args[0] for call in _open.call_args_list]
        self.assertEqual(len(staged), 2)
        self.assertNotEqual(staged[0], staged[1])
        # And neither is named after what the caller sent.
        for path in staged:
            self.assertNotIn('clash', path)

    @mock.patch('mod_api.routes.uploads.os.remove')
    @mock.patch('mod_api.routes.uploads.open', new_callable=mock.mock_open)
    def test_upload_rejects_content_already_in_the_library(
            self, _open, remove):
        g.db.add(Sample(SHA, 'ts', 'already_here'))
        g.db.commit()

        res = self._upload(self._admin('up3'))

        self.assertEqual(res.status_code, 409)
        # The half-written temp file is cleaned up rather than left behind.
        self.assertTrue(remove.called)

    @mock.patch('mod_api.routes.uploads.open', new_callable=mock.mock_open)
    def test_upload_rejects_a_forbidden_extension(self, _open):
        g.db.add(ForbiddenExtension('ts'))
        g.db.commit()

        res = self._upload(self._admin('up4'))

        self.assertEqual(res.status_code, 403)
        self.assertIsNone(
            QueuedSample.query.filter(QueuedSample.sha == SHA).first())

    def test_admin_sees_the_whole_queue(self):
        self._queue_row(self.user_id)

        res = self.client.get(
            '/api/v1/queued-samples', headers=self._admin('up5'))

        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json['data']), 1)

    def test_others_see_only_their_own_queue(self):
        self._queue_row(self.user_id)

        res = self.client.get(
            '/api/v1/queued-samples', headers=self._bystander('up6'))

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['data'], [])

    def test_someone_elses_queued_sample_reads_as_absent(self):
        queued_id = self._queue_row(self.user_id)

        res = self.client.get(
            f'/api/v1/queued-samples/{queued_id}',
            headers=self._bystander('up7'))

        # Not 403: a different reply would let an id be used to find out
        # what other people have queued.
        self.assertEqual(res.status_code, 404)

    @mock.patch('mod_api.routes.uploads.os.path.isfile', return_value=True)
    @mock.patch('mod_api.routes.uploads.os.rename')
    def test_finalize_creates_a_sample(self, rename, _isfile):
        # Version 1.2.3 is seeded by the test base.
        queued_id = self._queue_row(self.admin_id)

        res = self.client.post(
            f'/api/v1/queued-samples/{queued_id}/finalize',
            data=json.dumps({'version': '1.2.3', 'platform': 'linux'}),
            content_type='application/json',
            headers=self._admin('up8'))

        self.assertEqual(res.status_code, 201)
        self.assertIsNotNone(Sample.query.filter(Sample.sha == SHA).first())
        self.assertIsNone(
            QueuedSample.query.filter(QueuedSample.id == queued_id).first())
        # The file only moves once the rows are committed.
        self.assertTrue(rename.called)

    @mock.patch('mod_api.routes.uploads.os.path.isfile', return_value=True)
    def test_finalize_rejects_an_unknown_version(self, _isfile):
        queued_id = self._queue_row(self.admin_id)

        res = self.client.post(
            f'/api/v1/queued-samples/{queued_id}/finalize',
            data=json.dumps({'version': '9.9.9', 'platform': 'linux'}),
            content_type='application/json',
            headers=self._admin('up9'))

        self.assertEqual(res.status_code, 400)

    @mock.patch('mod_api.routes.uploads.os.path.isfile', return_value=False)
    def test_finalize_refuses_when_the_file_is_gone(self, _isfile):
        # Version 1.2.3 is seeded by the test base.
        queued_id = self._queue_row(self.admin_id)

        res = self.client.post(
            f'/api/v1/queued-samples/{queued_id}/finalize',
            data=json.dumps({'version': '1.2.3', 'platform': 'linux'}),
            content_type='application/json',
            headers=self._admin('up10'))

        self.assertEqual(res.status_code, 409)
        # The upload stays queued so it can be retried.
        self.assertIsNotNone(
            QueuedSample.query.filter(QueuedSample.id == queued_id).first())

    @mock.patch('mod_api.routes.uploads.os.remove')
    def test_delete_queued_sample(self, _remove):
        queued_id = self._queue_row(self.admin_id)

        res = self.client.delete(
            f'/api/v1/queued-samples/{queued_id}',
            headers=self._admin('up11'))

        self.assertEqual(res.status_code, 200)
        self.assertIsNone(
            QueuedSample.query.filter(QueuedSample.id == queued_id).first())

    @mock.patch('mod_api.routes.uploads.os.path.isfile', return_value=True)
    @mock.patch('mod_api.routes.uploads.os.rename')
    def test_link_attaches_the_upload_to_a_sample(self, rename, _isfile):
        queued_id = self._queue_row(self.admin_id)
        target = Sample('target_sha', 'ts', 'target')
        g.db.add(target)
        g.db.commit()
        target_id = target.id

        res = self.client.post(
            f'/api/v1/queued-samples/{queued_id}/link',
            data=json.dumps({'sample_id': target_id}),
            content_type='application/json',
            headers=self._admin('up12'))

        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json['sample_id'], target_id)
        self.assertEqual(
            ExtraFile.query.filter_by(sample_id=target_id).count(), 1)
        self.assertIsNone(
            QueuedSample.query.filter(QueuedSample.id == queued_id).first())
        self.assertTrue(rename.called)

    @mock.patch('mod_api.routes.uploads.os.path.isfile', return_value=True)
    def test_link_rejects_an_unknown_sample(self, _isfile):
        queued_id = self._queue_row(self.admin_id)

        res = self.client.post(
            f'/api/v1/queued-samples/{queued_id}/link',
            data=json.dumps({'sample_id': 999999}),
            content_type='application/json',
            headers=self._admin('up13'))

        self.assertEqual(res.status_code, 404)
        # The upload stays queued when the link cannot be made.
        self.assertIsNotNone(
            QueuedSample.query.filter(QueuedSample.id == queued_id).first())
