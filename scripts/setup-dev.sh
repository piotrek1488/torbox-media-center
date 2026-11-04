#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
command -v uv >/dev/null || { echo 'Install uv: https://docs.astral.sh/uv/getting-started/installation/' >&2; exit 1; }
uv venv --python 3.12 --allow-existing .venv
uv pip install --python .venv/bin/python -r requirements.txt
uv pip check --python .venv/bin/python
if [[ ! -e .env ]]; then
    cp .env.example .env
    # Use the repository-local, ignored output directory rather than /torbox.
    .venv/bin/python - <<'PY'
from pathlib import Path
path = Path('.env')
path.write_text(path.read_text().replace('MOUNT_PATH=/torbox', 'MOUNT_PATH=./torbox'))
PY
    chmod 600 .env
fi
printf '%s\n' 'Setup complete. Add your key to .env locally, then run scripts/run-dev.sh.'
