"""Ordered TMDB, TVDB and Kitsu lookups with separate provider credentials."""
from contextvars import ContextVar
from contextlib import contextmanager
from difflib import SequenceMatcher
from functools import lru_cache
import os
import json
from pathlib import Path
import re
import unicodedata

import httpx


_diagnostics = ContextVar('metadata_diagnostics', default=None)


@contextmanager
def capture_diagnostics():
    events = []
    token = _diagnostics.set(events)
    try:
        yield events
    finally:
        _diagnostics.reset(token)


def record(provider, status, **details):
    events = _diagnostics.get()
    if events is not None:
        events.append({'provider': provider, 'status': status, **details})


@lru_cache(maxsize=16)
def warn_missing_key(provider, variable):
    import logging
    logging.warning('Metadata provider %s skipped: %s is missing. Set it in .env/container environment.', provider, variable)


def normalized(title):
    title = unicodedata.normalize('NFKD', title).casefold().replace('ł', 'l')
    title = re.sub(r'[^\w]+', ' ', ''.join(c for c in title if not unicodedata.combining(c))).strip()
    # Localized part markers carry identity: part 1 must never match part 2.
    numbers = {'one': '1', 'two': '2', 'first': '1', 'second': '2',
               'pierwsza': '1', 'druga': '2', 'i': '1', 'ii': '2'}
    title = re.sub(r'\b(?:cz|czesc|part)\s*(\d+|one|two|first|second|pierwsza|druga|ii|i)\b',
                   lambda m: 'part ' + numbers.get(m[1], m[1]), title)
    return title


def numbered_movie(title):
    """An explicit franchise + movie number, never an index into search results."""
    match = re.match(r'^(.*?)\s+(?:movie|film)\s*#?\s*(\d+)\b', normalized(title))
    return (match[1], int(match[2])) if match else None


def title_similarity(query, title):
    wanted_part = re.search(r'\bpart (\d+)\b', normalized(query))
    found_part = re.search(r'\bpart (\d+)\b', normalized(title))
    if wanted_part and (not found_part or wanted_part[1] != found_part[1]):
        return 0.0
    wanted, found = numbered_movie(query), numbered_movie(title)
    if wanted and found:
        return 1.0 if wanted == found else 0.0
    return SequenceMatcher(None, normalized(query), normalized(title)).ratio()


def query_variants(query, is_series, year=None):
    variants = [query]
    if not is_series:
        match = re.match(r'^(.*?\s+(?:movie|film)\s*#?\s*\d+)\b', query, re.IGNORECASE)
        if match and match[1].strip() != query:
            variants.append(match[1].strip())
    if year:
        without_year = re.sub(rf'\s+[([]?{year}[)\]]?$', '', query).strip()
        if without_year and without_year != query:
            variants.append(without_year)
    for variant in list(variants):
        expanded = re.sub(r'\bcz\.?\s*(\d+)\b', r'część \1', variant, flags=re.IGNORECASE)
        if expanded != variant:
            variants.append(expanded)
    return list(dict.fromkeys(variants))


@lru_cache(maxsize=512)
def lookup(query, year, is_series, api_key, language):
    """Cache by series title, never by episode filename; errors are not cached."""
    if not api_key:
        raise ValueError('Set TMDB_API_KEY to enable TMDB metadata.')
    kind = 'tv' if is_series else 'movie'
    params = {'query': query, 'language': language, 'include_adult': 'false', 'api_key': api_key}
    # Episode years can differ from the premiere year of the series.
    if year and not is_series:
        params['primary_release_year'] = year
    with httpx.Client(
        base_url='https://api.themoviedb.org/3/',
        timeout=15,
    ) as client:
        response = client.get(f'search/{kind}', params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get('results'), list):
            raise ValueError('Invalid TMDB search response.')
        results = payload['results']
    record('tmdb', 'response', query=query, year=year, type=kind, results=len(results))
    candidates = []
    for result in results:
        if not isinstance(result, dict) or not result.get('id'):
            continue
        title = result.get('name' if is_series else 'title')
        if not isinstance(title, str) or not title.strip():
            continue
        original = result.get('original_name' if is_series else 'original_title') or title
        score = max(title_similarity(query, name)
                    for name in (title, original))
        date = result.get('first_air_date' if is_series else 'release_date') or ''
        result_year = int(date[:4]) if date[:4].isdigit() else None
        record('tmdb', 'candidate', title=title, original_title=original, year=result_year, score=round(score, 3), accepted=score >= 0.7 and (not year or is_series or result_year == year))
        if year and not is_series and result_year != year:
            continue
        if score >= 0.7:
            candidates.append((score, result, title, result_year))
    if not candidates:
        return None
    _, result, title, result_year = max(candidates, key=lambda candidate: candidate[0])
    image = lambda path: f'https://image.tmdb.org/t/p/original{path}' if path else None
    return {
        'title': title, 'year': result_year, 'type': 'series' if is_series else 'movie',
        'link': f'https://www.themoviedb.org/{kind}/{result["id"]}',
        'image': image(result.get('poster_path')),
        'backdrop': image(result.get('backdrop_path')),
    }


def choose(query, year, is_series, candidates):
    ranked = []
    for candidate, names in candidates:
        if year and not is_series and candidate['year'] != year:
            continue
        scores = [title_similarity(query, name)
                  for name in names if isinstance(name, str) and name.strip()]
        score = max(scores, default=0)
        if score >= 0.8:
            ranked.append((score, candidate))
    return max(ranked, key=lambda pair: pair[0])[1] if ranked else None


def release_year(value):
    text = str(value or '')
    return int(text[:4]) if text[:4].isdigit() else None


@lru_cache(maxsize=512)
def lookup_kitsu(query, year, is_series):
    with httpx.Client(base_url='https://kitsu.io/api/edge/', timeout=15, follow_redirects=True) as client:
        response = client.get('anime', params={'filter[text]': query, 'page[limit]': 20})
        response.raise_for_status()
        results = response.json()['data']
    candidates = []
    for item in results:
        attrs = item.get('attributes') or {}
        subtype = (attrs.get('subtype') or '').lower()
        if (subtype == 'movie') == is_series:
            continue
        title = attrs.get('canonicalTitle')
        if not title:
            continue
        titles = list((attrs.get('titles') or {}).values()) + (attrs.get('abbreviatedTitles') or [])
        candidate = {
            'title': title, 'year': release_year(attrs.get('startDate')),
            'type': 'series' if is_series else 'movie', 'provider': 'kitsu',
            'link': f'https://kitsu.io/anime/{attrs.get("slug") or item["id"]}',
            'image': (attrs.get('posterImage') or {}).get('original'),
            'backdrop': (attrs.get('coverImage') or {}).get('original'),
        }
        candidates.append((candidate, [title, *titles]))
    return choose(query, year, is_series, candidates)


@lru_cache(maxsize=32)
def tvdb_token(api_key, pin, day):
    body = {'apikey': api_key}
    if pin:
        body['pin'] = pin
    with httpx.Client(base_url='https://api4.thetvdb.com/v4/', timeout=15) as client:
        response = client.post('login', json=body)
        response.raise_for_status()
        return response.json()['data']['token']


@lru_cache(maxsize=512)
def lookup_tvdb(query, year, is_series, api_key, pin, language, day):
    token = tvdb_token(api_key, pin, day)
    kind = 'series' if is_series else 'movie'
    params = {'query': query, 'type': kind, 'limit': 20}
    if year and not is_series:
        params['year'] = year
    with httpx.Client(base_url='https://api4.thetvdb.com/v4/', timeout=15,
                      headers={'Authorization': f'Bearer {token}'}) as client:
        response = client.get('search', params=params)
        if response.status_code == 401:
            tvdb_token.cache_clear()
        response.raise_for_status()
        results = response.json()['data']
    # TVDB uses ISO 639-2 language keys for translations.
    lang = {'pl': 'pol', 'en': 'eng', 'ja': 'jpn'}.get(language.split('-')[0])
    candidates = []
    for item in results:
        if item.get('type') != kind:
            continue
        translations = item.get('translations') or {}
        title = translations.get(lang) or item.get('name')
        if not title:
            continue
        slug = item.get('slug')
        candidate = {
            'title': title, 'year': release_year(item.get('year')),
            'type': kind, 'provider': 'tvdb',
            'link': f'https://www.thetvdb.com/{"series" if is_series else "movies"}/{slug}' if slug else None,
            'image': item.get('image_url'), 'backdrop': None,
        }
        candidates.append((candidate, [title, item.get('name'), *(item.get('aliases') or []), *translations.values()]))
    return choose(query, year, is_series, candidates)


def search_providers(query, year, is_series):
    import logging
    import time
    language = os.getenv('METADATA_LANGUAGE', 'pl-PL')
    for variant in query_variants(query, is_series, year):
        for provider in os.getenv('METADATA_PROVIDERS', 'tmdb,tvdb,kitsu').split(','):
            provider = provider.strip().lower()
            try:
                if provider == 'tmdb':
                    key = os.getenv('TMDB_API_KEY', '').strip()
                    if not key:
                        record(provider, 'skipped_missing_key', variable='TMDB_API_KEY')
                        warn_missing_key(provider, 'TMDB_API_KEY')
                        continue
                    result = lookup(variant, year, is_series, key, language)
                elif provider == 'tvdb':
                    key = os.getenv('TVDB_API_KEY', '').strip()
                    if not key:
                        record(provider, 'skipped_missing_key', variable='TVDB_API_KEY')
                        warn_missing_key(provider, 'TVDB_API_KEY')
                        continue
                    result = lookup_tvdb(variant, year, is_series, key,
                                         os.getenv('TVDB_PIN', '').strip(), language, int(time.time() // 86400))
                elif provider == 'kitsu':
                    result = lookup_kitsu(variant, year, is_series)
                else:
                    logging.warning('Unknown metadata provider: %s', provider)
                    continue
                record(provider, 'matched' if result else 'no_match', query=variant, year=year, type='series' if is_series else 'movie')
                if result:
                    return {**result, 'provider': provider}
            except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError) as error:
                status = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
                record(provider, 'error', http_status=status, error_type=type(error).__name__)
                logging.warning('Metadata provider %s failed (%s%s); trying next provider.', provider, type(error).__name__, f', HTTP {status}' if status else '')
    return None


@lru_cache(maxsize=8)
def load_aliases(path, modified):
    with open(path, encoding='utf-8') as source:
        entries = json.load(source)
    return {normalized(name): entry for name, entry in entries.items()}


def search(query, year, is_series):
    result = search_providers(query, year, is_series)
    if result:
        return result
    # Explicit aliases cover alternate translations that fuzzy matching cannot infer.
    path = Path(os.getenv('METADATA_ALIASES_FILE', str(Path(__file__).resolve().parents[1] / 'assets/metadata-aliases.json')))
    if not path.is_file():
        return None
    try:
        alias = load_aliases(str(path), path.stat().st_mtime_ns).get(normalized(query))
        if not alias or alias['type'] != ('series' if is_series else 'movie'):
            return None
        if year and not is_series and alias.get('year') and year != alias['year']:
            return None
        return search_providers(alias['query'], alias.get('year') or year, is_series)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        import logging
        logging.warning('Invalid metadata aliases file; keeping filename metadata.')
        return None
