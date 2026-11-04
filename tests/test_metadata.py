import os
import unittest
from unittest.mock import patch

import httpx

os.environ.setdefault('TORBOX_API_KEY', 'offline-test-placeholder')
from library import metadata
from functions import torboxFunctions as torbox


class MetadataTests(unittest.TestCase):
    def setUp(self):
        metadata.lookup.cache_clear()
        self.env = patch.dict(os.environ, {'TMDB_API_KEY': 'tmdb-test', 'METADATA_LANGUAGE': 'pl-PL', 'METADATA_PROVIDERS': 'tmdb'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def client(self, handler):
        real_client = httpx.Client
        return patch.object(metadata.httpx, 'Client', side_effect=lambda **kwargs: real_client(
            **kwargs, transport=httpx.MockTransport(handler)))

    def test_movie_matching_year_auth_and_cache(self):
        requests = []
        def handler(request):
            requests.append(request)
            self.assertEqual(request.url.path, '/3/search/movie')
            self.assertEqual(request.url.params['primary_release_year'], '2021')
            self.assertEqual(request.url.params['api_key'], 'tmdb-test')
            self.assertNotIn('authorization', request.headers)
            return httpx.Response(200, json={'results': [
                {'id': 1, 'title': 'Dune', 'release_date': '1984-12-14'},
                {'id': 2, 'title': 'Diuna', 'original_title': 'Dune', 'release_date': '2021-09-15', 'poster_path': '/poster.jpg'},
            ]})
        with self.client(handler):
            result = metadata.search('Dune', 2021, False)
            self.assertEqual(result['title'], 'Diuna')
            self.assertEqual(result['year'], 2021)
            self.assertEqual(result['image'], 'https://image.tmdb.org/t/p/original/poster.jpg')
            metadata.search('Dune', 2021, False)
        self.assertEqual(len(requests), 1)

    def test_series_premiere_year_and_episode_numbering(self):
        def handler(request):
            self.assertEqual(request.url.path, '/3/search/tv')
            self.assertNotIn('primary_release_year', request.url.params)
            return httpx.Response(200, json={'results': [{'id': 42, 'name': 'Dark', 'first_air_date': '2017-12-01'}]})
        with self.client(handler), patch.object(torbox, 'SCAN_METADATA', True):
            result, success, _ = torbox.searchMetadata('Dark', {'season': 2, 'episode': 3, 'year': 2019}, 'Dark.S02E03.mkv', '', '', 'Dark')
        self.assertTrue(success)
        self.assertEqual(result['metadata_mediatype'], 'series')
        self.assertEqual(result['metadata_rootfoldername'], 'Dark (2017)')
        self.assertEqual(result['metadata_foldername'], 'Season 2')
        self.assertEqual(result['metadata_filename'], 'Dark S02E03.mkv')

    def test_movie_output_and_missing_year(self):
        def handler(request):
            return httpx.Response(200, json={'results': [{'id': 2, 'title': 'Diuna', 'original_title': 'Dune', 'release_date': '2021-09-15'}]})
        with self.client(handler), patch.object(torbox, 'SCAN_METADATA', True):
            result, success, _ = torbox.searchMetadata('Dune', {}, 'Dune.mkv', '', '', 'Dune')
        self.assertTrue(success)
        self.assertEqual(result['metadata_filename'], 'Diuna (2021).mkv')
        self.assertEqual(result['metadata_rootfoldername'], 'Diuna (2021)')
        self.assertEqual(result['metadata_mediatype'], 'movie')

    def test_malformed_json_falls_back(self):
        with self.client(lambda request: httpx.Response(200, text='not json')), patch.object(torbox, 'SCAN_METADATA', True):
            self.assertFalse(torbox.searchMetadata('Dune', {}, 'Dune.mkv', '', '', 'Dune')[1])

    def test_no_match_keeps_series_usable(self):
        with self.client(lambda request: httpx.Response(200, json={'results': []})), patch.object(torbox, 'SCAN_METADATA', True):
            result, success, _ = torbox.searchMetadata('Unknown', {'season': 1, 'episode': 2}, 'Unknown.S01E02.mkv', '', '', 'Unknown')
        self.assertFalse(success)
        self.assertEqual(result['metadata_mediatype'], 'series')
        self.assertEqual(result['metadata_foldername'], 'Season 1')
        self.assertEqual(result['metadata_filename'], 'Unknown.S01E02.mkv')

    def test_unrelated_result_rejected(self):
        with self.client(lambda request: httpx.Response(200, json={'results': [{'id': 1, 'title': 'Something Else', 'release_date': ''}]})):
            self.assertIsNone(metadata.search('Dune', None, False))

    def test_provider_failures_preserve_file(self):
        for status in (401, 429, 500):
            with self.subTest(status=status), self.client(lambda request: httpx.Response(status)), patch.object(torbox, 'SCAN_METADATA', True):
                result, success, _ = torbox.searchMetadata('Dune', {}, 'Dune.mkv', '', '', 'Dune')
                self.assertFalse(success)
                self.assertEqual(result['metadata_rootfoldername'], 'Dune')

    def test_timeout(self):
        def handler(request):
            raise httpx.ReadTimeout('offline timeout', request=request)
        with self.client(handler), patch.object(torbox, 'SCAN_METADATA', True):
            self.assertFalse(torbox.searchMetadata('Dune', {}, 'Dune.mkv', '', '', 'Dune')[1])

    def test_missing_key_no_request(self):
        with patch.dict(os.environ, {'TMDB_API_KEY': ''}), patch.object(metadata.httpx, 'Client') as client:
            self.assertIsNone(metadata.search('Dune', None, False))
            client.assert_not_called()

    def test_disabled_no_lookup(self):
        with patch.object(torbox, 'SCAN_METADATA', False), patch.object(torbox, 'search_metadata') as search:
            self.assertFalse(torbox.searchMetadata('Dune', {}, 'Dune.mkv', '', '', 'Dune')[1])
            search.assert_not_called()


if __name__ == '__main__':
    unittest.main()
