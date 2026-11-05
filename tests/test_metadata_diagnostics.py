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

    def test_main_workflow_failure_exposes_actual_type_year_and_status(self):
        os.environ.setdefault('TORBOX_API_KEY', 'torbox-fixture')
        from functions import torboxFunctions as torbox
        torbox.warn_no_match.cache_clear()
        with patch.dict(os.environ, {'METADATA_PROVIDERS': 'tmdb', 'TMDB_API_KEY': 'secret-fixture'}), self.client(lambda request: httpx.Response(401)), patch.object(torbox, 'SCAN_METADATA', True), self.assertLogs(level='WARNING') as logs:
            result, success, _ = torbox.searchMetadata('Zootopia 2', {}, 'Zootopia.2.2025.mkv', '', '', 'Zootopia 2')
        self.assertFalse(success)
        text = '\n'.join(logs.output)
        self.assertIn('type=movie year=2025', text)
        self.assertIn('"http_status": 401', text)
        self.assertIn('"attempts"', text)
        self.assertNotIn('secret-fixture', text)

    def test_failure_summary_whitelists_provider_fields(self):
        from functions.torboxFunctions import failure_details
        text = failure_details([], [{'provider': 'tmdb', 'status': 'error', 'http_status': 401, 'url': 'https://api.example/?api_key=secret-fixture', 'headers': {'Authorization': 'secret-fixture'}}])
        self.assertNotIn('secret-fixture', text)
        self.assertIn('401', text)

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

    def test_real_zootopia_release_names_query_normalization(self):
        from functions.mediaFunctions import parseMediaName
        names = [
            '[DEVIL-TORRENTS.PL] Zootopia.2.2025.PLDUB.MULTi.2160p.iT.WEB-DL.DDP5.1.Atmos.DV.HDR.H.265-P2P',
            '[XTORRENTY.ORG] Zootopia.2.2025.MULTi.2160p.AMZN.WEB-DL.HDR.H.265.DD5.1-RX',
        ]
        for name in names:
            with self.subTest(name=name):
                metadata.lookup.cache_clear()
                parsed = parseMediaName(name + '.mkv', name)
                candidate = parsed['metadata_candidates'][0]
                self.assertEqual(candidate['year'], 2025)
                self.assertIsNone(parsed.get('season'))
                queries = []
                def handler(request):
                    query = request.url.params['query']
                    queries.append(query)
                    self.assertEqual(request.url.params['primary_release_year'], '2025')
                    results = [{'id': 1084242, 'title': 'Zwierzogród 2', 'original_title': 'Zootopia 2', 'release_date': '2025-11-26'}] if query == 'Zootopia 2' else []
                    return httpx.Response(200, json={'results': results})
                with patch.dict(os.environ, {'METADATA_PROVIDERS': 'tmdb', 'TMDB_API_KEY': 'secret-fixture'}), self.client(handler):
                    result = metadata.search(candidate['title'], candidate['year'], False)
                self.assertEqual(result['title'], 'Zwierzogród 2')
                self.assertIn('Zootopia 2', queries)

    def test_generic_release_separators_keep_literal_title(self):
        self.assertEqual(metadata.query_variants('Some.Other_Title.', False), ['Some.Other_Title.', 'Some Other Title'])
        self.assertEqual(metadata.query_variants('Dr. Strangelove', False)[0], 'Dr. Strangelove')

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
