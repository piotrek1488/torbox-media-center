"""TMDB metadata lookup. Credentials are separate from TorBox authentication."""
from difflib import SequenceMatcher
from functools import lru_cache
import os
import re
import unicodedata

import httpx


def normalized(title):
    title = unicodedata.normalize('NFKD', title).casefold()
    return re.sub(r'[^\w]+', ' ', ''.join(c for c in title if not unicodedata.combining(c))).strip()


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
    candidates = []
    for result in results:
        if not isinstance(result, dict) or not result.get('id'):
            continue
        title = result.get('name' if is_series else 'title')
        if not isinstance(title, str) or not title.strip():
            continue
        original = result.get('original_name' if is_series else 'original_title') or title
        score = max(SequenceMatcher(None, normalized(query), normalized(name)).ratio()
                    for name in (title, original))
        date = result.get('first_air_date' if is_series else 'release_date') or ''
        result_year = int(date[:4]) if date[:4].isdigit() else None
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


def search(query, year, is_series):
    return lookup(query, year, is_series,
                  os.getenv('TMDB_API_KEY', '').strip(),
                  os.getenv('METADATA_LANGUAGE', 'pl-PL'))
