"""Contains classes and methods to parse media info from samples."""

import collections
import os
import subprocess
import sys
from collections import OrderedDict
from typing import Any, Dict, List, Type

import xmltodict
from lxml import etree


class InvalidMediaInfoError(Exception):
    """Custom exception class to handle Invalid Media."""

    def __init__(self, message) -> None:
        Exception.__init__(self)
        self.message = message


class MediaInfoFetcher:
    """Class to fetch media info from sample."""

    def __init__(self, sample) -> None:
        from run import config
        # Fetch media info
        media_info_path = os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'TestFiles', 'media', sample.sha + '.xml')
        if os.path.isfile(media_info_path):
            with open(media_info_path) as fd:
                try:
                    doc = xmltodict.parse(fd.read())
                except Exception:
                    raise InvalidMediaInfoError('No Mediainfo root element present')
                if 'Mediainfo' in doc:
                    self.media_info = doc['Mediainfo']
                    self.video_tracks = []
                    self.caption_tracks = []
                    self.audio_tracks = []
                    self.other_tracks = []
                    self.general_track = {}
                    self.parsed = False
                else:
                    raise InvalidMediaInfoError('No Mediainfo root element present')
        else:
            raise InvalidMediaInfoError('File {path} not found'.format(path=media_info_path))

    def get_media_info(self, force_parse=False) -> List[Dict[str, Any]]:
        """Get media info from the sample file."""
        result = [{
            'name': 'Media info version',
            'value': self.media_info['@version']
        }]

        if not self.parsed or force_parse:
            self._process_tracks()

        result.append({
            'name': 'General',
            'value': self.general_track
        })
        result.append({
            'name': 'Video',
            'value': self.video_tracks
        })
        result.append({
            'name': 'Captions',
            'value': self.caption_tracks
        })

        return result

    def _process_tracks(self) -> None:
        """Reset stored tracks."""
        if self.parsed:
            self.video_tracks = []
            self.caption_tracks = []
            self.audio_tracks = []
            self.other_tracks = []
            self.general_track = {}
            self.parsed = False

        try:
            file_info = self.media_info['File']
            if 'track' in file_info:
                for track in file_info['track']:
                    self._process_track(track)
                # Ran through all tracks, no errors, so parsed successfully
                self.parsed = True
            else:
                raise InvalidMediaInfoError('No tracks present in XML')
        except KeyError:
            raise InvalidMediaInfoError('No File element present in XML')

    def _process_track(self, track) -> None:
        """
        Process different tracks according to their type.

        :param track: track to be processed, is a dict with track info
        :type track: dict
        :raises InvalidMediaInfoError: when track dict doesn't contain type
        """
        if type(track) is not OrderedDict:
            return
        if '@type' not in track:
            raise InvalidMediaInfoError('Track file does not contain a type')
        track_type = track['@type']
        if track_type == 'General':
            self._process_general(track)
        elif track_type == 'Video':
            self._process_video(track)
        elif track_type == 'Audio':
            # Implement at some point
            pass
        elif track_type == 'Text':
            self._process_text(track)
        # Other tracks are ignored for now
        return

    def _process_generic(self, track, keys) -> dict:
        """
        Process generic information about a track.

        :param track: track
        :type track: dict
        :param keys: keys to be parsed
        :type keys: list
        :return: parsed information
        :rtype: dict
        """
        result = {}
        # Values we could use, but they're not always present
        for key in keys:
            if key in track:
                result[key.replace('_', ' ')] = track[key]
        return result

    def _process_general(self, track) -> None:
        """
        Process general information about a track.

        :param track: track
        :type track: dict
        :return: parsed information
        :rtype: dict
        """
        self.general_track = self._process_generic(track, ['Format', 'File_size', 'Duration', 'Codec_ID'])

    def _process_video(self, track) -> None:
        """
        Process video from a track.

        :param track: track
        :type track: dict
        :return: parsed information and name
        :rtype: dict
        """
        result = self._process_generic(track, ['Display_aspect_ratio', 'Writing_library', 'Duration', 'Codec_ID'])
        # Append non standard ones
        if 'Width' in track and 'Height' in track:
            result['Resolution'] = '{width} x {height}'.format(width=track['Width'], height=track['Height'])

        if 'Format' in track:
            v_format = track['Format']
            if 'Format_Info' in track:
                v_format += ' ({info})'.format(info=track['Format_Info'])
            result['Format'] = v_format

        if 'Frame_rate' in track:
            v_rate = track['Frame_rate']
            if 'Frame_rate_mode' in track:
                v_rate += ' (mode: {mode})'.format(mode=track['Frame_rate_mode'])
            result['Frame rate'] = v_rate

        if 'Scan_type' in track:
            v_scan = track['Scan_type']
            if 'Scan_order' in track:
                v_scan += ' ({order})'.format(order=track['Scan_order'])
            result['Scan type'] = v_scan

        name = 'Stream nr. {number}'.format(number=len(self.video_tracks))
        if 'ID' in track:
            name = 'ID: {number}'.format(number=track['ID'])

        self.video_tracks.append({'name': name, 'value': result})

    def _process_text(self, track) -> None:
        self.caption_tracks.append({
            'name': 'ID: {number}'.format(number=track['ID']),
            'value': self._process_generic(track, ['Format', 'Menu_ID', 'Muxing_mode'])
        })

    @staticmethod
    def generate_media_xml(sample) -> MediaInfoFetcher:
        """
        Generate xml for the sample media.

        :param sample: sample
        :type sample: Model sample
        :raises InvalidMediaInfoError: when system platform is windows
        :raises InvalidMediaInfoError: when not able to generate media info
        :return: fetched media info
        :rtype: instance
        """
        from run import config
        if not sys.platform.startswith("linux"):
            raise InvalidMediaInfoError('Windows generation of MediaInfo unsupported')

        media_folder = os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'TestFiles')
        media_info_path = os.path.join(media_folder, 'media', sample.sha + '.xml')
        output_handle = open(media_info_path, 'w')
        media_path = os.path.join(media_folder, sample.filename)
        process = subprocess.Popen(['mediainfo', '--Output=XML', media_path], stdout=output_handle)
        process.wait()
        if os.path.isfile(media_info_path):
            # Load media info, and replace full pathname
            tree = etree.parse(media_info_path)
            for elem in tree.xpath("//track[@type='General']"):
                for child in elem:
                    if child.tag == 'Complete_name':
                        child.text = child.text.replace(media_folder, '')
                        break
            # Store
            tree.write(media_info_path, encoding='utf-8', xml_declaration=True, pretty_print=True)
            # Return instance
            return MediaInfoFetcher(sample)

        raise InvalidMediaInfoError('Could not generate media info')
