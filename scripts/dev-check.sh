#!/usr/bin/env bash
# Cek menyeluruh paket Vinbox di platform yang sama dengan Vinbox (Linux).
#
#   bash scripts/dev-check.sh              # seluruh tes
#   bash scripts/dev-check.sh tests/sdk    # subset
#
# Dipakai juga oleh CI dan oleh pemeriksaan sebelum menerbitkan ke PyPI.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== python: $(python3 --version)"
python3 -m pip install --quiet --upgrade uv

echo "== uv sync (lock harus konsisten: --frozen)"
uv sync --frozen --group dev

echo "== import paket"
uv run python - <<'PY'
import handprint.agent_server
import handprint.sdk
import handprint.tools
import handprint.workspace

from handprint.sdk import vinbox

print("handprint.sdk        :", handprint.sdk.__name__)
print("handprint.tools      :", handprint.tools.__name__)
print("handprint.workspace  :", handprint.workspace.__name__)
print("handprint.agent_server:", handprint.agent_server.__name__)
print("kontrak cdp          :", vinbox.cdp_url())
print("kontrak llm          :", vinbox.llm_base_url())
print("kontrak ui           :", vinbox.ui_dir())
PY

echo "== pytest ${*:-tests}"
uv run python -m pytest "${@:-tests}"
