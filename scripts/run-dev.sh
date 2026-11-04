#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
[[ -x .venv/bin/python ]] || { echo 'Run bash scripts/setup-dev.sh first.' >&2; exit 1; }
.venv/bin/python - <<'PY'
import os
from dotenv import load_dotenv
load_dotenv('.env')
if not os.getenv('TORBOX_API_KEY', '').strip():
    raise SystemExit('Add TORBOX_API_KEY to your local .env before starting.')
if (os.getenv('ENABLE_METADATA', 'false').lower() == 'true'
        and os.getenv('RAW_MODE', 'false').lower() != 'true'
        and not os.getenv('TMDB_API_KEY', '').strip()):
    raise SystemExit('Add TMDB_API_KEY to .env for TMDB metadata.')
PY
exec .venv/bin/python main.py
