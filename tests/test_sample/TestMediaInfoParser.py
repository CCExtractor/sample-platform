from collections import OrderedDict
from unittest import mock

from mod_sample.media_info_parser import (InvalidMediaInfoError,
                                          MediaInfoFetcher)
from tests.base import BaseTestCase


class MockSample:

    def __init__(self):
        self.sha = 'sha'
        self.filename = 'filename'


MOCK_MediaInfoFetcher = mock.MagicMock()


class TestMediaInfoFetcher(BaseTestCase):

    @mock.patch('mod_sample.media_info_parser.open')
    @mock.patch('mod_sample.media_info_parser.os')
    @mock.patch('mod_sample.media_info_parser.xmltodict')
    def test_init(self, mock_xml, mock_os, mock_open):
        """
        Test initialisation of MediaInfoFetcher.
        """
        mock_xml.parse.return_value = {'Mediainfo': 'test'}

        MediaInfoFetcher(MockSample())

        mock_os.path.join.assert_called_once()
        mock_os.path.isfile.assert_called_once()
        mock_xml.parse.assert_called_once_with(mock_open().__enter__().read())

    @mock.patch('mod_sample.media_info_parser.open')
    @mock.patch('mod_sample.media_info_parser.os')
    @mock.patch('mod_sample.media_info_parser.xmltodict')
    def test_init_invalid_media_xml(self, mock_xml, mock_os, mock_open):
        """
        Test initialisation of MediaInfoFetcher with wrong media xml.
        """
        mock_xml.parse.side_effect = Exception

        with self.assertRaises(InvalidMediaInfoError):
            MediaInfoFetcher(MockSample())

        mock_os.path.join.assert_called_once()
        mock_os.path.isfile.assert_called_once()
        mock_xml.parse.assert_called_once_with(mock_open().__enter__().read())

    @mock.patch('mod_sample.media_info_parser.open')
    @mock.patch('mod_sample.media_info_parser.os')
    @mock.patch('mod_sample.media_info_parser.xmltodict')
    def test_init_invalid_media_info_path(self, mock_xml, mock_os, mock_open):
        """
        Test initialisation of MediaInfoFetcher with wrong media info file.
        """
        mock_os.path.isfile.return_value = False

        with self.assertRaises(InvalidMediaInfoError):
            MediaInfoFetcher(MockSample())

        mock_os.path.join.assert_called_once()
        mock_os.path.isfile.assert_called_once()
        mock_xml.parse.assert_not_called()

    def test_get_media_info(self):
        """
        Test get_media_info without forced parsing.
        """
        MOCK_MediaInfoFetcher.reset_mock()

        result = MediaInfoFetcher.get_media_info(MOCK_MediaInfoFetcher, False)

        MOCK_MediaInfoFetcher._process_tracks.assert_not_called()
        self.assertEqual(len(result), 4)

    def test_get_media_info_forced(self):
        """
        Test get_media_info with forced parsing.
        """
        MOCK_MediaInfoFetcher.reset_mock()

        result = MediaInfoFetcher.get_media_info(MOCK_MediaInfoFetcher, True)

        MOCK_MediaInfoFetcher._process_tracks.assert_called_once()
        self.assertEqual(len(result), 4)

    def test__process_tracks_file_key_error(self):
        """
        Test _process_tracks method with key error in self.media_info
        """
        MOCK_MediaInfoFetcher.reset_mock()
        MOCK_MediaInfoFetcher.media_info = {}

        with self.assertRaises(InvalidMediaInfoError):
            MediaInfoFetcher._process_tracks(MOCK_MediaInfoFetcher)

    def test__process_tracks_no_track(self):
        """
        Test _process_tracks method with no track in media info file
        """
        MOCK_MediaInfoFetcher.reset_mock()
        MOCK_MediaInfoFetcher.media_info = {'File': OrderedDict()}

        with self.assertRaises(InvalidMediaInfoError):
            MediaInfoFetcher._process_tracks(MOCK_MediaInfoFetcher)

    def test__process_tracks(self):
        """
        Test _process_tracks method with valid information.
        """
        MOCK_MediaInfoFetcher.reset_mock()
        MOCK_MediaInfoFetcher.media_info = {'File': OrderedDict([('track', ['track1'])])}

        MediaInfoFetcher._process_tracks(MOCK_MediaInfoFetcher)

        MOCK_MediaInfoFetcher._process_track.assert_called_once_with('track1')

    def test__process_track_not_ordereddict(self):
        """
        Test _process_track method for invalid track.
        """
        MOCK_MediaInfoFetcher.reset_mock()
        track = {}

        result = MediaInfoFetcher._process_track(MOCK_MediaInfoFetcher, track)

        self.assertIsNone(result)

    def test__process_track_missing_type(self):
        """
        Test _process_track method for track missing type.
        """
        MOCK_MediaInfoFetcher.reset_mock()
        track = OrderedDict()

        with self.assertRaises(InvalidMediaInfoError):
            MediaInfoFetcher._process_track(MOCK_MediaInfoFetcher, track)

    def test__process_track_general(self):
        """
        Test _process_track method for general track.
        """
        MOCK_MediaInfoFetcher.reset_mock()
        track = OrderedDict([('@type', 'General')])

        MediaInfoFetcher._process_track(MOCK_MediaInfoFetcher, track)

        MOCK_MediaInfoFetcher._process_general.assert_called_once_with(track)

    def test__process_track_video(self):
        """
        Test _process_track method for video track.
        """
        MOCK_MediaInfoFetcher.reset_mock()
        track = OrderedDict([('@type', 'Video')])

        MediaInfoFetcher._process_track(MOCK_MediaInfoFetcher, track)

        MOCK_MediaInfoFetcher._process_video.assert_called_once_with(track)

    def test__process_track_audio(self):
        """
        Test _process_track method for audio track.

        This is currently not supported.
        """
        MOCK_MediaInfoFetcher.reset_mock()
        track = OrderedDict([('@type', 'Audio')])

        MediaInfoFetcher._process_track(MOCK_MediaInfoFetcher, track)

        MOCK_MediaInfoFetcher._process_audio.assert_not_called()

    def test__process_track_text(self):
        """
        Test _process_track method for text track.
        """
        MOCK_MediaInfoFetcher.reset_mock()
        track = OrderedDict([('@type', 'Text')])

        MediaInfoFetcher._process_track(MOCK_MediaInfoFetcher, track)

        MOCK_MediaInfoFetcher._process_text.assert_called_once_with(track)

    def test__process_generic(self):
        """
        Test replacement of key '_' with " " using _process_generic method.
        """
        MOCK_MediaInfoFetcher.reset_mock()
        keys = ['some_key']
        track = OrderedDict([('some_key', 'test')])

        result = MediaInfoFetcher._process_generic(MOCK_MediaInfoFetcher, track, keys)
        self.assertEqual(result['some key'], track['some_key'])

    def test__process_general(self):
        """
        Test _process_general method.
        """
        MOCK_MediaInfoFetcher.reset_mock()
        track = {}
        key_list = ['Format', 'File_size', 'Duration', 'Codec_ID']

        MediaInfoFetcher._process_general(MOCK_MediaInfoFetcher, track)

        MOCK_MediaInfoFetcher._process_generic.assert_called_once_with(track, key_list)

    def test__process_video(self):
        """
        Test _process_video method.
        """
        MOCK_MediaInfoFetcher.reset_mock()
        track = {
            'Width': 10,
            'Height': 10,
            'Format': 'mp4',
            'Format_Info': 'video_content',
            'Frame_rate': '30',
            'Frame_rate_mode': 'fps',
            'Scan_type': 'test',
            'Scan_order': 'vertical',
            'ID': 'test'
        }
        key_list = ['Display_aspect_ratio', 'Writing_library', 'Duration', 'Codec_ID']

        MediaInfoFetcher._process_video(MOCK_MediaInfoFetcher, track)

        MOCK_MediaInfoFetcher._process_generic.assert_called_once_with(track, key_list)
        MOCK_MediaInfoFetcher.video_tracks.append.assert_called_once()

    def test__process_text(self):
        """
        Test _process_text method.
        """
        MOCK_MediaInfoFetcher.reset_mock()
        track = {'ID': 'test'}
        key_list = ['Format', 'Menu_ID', 'Muxing_mode']

        MediaInfoFetcher._process_text(MOCK_MediaInfoFetcher, track)

        MOCK_MediaInfoFetcher.caption_tracks.append.assert_called_once()
        MOCK_MediaInfoFetcher._process_generic.assert_called_once_with(track, key_list)

    @mock.patch('mod_sample.media_info_parser.sys')
    def test_generate_media_xml_windows(self, mock_sys):
        """
        Raise error when generating media info xml for windows.
        """
        mock_sys.platform = 'windows'

        with self.assertRaises(InvalidMediaInfoError):
            MediaInfoFetcher.generate_media_xml(MockSample())

    @mock.patch('mod_sample.media_info_parser.open')
    @mock.patch('mod_sample.media_info_parser.subprocess')
    @mock.patch('mod_sample.media_info_parser.sys')
    def test_generate_media_xml_not_file(self, mock_sys, mock_subprocess, mock_open):
        """
        Raise error when media_info_path is not a file.
        """
        mock_sys.platform = 'linux'

        with self.assertRaises(InvalidMediaInfoError):
            MediaInfoFetcher.generate_media_xml(MockSample())

        mock_open.assert_called_once()
        mock_subprocess.Popen.assert_called_once()

    @mock.patch('mod_sample.media_info_parser.MediaInfoFetcher')
    @mock.patch('mod_sample.media_info_parser.etree')
    @mock.patch('mod_sample.media_info_parser.os')
    @mock.patch('mod_sample.media_info_parser.open')
    @mock.patch('mod_sample.media_info_parser.subprocess')
    @mock.patch('mod_sample.media_info_parser.sys')
    def test_generate_media_xml(self, mock_sys, mock_subprocess, mock_open, mock_os, mock_etree,
                                mock_media_info_fetcher):
        """
        Test generate_media_xml method with valid information.
        """
        mock_sys.platform = 'linux'
        mock_os.path.isfile.return_value = True

        response = MediaInfoFetcher.generate_media_xml(MockSample())

        self.assertEqual(response, mock_media_info_fetcher())
        mock_open.assert_called_once()
        mock_subprocess.Popen.assert_called_once()
        mock_os.path.isfile.assert_called_once()
        mock_etree.parse.assert_called_once()
