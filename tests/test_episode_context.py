import os
import unittest
from unittest.mock import patch

os.environ.setdefault('TORBOX_API_KEY', 'offline-test-placeholder')
from functions.mediaFunctions import parseMediaName
from functions import torboxFunctions as torbox


class EpisodeContextTests(unittest.TestCase):
    def test_actual_complete_series_path(self):
        parent = 'Dragon Ball Z Kai The Complete Series (2009–2015)'
        name = 'Episode 121 I am the Strongest! The Clash of Goku vs. Vegeta.mkv'
        parsed = parseMediaName(name, parent, parent + '/' + name)
        self.assertEqual(parsed['title'], 'Dragon Ball Z Kai')
        self.assertEqual(parsed['year'], 2009)
        self.assertEqual(parsed['episode'], 121)
        data = {'title': 'Dragon Ball Z Kai', 'year': 2009, 'link': None, 'image': None, 'backdrop': None}
        with patch.object(torbox, 'SCAN_METADATA', True), patch.object(torbox, 'search_metadata', return_value=data) as search, patch.object(torbox, 'insertData'):
            result = torbox.process_file(
                {'id': 1, 'name': parent, 'hash': 'hash'},
                {'id': 2, 'name': parent + '/' + name, 'short_name': name, 'mimetype': 'video/x-matroska', 'size': 100},
                torbox.DownloadType.torrent)
        self.assertEqual(search.call_args.args, ('Dragon Ball Z Kai', 2009, True))
        self.assertEqual(result['metadata_filename'], 'Dragon Ball Z Kai E121.mkv')

    def test_episode_prefix_uses_series_folder(self):
        name = 'Episode 121 I am the Strongest! The Clash of Goku vs. Vegeta.mkv'
        result = parseMediaName(name, 'Anime collection', f'Dragon Ball Kai/Season 1/{name}')
        self.assertEqual(result['title'], 'Dragon Ball Kai')
        self.assertEqual(result['episode'], 121)
        self.assertTrue(result['absolute_episode'])

    def test_leading_season_episode_and_numeric_names(self):
        for name in ['S01E02 - Episode title.mkv', '002 - Episode title.mkv', 'Odcinek 2 Episode title.mkv']:
            with self.subTest(name=name):
                result = parseMediaName(name, 'Dragon Ball Kai')
                self.assertEqual(result['title'], 'Dragon Ball Kai')
                self.assertEqual(result['episode'], 2)

    def test_named_series_in_filename_remains_authoritative(self):
        result = parseMediaName('Dragon Ball Kai S01E02.mkv', 'Different show', 'Other folder/Dragon Ball Kai S01E02.mkv')
        self.assertEqual(result['title'], 'Dragon Ball Kai')

    def test_movie_does_not_use_collection_folder(self):
        result = parseMediaName('Batman Długie Halloween cz.2.mkv', 'ciekawe filmy seriale')
        self.assertEqual(result['title'], 'Batman Długie Halloween cz.2')

    def test_episode_without_series_context_is_not_guessed(self):
        name = 'Episode 121 I am the Strongest.mkv'
        result = parseMediaName(name)
        self.assertEqual(result['episode'], 121)
        self.assertNotEqual(result['title'], 'Dragon Ball Kai')

    def test_process_file_uses_full_torbox_path(self):
        name = 'Episode 121 I am the Strongest.mkv'
        data = {'title': 'Dragon Ball Kai', 'year': 2009, 'link': None, 'image': None, 'backdrop': None}
        with patch.object(torbox, 'SCAN_METADATA', True), patch.object(torbox, 'search_metadata', return_value=data) as search, patch.object(torbox, 'insertData'):
            result = torbox.process_file(
                {'id': 1, 'name': 'Anime collection', 'hash': 'hash'},
                {'id': 2, 'name': f'Dragon Ball Kai/Season 1/{name}', 'short_name': name, 'mimetype': 'video/x-matroska', 'size': 100},
                torbox.DownloadType.torrent)
        self.assertEqual(search.call_args.args, ('Dragon Ball Kai', None, True))
        self.assertEqual(result['metadata_filename'], 'Dragon Ball Kai E121.mkv')
        self.assertEqual(result['metadata_mediatype'], 'series')
