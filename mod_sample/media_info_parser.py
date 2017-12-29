import os
import traceback

import sys
from collections import OrderedDict

from lxml import etree
import subprocess
import xmltodict


class InvalidMediaInfoError(Exception):
    def __init__(self, message):
        Exception.__init__(self)
        self.message = message


class MediaInfoFetcher:
    def __init__(self, sample):
        from run import config
        # Fetch media info
        media_info_path = os.path.join(
            config.get('SAMPLE_REPOSITORY', ''), 'TestFiles', 'media',
            sample.sha + '.xml')
        if os.path.isfile(media_info_path):
            with open(media_info_path) as fd:
                try:
                    doc = xmltodict.parse(fd.read())
                except Exception:
                # Show error if Mediainfo can't be open
                    raise InvalidMediaInfoError(
                        'No Mediainfo root element present')
                if 'Mediainfo' in doc:
                    self.media_info = doc['Mediainfo']
                    self.video_tracks = []
                    self.caption_tracks = []
                    self.audio_tracks = []
                    self.other_tracks = []
                    self.general_track = {}
                    self.parsed = False
                else:
                # Throw error if there is no Mediainfo in doc
                    raise InvalidMediaInfoError(
                        'No Mediainfo root element present')
        else:
            raise InvalidMediaInfoError(
                'File {path} not found'.format(path=media_info_path))

    def get_media_info(self, force_parse=False):
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

    def _process_tracks(self):
        # Reset stored tracks
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

    def _process_track(self, track):
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

    def _process_generic(self, track, keys):
        result = {}
        # Values we could use, but they're not always present
        for key in keys:
            if key in track:
                result[key.replace('_', ' ')] = track[key]
        return result

    def _process_general(self, track):
        self.general_track = self._process_generic(
            track, ['Format', 'File_size', 'Duration', 'Codec_ID']
        )

    def _process_video(self, track):
        result = self._process_generic(
            track, ['Display_aspect_ratio', 'Writing_library', 'Duration',
                    'Codec_ID'])
        # Append non standard ones
        if 'Width' in track and 'Height' in track:
            result['Resolution'] = '{width} x {height}'.format(
                width=track['Width'],
                height=track['Height'])

        if 'Format' in track:
            v_format = track['Format']
            if 'Format_Info' in track:
                v_format += ' ({info})'.format(info=track['Format_Info'])
            result['Format'] = v_format

        if 'Frame_rate' in track:
            v_rate = track['Frame_rate']
            if 'Frame_rate_mode' in track:
                v_rate += ' (mode: {mode})'.format(
                    mode=track['Frame_rate_mode'])
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

    def _process_text(self, track):
        self.caption_tracks.append({
            'name': 'ID: {number}'.format(number=track['ID']),
            'value': self._process_generic(
                track, ['Format', 'Menu_ID', 'Muxing_mode'])
        })

    @staticmethod
    def generate_media_xml(sample):
        from run import config
        if not sys.platform.startswith("linux"):
            raise InvalidMediaInfoError('Windows generation of MediaInfo '
                                        'unsupported')
        media_folder = os.path.join(
            config.get('SAMPLE_REPOSITORY', ''), 'TestFiles')
        media_info_path = os.path.join(
            media_folder, 'media', sample.sha + '.xml')
        output_handle = open(media_info_path, 'w')
        media_path = os.path.join(media_folder, sample.filename)
        process = subprocess.Popen(
            ['mediainfo', '--Output=XML', media_path], stdout=output_handle)
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
            tree.write(media_info_path, encoding='utf-8',
                       xml_declaration=True, pretty_print=True)
            # Return instance
            return MediaInfoFetcher(sample)
        raise InvalidMediaInfoError('Could not generate media info')
