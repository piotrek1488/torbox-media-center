import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from library import metadata


class QueryTests(unittest.TestCase):
    def test_bilingual_title_with_middle_year(self):
        self.assertEqual(metadata.query_variants('To 2017 IT', False, 2017), ['To 2017 IT', 'To', 'IT'])
        self.assertIsNone(metadata.translated_title_parts('Blade Runner 2049 Final Cut', 2017))
        self.assertIsNone(metadata.translated_title_parts('2001 A Space Odyssey'))
        self.assertIsNone(metadata.translated_title_parts('Class of 1984'))
        self.assertEqual(metadata.title_similarity('To', 'Tor'), 0)
        self.assertEqual(metadata.title_similarity('IT', 'IT 2'), 0)

    def test_bilingual_query_keeps_year_and_matches_alternate_title(self):
        client = httpx.Client
        calls = []
        def handler(request):
            query = request.url.params['query']
            calls.append(query)
            self.assertEqual(request.url.params['primary_release_year'], '2017')
            results = [{'id': 346364, 'title': 'To', 'original_title': 'It', 'release_date': '2017-09-06'}] if query == 'IT' else []
            return httpx.Response(200, json={'results': results})
        metadata.lookup.cache_clear()
        with patch.dict(os.environ, {'METADATA_PROVIDERS': 'tmdb', 'TMDB_API_KEY': 'test'}), patch.object(metadata.httpx, 'Client', side_effect=lambda **kwargs: client(**kwargs, transport=httpx.MockTransport(handler))):
            result = metadata.search('To 2017 IT', None, False)
        self.assertEqual(result['title'], 'To')
        self.assertEqual(result['year'], 2017)
        self.assertEqual(calls, ['To 2017 IT', 'To', 'IT'])

    def test_actual_yattodetaman_filename(self):
        from functions.mediaFunctions import parseMediaName
        result = parseMediaName('Yattodetaman.1981-1982.S01E01.PL.1080p.WEB-DL.H264-SLH.mkv')
        self.assertEqual(result['title'], 'Yattodetaman')
        self.assertEqual(result['year'], 1981)
        self.assertEqual(result['season'], 1)
        self.assertEqual(result['episode'], 1)

    def test_repeated_no_match_warning_is_suppressed(self):
        from functions.torboxFunctions import warn_no_match
        warn_no_match.cache_clear()
        with self.assertLogs(level='WARNING') as logs:
            warn_no_match('Yattodetaman', 1981, True)
            warn_no_match('Yattodetaman', 1981, True)
        self.assertEqual(len(logs.records), 1)
        warn_no_match.cache_clear()

    def test_year_suffix_and_part_variants(self):
        self.assertEqual(metadata.query_variants('Yattodetaman 1981', True, 1981), ['Yattodetaman 1981', 'Yattodetaman'])
        self.assertIn('Batman Długie Halloween część 2', metadata.query_variants('Batman Długie Halloween cz.2', False))
        self.assertEqual(metadata.query_variants('2001', False, 2001), ['2001'])
        self.assertEqual(metadata.query_variants('Blade Runner 2049', False, 2017), ['Blade Runner 2049'])

    def test_polish_letters_parts_and_wrong_sequel(self):
        self.assertEqual(metadata.normalized('Długie'), metadata.normalized('Dlugie'))
        self.assertEqual(metadata.title_similarity('Batman Długie Halloween cz.2', 'Batman: Długie Halloween, część II'), 1)
        self.assertEqual(metadata.title_similarity('Batman Długie Halloween cz.2', 'Batman: Długie Halloween, część 1'), 0)
        self.assertEqual(metadata.title_similarity('Batman Długie Halloween cz.2', 'Batman: Długie Halloween'), 0)

    def test_yattodetaman_query_retry(self):
        metadata.lookup_kitsu.cache_clear()
        client = httpx.Client
        queries = []
        def handler(request):
            query = request.url.params['filter[text]']
            queries.append(query)
            return httpx.Response(200, json={'data': [] if query.endswith('1981') else [{
                'id': 'test', 'attributes': {'canonicalTitle': 'Yattodetaman', 'subtype': 'TV', 'startDate': '1981-02-07'}
            }]})
        with patch.dict(os.environ, {'METADATA_PROVIDERS': 'kitsu'}), patch.object(metadata.httpx, 'Client', side_effect=lambda **kwargs: client(**kwargs, transport=httpx.MockTransport(handler))):
            result = metadata.search('Yattodetaman 1981', 1981, True)
        self.assertEqual(queries, ['Yattodetaman 1981', 'Yattodetaman'])
        self.assertEqual(result['title'], 'Yattodetaman')

    def test_shipped_aliases_requery_provider_not_fabricated_metadata(self):
        path = Path(__file__).resolve().parents[1] / 'assets/metadata-aliases.json'
        entries = json.loads(path.read_text())
        for query, alias in entries.items():
            with self.subTest(query=query), patch.object(metadata, 'search_providers', side_effect=[None, {'title': 'provider result'}]) as provider:
                result = metadata.search(query, None, False)
                self.assertEqual(result['title'], 'provider result')
                self.assertEqual(provider.call_args.args, (alias['query'], alias['year'], False))

    def test_alias_conflicting_year_or_type_rejected(self):
        with patch.object(metadata, 'search_providers', return_value=None) as provider:
            self.assertIsNone(metadata.search('Batman Długie Halloween cz.2', 1999, False))
            self.assertIsNone(metadata.search('Batman Długie Halloween cz.2', None, True))
            self.assertEqual(provider.call_count, 2)

    def test_missing_alias_does_not_guess_generic_folder(self):
        with patch.object(metadata, 'search_providers', return_value=None) as provider:
            self.assertIsNone(metadata.search('ciekawe filmy seriale', None, False))
            provider.assert_called_once()

    def test_broken_custom_alias_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'aliases.json'
            path.write_text('bad json')
            with patch.dict(os.environ, {'METADATA_ALIASES_FILE': str(path)}), patch.object(metadata, 'search_providers', return_value=None):
                self.assertIsNone(metadata.search('test', None, False))
