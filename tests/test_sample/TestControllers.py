from importlib import reload
from unittest import mock

from flask import g

from mod_home.models import CCExtractorVersion
from mod_sample.media_info_parser import InvalidMediaInfoError
from mod_sample.models import Sample
from tests.base import BaseTestCase


def raise_media_exception():
    """Raise error about failed media info generation."""
    raise InvalidMediaInfoError('Could not generate media info')


class TestControllers(BaseTestCase):
    """Test sample pages."""

    def test_root(self):
        """Test the access of the sample index page."""
        response = self.app.test_client().get('/sample/')
        self.assertEqual(response.status_code, 200)
        self.assert_template_used('sample/index.html')

    @mock.patch('mod_sample.media_info_parser.MediaInfoFetcher')
    def test_sample_pass(self, mock_media):
        """Test the access and data of the passed sample info page."""
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
        """Test the access and data of the failed sample info page."""
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
        """Test sample loading."""
        import mod_sample.controllers
        reload(mod_sample.controllers)
        sample = Sample.query.filter(Sample.sha == 'sample1').first()
        from unittest.mock import Mock
        media_info_fetcher = mock_media(sample)
        media_info_fetcher.get_media_info.side_effect = raise_media_exception
        response = self.app.test_client().get('/sample/sample1')
        self.assertEqual(response.status_code, 200)
        self.assert_template_used('sample/sample_info.html')

    def test_sample_id(self):
        """Test if Sample Id would be returned."""
        response = self.app.test_client().get('/sample/1')
        self.assertEqual(response.status_code, 200)
        self.assert_template_used('sample/sample_info.html')

    @mock.patch('mod_sample.controllers.serve_file_download')
    @mock.patch('mod_sample.controllers.Sample')
    def test_download_sample(self, mock_sample, mock_serve_download):
        """Test function download_sample."""
        from mod_sample.controllers import download_sample

        response = download_sample(1)

        self.assertEqual(response, mock_serve_download())
        mock_sample.query.filter.assert_called_once_with(mock_sample.id == 1)

    @mock.patch('mod_sample.controllers.serve_file_download')
    @mock.patch('mod_sample.controllers.Sample')
    def test_download_sample_raise_exception(self, mock_sample, mock_serve_download):
        """Test function download_sample to raise SampleNotFoundException."""
        from mod_sample.controllers import (SampleNotFoundException,
                                            download_sample)

        mock_sample.query.filter.return_value.first.return_value = None

        with self.assertRaises(SampleNotFoundException):
            download_sample(1)

        mock_sample.query.filter.assert_called_once_with(mock_sample.id == 1)
        mock_serve_download.assert_not_called()

    @mock.patch('mod_sample.controllers.serve_file_download')
    @mock.patch('mod_sample.controllers.Sample')
    @mock.patch('mod_sample.controllers.os')
    def test_download_sample_media_info(self, mock_os, mock_sample, mock_serve_download):
        """Test function download_sample_media_info."""
        from mod_sample.controllers import download_sample_media_info

        response = download_sample_media_info(1)

        self.assertEqual(response, mock_serve_download())
        mock_sample.query.filter.assert_called_once_with(mock_sample.id == 1)
        mock_os.path.isfile.assert_called_once()

    @mock.patch('mod_sample.controllers.serve_file_download')
    @mock.patch('mod_sample.controllers.Sample')
    @mock.patch('mod_sample.controllers.os')
    def test_download_sample_media_info_path_wrong(self, mock_os, mock_sample, mock_serve_download):
        """Test function download_sample_media_info with wrong path for media info."""
        from mod_sample.controllers import (SampleNotFoundException,
                                            download_sample_media_info)

        mock_os.path.isfile.return_value = False

        with self.assertRaises(SampleNotFoundException):
            download_sample_media_info(1)

        mock_sample.query.filter.assert_called_once_with(mock_sample.id == 1)
        mock_os.path.isfile.assert_called_once()

    @mock.patch('mod_sample.controllers.serve_file_download')
    @mock.patch('mod_sample.controllers.Sample')
    @mock.patch('mod_sample.controllers.os')
    def test_download_sample_media_info_sample_not_found(self, mock_os, mock_sample, mock_serve_download):
        """Test function download_sample_media_info to raise SampleNotFoundException."""
        from mod_sample.controllers import (SampleNotFoundException,
                                            download_sample_media_info)

        mock_sample.query.filter.return_value.first.return_value = None

        with self.assertRaises(SampleNotFoundException):
            download_sample_media_info(1)

        mock_sample.query.filter.assert_called_once_with(mock_sample.id == 1)
        mock_os.path.isfile.assert_not_called()

    @mock.patch('mod_sample.controllers.serve_file_download')
    @mock.patch('mod_sample.controllers.Sample')
    @mock.patch('mod_sample.controllers.ExtraFile')
    def test_download_sample_additional(self, mock_extra, mock_sample, mock_serve_download):
        """Test function download_sample_additional."""
        from mod_sample.controllers import download_sample_additional

        response = download_sample_additional(1, 1)

        self.assertEqual(response, mock_serve_download())
        mock_sample.query.filter.assert_called_once_with(mock_sample.id == 1)
        mock_extra.query.filter.assert_called_once_with(mock_extra.id == 1)

    @mock.patch('mod_sample.controllers.serve_file_download')
    @mock.patch('mod_sample.controllers.Sample')
    @mock.patch('mod_sample.controllers.ExtraFile')
    def test_download_sample_additional_sample_not_found(self, mock_extra, mock_sample, mock_serve_download):
        """Test function download_sample_additional to raise SampleNotFoundException."""
        from mod_sample.controllers import (SampleNotFoundException,
                                            download_sample_additional)

        mock_sample.query.filter.return_value.first.return_value = None

        with self.assertRaises(SampleNotFoundException):
            download_sample_additional(1, 1)

        mock_sample.query.filter.assert_called_once_with(mock_sample.id == 1)
        mock_extra.query.filter.assert_not_called()

    @mock.patch('mod_sample.controllers.serve_file_download')
    @mock.patch('mod_sample.controllers.Sample')
    @mock.patch('mod_sample.controllers.ExtraFile')
    def test_download_sample_additional_extrafile_not_found(self, mock_extra, mock_sample, mock_serve_download):
        """Test function download_sample_additional to raise SampleNotFoundException when extra file not found."""
        from mod_sample.controllers import (SampleNotFoundException,
                                            download_sample_additional)

        mock_extra.query.filter.return_value.first.return_value = None

        with self.assertRaises(SampleNotFoundException):
            download_sample_additional(1, 1)

        mock_sample.query.filter.assert_called_once_with(mock_sample.id == 1)
        mock_extra.query.filter.assert_called_once_with(mock_extra.id == 1)
