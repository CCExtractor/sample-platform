from mock import mock
from importlib import reload
from tests.base import BaseTestCase
from mod_sample.models import Sample
from mod_home.models import CCExtractorVersion
from mod_sample.media_info_parser import InvalidMediaInfoError
from flask import g


def raise_media_exception():
    raise InvalidMediaInfoError('Could not generate media info')


class TestControllers(BaseTestCase):

    def test_root(self):
        response = self.app.test_client().get('/sample/')
        self.assertEqual(response.status_code, 200)
        self.assert_template_used('sample/index.html')

    @mock.patch('mod_sample.media_info_parser.MediaInfoFetcher')
    def test_sample_pass(self, mock_media):
        import mod_sample.controllers
        reload(mod_sample.controllers)
        response = self.app.test_client().get('/sample/sample1')
        self.assertEqual(response.status_code, 200)
        self.assert_template_used('sample/sample_info.html')
        sample = Sample.query.filter(Sample.sha == 'sample1').first()
        mock_media.assert_called_with(sample)
        self.assertIn(sample.sha, str(response.data))
        self.assertIn('Repository: Pass', str(response.data))
        self.assertIn('Last release: Pass', str(response.data))

    @mock.patch('mod_sample.media_info_parser.MediaInfoFetcher')
    def test_sample_fail(self, mock_media):
        version = CCExtractorVersion('1.3', '2015-02-27T19:35:32Z', 'abcdefgh')
        g.db.add(version)
        g.db.commit()
        import mod_sample.controllers
        reload(mod_sample.controllers)
        response = self.app.test_client().get('/sample/sample2')
        self.assertEqual(response.status_code, 200)
        self.assert_template_used('sample/sample_info.html')
        sample = Sample.query.filter(Sample.sha == 'sample2').first()
        mock_media.assert_called_with(sample)
        self.assertIn('Repository: Pass', str(response.data))
        self.assertIn('Last release: Fail', str(response.data))

    @mock.patch('mod_sample.media_info_parser.MediaInfoFetcher')
    def test_sample_create_xml(self, mock_media):
        import mod_sample.controllers
        reload(mod_sample.controllers)
        sample = Sample.query.filter(Sample.sha == 'sample1').first()
        from mock import Mock
        media_info_fetcher = mock_media(sample)
        media_info_fetcher.get_media_info.side_effect = raise_media_exception
        response = self.app.test_client().get('/sample/sample1')
        self.assertEqual(response.status_code, 200)
        self.assert_template_used('sample/sample_info.html')

    def test_sample_id(self):
        """
        Test if Sample Id would be returned
        """
        response = self.app.test_client().get('/sample/1')
        self.assertEqual(response.status_code, 200)
        self.assert_template_used('sample/sample_info.html')
