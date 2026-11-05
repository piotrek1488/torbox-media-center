"""Read-only metadata diagnosis: no TorBox key, database or mount is used."""
import argparse
import json
import logging
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from dotenv import load_dotenv
load_dotenv(root / '.env')
from functions.mediaFunctions import parseMediaName, metadataMediaTypes
from library import metadata

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('filename')
parser.add_argument('--download', default='')
parser.add_argument('--path', default='')
parser.add_argument('--offline', action='store_true', help='Show parsing and configuration without network requests')
args = parser.parse_args()
for name in ('httpx', 'httpcore'):
    logging.getLogger(name).setLevel(logging.CRITICAL)
parsed = parseMediaName(args.filename, args.download, args.path)
media_types = metadataMediaTypes(parsed)
is_series = media_types[0] == 'series'
report = {
    'providers': os.getenv('METADATA_PROVIDERS', 'tmdb,tvdb,kitsu'),
    'language': os.getenv('METADATA_LANGUAGE', 'pl-PL'),
    'credentials_present': {name: bool(os.getenv(name, '').strip()) for name in ('TMDB_API_KEY', 'TVDB_API_KEY', 'TVDB_PIN')},
    'type': media_types[0],
    'lookup_types': media_types,
    'candidates': parsed.get('metadata_candidates', []),
}
if not args.offline:
    with metadata.capture_diagnostics() as events:
        for media_type in media_types:
            for candidate in report['candidates']:
                result = metadata.search(candidate['title'], candidate.get('year'), media_type == 'series')
                if result:
                    report['match'] = {key: result.get(key) for key in ('title', 'year', 'provider', 'link')}
                    break
            if 'match' in report:
                break
    report['events'] = events
print(json.dumps(report, ensure_ascii=False, indent=2))
