import os
import unittest
from unittest.mock import patch

os.environ.setdefault('TORBOX_API_KEY', 'offline-test-placeholder')
from functions.mediaFunctions import parseMediaName
from functions import torboxFunctions as torbox


def provider(title='Northern Skies'):
    return {'title': title, 'year': 2014, 'link': None, 'image': None, 'backdrop': None}


class ResolutionTests(unittest.TestCase):
    def process(self, name, path, download, search):
        with patch.object(torbox, 'SCAN_METADATA', True), patch.object(torbox, 'search_metadata', side_effect=search), patch.object(torbox, 'insertData'):
            return torbox.process_file({'id': 1, 'name': download, 'hash': 'hash'},
                                      {'id': 2, 'short_name': name, 'name': path, 'mimetype': 'video/x-matroska', 'size': 100}, torbox.DownloadType.torrent)

    def test_arbitrary_series_without_episode_numbers(self):
        results = []
        calls = []
        for name in ['The Beginning.mkv', 'An Unexpected Visitor.mkv']:
            def search(title, year, series):
                calls.append((title, series))
                return provider()
            results.append(self.process(name, 'Northern Skies/Season 2/' + name, 'Collection', search))
        self.assertEqual(calls, [('Northern Skies', True)] * 2)
        self.assertEqual([r['metadata_filename'] for r in results], ['The Beginning.mkv', 'An Unexpected Visitor.mkv'])
        self.assertEqual(results[0]['metadata_foldername'], 'Season 2')
        self.assertEqual(results[0]['metadata_query_source'], 'folder')

    def test_complete_series_context_without_number(self):
        result = self.process('The Unexpected Visitor.mkv', 'The Unexpected Visitor.mkv', 'Harbor Lights The Complete Series', lambda *args: provider('Harbor Lights'))
        self.assertEqual(result['metadata_query'], 'Harbor Lights')
        self.assertEqual(result['metadata_mediatype'], 'series')
        self.assertEqual(result['metadata_filename'], 'The Unexpected Visitor.mkv')

    def test_failed_nearest_folder_tries_download_title(self):
        queries = []
        def search(title, year, series):
            queries.append(title)
            return provider() if title == 'Northern Skies' else None
        result = self.process('Episode 2 The Beginning.mkv', 'Unknown Release/Season 1/Episode 2 The Beginning.mkv', 'Northern Skies', search)
        self.assertEqual(queries, ['Unknown Release', 'Northern Skies'])
        self.assertEqual(result['metadata_query_source'], 'download')

    def test_filename_title_beats_different_folder(self):
        queries = []
        def search(title, *args):
            queries.append(title)
            return provider('Another Show')
        self.process('Another Show S01E02.mkv', 'Folder/Another Show S01E02.mkv', 'Folder', search)
        self.assertEqual(queries, ['Another Show'])

    def test_movie_uses_movie_folder_after_generic_filename(self):
        calls = []
        def search(title, year, series):
            calls.append((title, series))
            return provider('Arrival') if title == 'Arrival' else None
        result = self.process('video.mkv', 'Arrival (2016)/video.mkv', 'Movies', search)
        self.assertEqual(calls, [('video', False), ('Arrival', False)])
        self.assertEqual(result['metadata_query'], 'Arrival')

    def test_candidates_bounded_and_deduplicated(self):
        parsed = parseMediaName('Episode 1.mkv', 'Download', 'A/B/C/D/E/Season 1/Episode 1.mkv')
        self.assertLessEqual(len(parsed['metadata_candidates']), 4)
        parsed = parseMediaName('Episode 1.mkv', 'Northern Skies', 'Northern Skies/Season 1/Episode 1.mkv')
        self.assertEqual([c['title'] for c in parsed['metadata_candidates']], ['Northern Skies'])

    def test_no_provider_match_does_not_invent_metadata(self):
        result = self.process('The Beginning.mkv', 'Northern Skies/Season 2/The Beginning.mkv', 'Collection', lambda *args: None)
        self.assertIsNone(result['metadata_link'])
        self.assertEqual(result['metadata_filename'], 'The Beginning.mkv')
        self.assertEqual(result['metadata_mediatype'], 'series')
