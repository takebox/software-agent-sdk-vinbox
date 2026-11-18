#!/usr/bin/env bash
# Pasang kelima wheel Vinbox di venv bersih lalu buktikan bisa dipakai.
#
#   bash scripts/check_vinbox_install.sh [dist-vinbox]
#
# Dependensi pihak ketiga diambil dari PyPI; kelima wheel Vinbox diambil dari
# folder lokal. Ini yang meniru `pip install software-agent-sdk-vinbox` tanpa
# harus menerbitkan apa pun lebih dulu.
set -euo pipefail

WHEELS="${1:-dist-vinbox}"
VENV="${TMPDIR:-/tmp}/vinbox-install-check"

rm -rf "$VENV"
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip

echo "== pasang software-agent-sdk-vinbox dari $WHEELS"
"$VENV/bin/python" -m pip install --quiet \
    --find-links "$WHEELS" \
    software-agent-sdk-vinbox

echo "== versi terpasang"
"$VENV/bin/python" -m pip list 2>/dev/null | grep -Ei 'handprint-vinbox|software-agent-sdk-vinbox'

echo "== kontrak Vinbox"
"$VENV/bin/python" - <<'PY'
from handprint.sdk import vinbox

print("cdp :", vinbox.cdp_url())
print("llm :", vinbox.llm_base_url())
print("ui  :", vinbox.ui_dir())
print("port:", vinbox.agent_server_port())
PY

echo "== agent-server"
"$VENV/bin/agent-server" --help >/dev/null
echo "agent-server --help: ok"

echo "== tidak ada paket umum yang ikut"
if "$VENV/bin/python" -m pip list 2>/dev/null | grep -Ei '^openhands|^handprint-sdk|^handprint-tools' ; then
    echo "GAGAL: ada paket non-Vinbox terpasang"
    exit 1
fi
echo "bersih: hanya paket Vinbox"

echo
echo "Siap: instalasi bersih berhasil."
