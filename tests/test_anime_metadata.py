import os
import unittest
from unittest.mock import patch

import httpx

os.environ.setdefault('TORBOX_API_KEY', 'offline-test-placeholder')
from library import metadata
from functions.mediaFunctions import constructSeriesTitle, parseMediaName
from functions import torboxFunctions as torbox


class AnimeTests(unittest.TestCase):
    filename = '[Grupa Mirai] Dragon Ball - 118 [v2] [DVD 720x540 AC3] [4F4E90E0].mkv'

    def setUp(self):
        metadata.lookup_kitsu.cache_clear()
        metadata.lookup_tvdb.cache_clear()
        metadata.tvdb_token.cache_clear()
        self.env = patch.dict(os.environ, {'METADATA_PROVIDERS': 'tmdb,tvdb,kitsu', 'TMDB_API_KEY': '', 'TVDB_API_KEY': '', 'TVDB_PIN': ''})
        self.env.start()
        self.addCleanup(self.env.stop)

    def client(self, handler):
        client = httpx.Client
        return patch.object(metadata.httpx, 'Client', side_effect=lambda **kwargs: client(
            **kwargs, transport=httpx.MockTransport(handler)))

    def test_empty_numbers_and_ranges(self):
        self.assertIsNone(constructSeriesTitle([], []))
        self.assertEqual(constructSeriesTitle(1, []), 'S01')
        self.assertEqual(constructSeriesTitle([1], [118]), 'S01E118')
        self.assertEqual(constructSeriesTitle(0, [1, 2]), 'S00E01-E02')
        self.assertIsNone(constructSeriesTitle(episode=['invalid']))

    def test_real_anime_filename(self):
        result = parseMediaName(self.filename)
        self.assertEqual(result['title'], 'Dragon Ball')
        self.assertEqual(result['episode'], 118)
        self.assertTrue(result['absolute_episode'])
        other = parseMediaName('[SubsPlease] Frieren - 12 (1080p).mkv')
        self.assertEqual(other['episode'], 12)

    def test_numbered_movie_query_fallback_and_polish_subtitle(self):
        title = 'Dragon Ball Z Movie 13 - Eksplozja Smoczej Pięści!! Jeśli nie Goku, to kto'
        calls = []
        def handler(request):
            query = request.url.params['filter[text]']
            calls.append(query)
            results = [] if query == title else [
                {'id': '12', 'attributes': {'canonicalTitle': 'Dragon Ball Z Movie 12: Fukkatsu no Fusion', 'subtype': 'movie', 'startDate': '1995-03-04'}},
                {'id': '13', 'attributes': {'canonicalTitle': 'Dragon Ball Z Movie 13: Ryuuken Bakuhatsu!! Gokuu ga Yaraneba Dare ga Yaru', 'titles': {'en': 'Dragon Ball Z: Wrath of the Dragon'}, 'subtype': 'movie', 'startDate': '1995-07-15'}},
            ]
            return httpx.Response(200, json={'data': results})
        with self.client(handler), patch.dict(os.environ, {'METADATA_PROVIDERS': 'kitsu'}), patch.object(torbox, 'SCAN_METADATA', True):
            result, success, _ = torbox.searchMetadata(title, {}, title + '.mkv', '', '', 'Dragon Ball Z S01')
        self.assertTrue(success)
        self.assertEqual(calls, [title, 'Dragon Ball Z Movie 13'])
        self.assertEqual(result['metadata_mediatype'], 'movie')
        self.assertEqual(result['metadata_years'], 1995)
        self.assertIn('Movie 13', result['metadata_title'])
        self.assertNotIn('metadata_foldername', result)
        self.assertIsNone(result['metadata_season'])

    def test_numbered_movie_never_accepts_different_number_or_franchise(self):
        self.assertEqual(metadata.title_similarity('Dragon Ball Z Movie 13', 'Dragon Ball Z Movie 12'), 0)
        self.assertEqual(metadata.title_similarity('Dragon Ball Z Movie 13', 'Dragon Ball Movie 13'), 0)
        self.assertEqual(metadata.query_variants('Dragon Ball Z Movie 13 - Polish subtitle', True), ['Dragon Ball Z Movie 13 - Polish subtitle'])

    def test_absolute_episode_overrides_pack_range(self):
        result = parseMediaName(self.filename, 'Dragon Ball - 001-153')
        self.assertEqual(result['episode'], 118)

    def test_process_file_regression(self):
        provider = {'title': 'Dragon Ball', 'year': 1986, 'provider': 'kitsu',
                    'link': None, 'image': None, 'backdrop': None}
        with patch.object(torbox, 'SCAN_METADATA', True), patch.object(torbox, 'search_metadata', return_value=provider), patch.object(torbox, 'insertData') as insert:
            result = torbox.process_file(
                {'id': 1, 'name': 'Dragon Ball - 001-153', 'hash': 'test'},
                {'id': 2, 'short_name': self.filename, 'name': self.filename,
                 'size': 100, 'mimetype': 'video/x-matroska'}, torbox.DownloadType.torrent)
        self.assertEqual(result['metadata_filename'], 'Dragon Ball E118.mkv')
        self.assertEqual(result['metadata_episode'], 118)
        insert.assert_called_once()

    def test_kitsu_alias_and_complete_metadata_path(self):
        calls = []
        def handler(request):
            calls.append(request)
            self.assertEqual(request.url.params['filter[text]'], 'Dragon Ball')
            self.assertNotIn('authorization', request.headers)
            return httpx.Response(200, json={'data': [{'id': '1', 'attributes': {
                'canonicalTitle': 'Dragon Ball', 'titles': {'ja_jp': 'ドラゴンボール'},
                'subtype': 'TV', 'startDate': '1986-02-26', 'slug': 'dragon-ball',
                'posterImage': {'original': 'https://example.test/poster.jpg'},
            }}]})
        with self.client(handler), patch.object(torbox, 'SCAN_METADATA', True):
            parsed = parseMediaName(self.filename)
            result, success, _ = torbox.searchMetadata('Dragon Ball', parsed, self.filename, '', '', 'Dragon Ball')
            metadata.search('Dragon Ball', None, True)
        self.assertTrue(success)
        self.assertEqual(result['metadata_provider'], 'kitsu')
        self.assertEqual(result['metadata_years'], 1986)
        self.assertEqual(result['metadata_filename'], 'Dragon Ball E118.mkv')
        self.assertEqual(result['metadata_foldername'], 'Season 1')
        self.assertEqual(len(calls), 1)

    def test_tmdb_failure_falls_through_tvdb_to_kitsu(self):
        result = {'title': 'Dragon Ball', 'year': 1986}
        with patch.dict(os.environ, {'TMDB_API_KEY': 'test', 'TVDB_API_KEY': 'test'}), patch.object(metadata, 'lookup', side_effect=httpx.ReadTimeout('timeout')), patch.object(metadata, 'lookup_tvdb', return_value=None) as tvdb, patch.object(metadata, 'lookup_kitsu', return_value=result) as kitsu:
            self.assertEqual(metadata.search('Dragon Ball', None, True)['provider'], 'kitsu')
            tvdb.assert_called_once()
            kitsu.assert_called_once()

    def test_provider_order_and_short_circuit(self):
        with patch.dict(os.environ, {'METADATA_PROVIDERS': 'kitsu,tmdb', 'TMDB_API_KEY': 'test'}), patch.object(metadata, 'lookup_kitsu', return_value={'title': 'Dragon Ball'}) as kitsu, patch.object(metadata, 'lookup') as tmdb:
            self.assertEqual(metadata.search('Dragon Ball', None, True)['provider'], 'kitsu')
            tmdb.assert_not_called()

    def test_kitsu_rejects_wrong_type_and_title(self):
        with self.client(lambda request: httpx.Response(200, json={'data': [
            {'id': '1', 'attributes': {'canonicalTitle': 'Dragon Ball', 'subtype': 'movie'}},
            {'id': '2', 'attributes': {'canonicalTitle': 'Unrelated Anime', 'subtype': 'TV'}},
        ]})):
            self.assertIsNone(metadata.search('Dragon Ball', None, True))

    def test_tvdb_login_alias_translation_and_cache(self):
        calls = []
        def handler(request):
            calls.append(request)
            if request.url.path.endswith('/login'):
                self.assertEqual(request.method, 'POST')
                self.assertIn(b'"apikey":"test"', request.content)
                self.assertNotIn(b'"pin"', request.content)
                return httpx.Response(200, json={'data': {'token': 'test-token'}})
            self.assertEqual(request.headers['authorization'], 'Bearer test-token')
            return httpx.Response(200, json={'data': [{'type': 'series', 'name': 'Dragon Ball', 'aliases': ['Doragon Boru'], 'translations': {'pol': 'Dragon Ball'}, 'year': '1986', 'slug': 'dragon-ball'}]})
        with self.client(handler), patch.dict(os.environ, {'METADATA_PROVIDERS': 'tvdb', 'TVDB_API_KEY': 'test'}):
            result = metadata.search('Doragon Boru', None, True)
            self.assertEqual(result['provider'], 'tvdb')
            self.assertEqual(result['year'], 1986)
            metadata.search('Doragon Boru', None, True)
        self.assertEqual(len(calls), 2)

    def test_all_providers_unavailable_keep_filename(self):
        with self.client(lambda request: httpx.Response(503)), patch.object(torbox, 'SCAN_METADATA', True):
            result, success, _ = torbox.searchMetadata('Dragon Ball', {'episode': []}, self.filename, '', '', 'Dragon Ball')
        self.assertFalse(success)
        self.assertEqual(result['metadata_episode'], 118)
        self.assertEqual(result['metadata_filename'], self.filename)


if __name__ == '__main__':
    unittest.main()
