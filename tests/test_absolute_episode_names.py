import os
import unittest
from unittest.mock import patch

os.environ.setdefault('TORBOX_API_KEY', 'offline-test-placeholder')
from functions.mediaFunctions import parseMediaName
from functions import torboxFunctions as torbox


class AbsoluteEpisodeNamesTests(unittest.TestCase):
    def test_trailing_punctuation_and_release_tags(self):
        for name in [
            'Naruto - 137..mkv', 'Naruto - 137. [1080p].mkv',
            'Naruto - 137.1080p.mkv', '[Group] Naruto - 137. [DVD].mkv',
            'Naruto - 137.', 'Naruto - 137.avi',
            'Another Show – 137. [720p].mkv', 'Another Show — 137v2. [1080p].mkv',
        ]:
            with self.subTest(name=name):
                parsed = parseMediaName(name)
                self.assertEqual(parsed['title'], 'Naruto' if 'Naruto' in name else 'Another Show')
                self.assertEqual(parsed['episode'], 137)
                self.assertEqual(parsed['metadata_candidates'][0]['title'], parsed['title'])

    def test_film_year_suffix_not_episode(self):
        self.assertIsNone(parseMediaName('Some Movie - 2025.mkv').get('episode'))

    def test_fractional_episode_not_silently_truncated(self):
        self.assertNotEqual(parseMediaName('Another Show - 137.5.mkv').get('episode'), 137)

    def test_process_file_queries_series_without_episode_suffix(self):
        name = 'Naruto - 137. [1080p].mkv'
        data = {'title': 'Naruto', 'year': 2002, 'link': None, 'image': None, 'backdrop': None}
        with patch.object(torbox, 'SCAN_METADATA', True), patch.object(torbox, 'search_metadata', return_value=data) as search, patch.object(torbox, 'insertData'):
            result = torbox.process_file({'id': 1, 'name': 'Anime', 'hash': 'hash'},
                                        {'id': 2, 'short_name': name, 'name': name, 'mimetype': 'video/x-matroska', 'size': 100}, torbox.DownloadType.torrent)
        self.assertEqual(search.call_args.args, ('Naruto', None, True))
        self.assertEqual(result['metadata_episode'], 137)
        self.assertEqual(result['metadata_filename'], 'Naruto E137.mkv')
