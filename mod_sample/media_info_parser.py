"""Contains classes and methods to parse media info from samples."""
from __future__ import annotations

import collections
import os
import subprocess
import sys
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Type

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

        media_info_path = os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'TestFiles', 'media', sample.sha + '.xml')
        if not os.path.isfile(media_info_path):
            raise InvalidMediaInfoError(f"File {media_info_path} not found")

        with open(media_info_path) as fd:
            try:
                doc = xmltodict.parse(fd.read())
            except Exception:
                raise InvalidMediaInfoError("No Mediainfo root element present")
            if 'MediaInfo' not in doc:
                raise InvalidMediaInfoError("Mediainfo xml root element not present")

            self.media_info = doc['MediaInfo']
            self.video_tracks = []      # type: List
            self.caption_tracks = []    # type: List
            self.audio_tracks = []      # type: List
            self.other_tracks = []      # type: List
            self.general_track = {}     # type: Dict
            self.parsed = False

    def get_media_info(self, force_parse=False) -> Optional[List[Dict[str, Any]]]:
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

        if 'media' not in self.media_info:
            raise InvalidMediaInfoError("No media element present in XML")

        file_info = self.media_info['media']
        if 'track' not in file_info:
            raise InvalidMediaInfoError("No tracks present in XML")

        for track in file_info['track']:
            self._process_track(track)

        self.parsed = True

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
            raise InvalidMediaInfoError("Track file does not contain a type")
        track_type = track['@type']
        if track_type == 'General':
            self._process_general(track)
        elif track_type == 'Video':
            self._process_video(track)
        elif track_type == 'Audio':
            # TODO: Implement at some point
            pass
        elif track_type == 'Text':
            self._process_text(track)

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
        if 'FileSize' in result:
            fileSize = round(float(result['FileSize']) / 1048576, 2)
            result['FileSize'] = f'{fileSize} MB'
        if 'Duration' in result:
            min, sec = divmod(round(float(result['Duration'])), 60)
            result['Duration'] = f'{min}m {sec}s'
        return result

    def _process_general(self, track) -> None:
        """
        Process general information about a track.

        :param track: track
        :type track: dict
        :return: parsed information
        :rtype: dict
        """
        self.general_track = self._process_generic(track, ['Format', 'FileSize', 'Duration', 'CodecID'])

    def _process_video(self, track) -> None:
        """
        Process video from a track.

        :param track: track
        :type track: dict
        :return: parsed information and name
        :rtype: dict
        """
        result = self._process_generic(track, ['DisplayAspectRatio', 'Encoded_Library', 'Duration', 'CodecID'])

        if 'Width' in track and 'Height' in track:
            result['Resolution'] = f"{track['Width']} x {track['Height']}"

        if 'Format' in track:
            result['Format'] = track['Format']

        if 'FrameRate' in track:
            v_rate = track['FrameRate']
            if 'FrameRate_mode' in track:
                v_rate += f" (mode: {track['FrameRate_mode']})"
            result['Frame rate'] = v_rate

        if 'ScanType' in track:
            v_scan = track['ScanType']
            if 'ScanOrder' in track:
                v_scan += f" ({track['ScanOrder']})"
            result['Scan type'] = v_scan

        name = f"Stream nr. {len(self.video_tracks)}"
        if 'ID' in track:
            name = f"ID: {track['ID']}"

        self.video_tracks.append({'name': name, 'value': result})

    def _process_text(self, track) -> None:
        self.caption_tracks.append({
            'name': f"ID: {track['ID']}",
            'value': self._process_generic(track, ['Format', 'MenuID', 'MuxingMode'])
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
            root = tree.getroot()
            try:
                for rootElems in root:
                    if rootElems.tag.split('}')[1] == 'media':
                        rootElems.set("ref", media_path.replace(media_folder, ''))
            except Exception as e:
                raise
            # Store
            tree.write(media_info_path, encoding='utf-8', xml_declaration=True, pretty_print=True)
            # Return instance
            return MediaInfoFetcher(sample)

        raise InvalidMediaInfoError('Could not generate media info')
