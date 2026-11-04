import json
import os
import unittest
from unittest.mock import patch

import httpx
from library import metadata


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        metadata.lookup.cache_clear()
        metadata.warn_missing_key.cache_clear()

    def client(self, handler):
        client = httpx.Client
        return patch.object(metadata.httpx, 'Client', side_effect=lambda **kwargs: client(**kwargs, transport=httpx.MockTransport(handler)))

    def test_zootopia_original_title_matches_localized_tmdb_result(self):
        def handler(request):
            self.assertEqual(request.url.params['query'], 'Zootopia 2')
            self.assertEqual(request.url.path, '/3/search/movie')
            return httpx.Response(200, json={'results': [{'id': 1084242, 'title': 'Zwierzogród 2', 'original_title': 'Zootopia 2', 'release_date': '2025-11-26'}]})
        with patch.dict(os.environ, {'METADATA_PROVIDERS': 'tmdb', 'TMDB_API_KEY': 'secret-fixture'}), self.client(handler), metadata.capture_diagnostics() as events:
            result = metadata.search('Zootopia 2', 2025, False)
        self.assertEqual(result['title'], 'Zwierzogród 2')
        self.assertEqual(events[-1]['status'], 'matched')
        self.assertNotIn('secret-fixture', json.dumps(events))

    def test_missing_key_distinguished_from_zero_results(self):
        with patch.dict(os.environ, {'METADATA_PROVIDERS': 'tmdb', 'TMDB_API_KEY': ''}), metadata.capture_diagnostics() as events:
            self.assertIsNone(metadata.search('Zootopia 2', None, False))
        self.assertEqual(events[0]['status'], 'skipped_missing_key')

    def test_http_error_status_without_secret_url(self):
        with patch.dict(os.environ, {'METADATA_PROVIDERS': 'tmdb', 'TMDB_API_KEY': 'secret-fixture'}), self.client(lambda request: httpx.Response(401)), metadata.capture_diagnostics() as events, self.assertLogs(level='WARNING') as logs:
            metadata.search('Zootopia 2', None, False)
        self.assertEqual(events[0]['http_status'], 401)
        self.assertNotIn('secret-fixture', json.dumps(events) + str(logs.output))

    def test_rejected_year_visible(self):
        with patch.dict(os.environ, {'METADATA_PROVIDERS': 'tmdb', 'TMDB_API_KEY': 'secret-fixture'}), self.client(lambda request: httpx.Response(200, json={'results': [{'id': 1, 'title': 'Zootopia 2', 'release_date': '2025-11-26'}]})), metadata.capture_diagnostics() as events:
            self.assertIsNone(metadata.search('Zootopia 2', 2026, False))
        candidate = next(event for event in events if event['status'] == 'candidate')
        self.assertEqual(candidate['year'], 2025)
        self.assertFalse(candidate['accepted'])
