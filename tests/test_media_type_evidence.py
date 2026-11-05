import os
import unittest
from unittest.mock import patch

os.environ.setdefault('TORBOX_API_KEY', 'offline-test-placeholder')
from functions.mediaFunctions import parseMediaName, metadataMediaTypes
from functions import torboxFunctions as torbox


class MediaTypeEvidenceTests(unittest.TestCase):
    def test_year_in_filename_precedes_folder_type(self):
        parsed = parseMediaName('Zootopia.2.2025.mkv', '9061af8', 'Season 1/Zootopia.2.2025.mkv')
        self.assertEqual(metadataMediaTypes(parsed), ['movie', 'series'])
        self.assertNotIn('9061af8', [c['title'] for c in parsed['metadata_candidates']])

    def test_technical_identifiers_are_not_series_evidence(self):
        for name in ['9061af8', '01234e56', 'ab12e034ff', 'abcdef0123456789']:
            parsed = parseMediaName('Zootopia.2.2025.mkv', name, name + '/Zootopia.2.2025.mkv')
            self.assertEqual(metadataMediaTypes(parsed), ['movie'])
            self.assertEqual(len(parsed['metadata_candidates']), 1)

    def test_explicit_episode_stays_series_even_with_year(self):
        parsed = parseMediaName('Some.Show.2025.S01E02.mkv', '9061af8')
        self.assertEqual(metadataMediaTypes(parsed), ['series'])

    def test_main_workflow_uses_movie_endpoint_and_output_type(self):
        name = 'Zootopia.2.2025.mkv'
        parsed = parseMediaName(name, '9061af8', 'Season 1/' + name)
        calls = []
        def search(title, year, series):
            calls.append((title, year, series))
            return {'title': 'Zwierzogród 2', 'year': 2025, 'link': None, 'image': None, 'backdrop': None}
        with patch.object(torbox, 'SCAN_METADATA', True), patch.object(torbox, 'search_metadata', side_effect=search):
            result, success, _ = torbox.searchMetadata('Zootopia 2', parsed, name, '', '', '9061af8')
        self.assertTrue(success)
        self.assertEqual(calls[0], ('Zootopia 2', 2025, False))
        self.assertEqual(result['metadata_mediatype'], 'movie')
        self.assertIsNone(result['metadata_season'])
        self.assertNotIn('metadata_foldername', result)
        self.assertEqual(result['metadata_filename'], 'Zwierzogród 2 (2025).mkv')

    def test_contextual_series_fallback_still_supported(self):
        name = 'The Beginning 2014.mkv'
        parsed = parseMediaName(name, 'Northern Skies The Complete Series')
        def search(title, year, series):
            return {'title': 'Northern Skies', 'year': 2014, 'link': None, 'image': None, 'backdrop': None} if series else None
        with patch.object(torbox, 'SCAN_METADATA', True), patch.object(torbox, 'search_metadata', side_effect=search):
            result, success, _ = torbox.searchMetadata('The Beginning', parsed, name, '', '', 'Northern Skies The Complete Series')
        self.assertTrue(success)
        self.assertEqual(result['metadata_mediatype'], 'series')
        self.assertEqual(result['metadata_filename'], name)
