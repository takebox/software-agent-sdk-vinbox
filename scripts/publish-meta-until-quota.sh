#!/usr/bin/env bash
# Terbitkan paket meta ke PyPI, tunggu sampai kuota proyek baru terbuka.
#
# PyPI menolak pembuatan proyek baru milik akun ini dengan
# `429 Too many new projects created` dan **tidak** mengirim `Retry-After`,
# jadi jendela waktunya tidak bisa dibaca dari respons. Satu-satunya cara yang
# jujur adalah mencoba berkala dengan jeda panjang: skrip ini satu percobaan
# per 20 menit, maksimal 72 kali (~24 jam). Berhenti lebih awal kalau paketnya
# ternyata sudah ada.
#
# Pakai:
#   bash scripts/publish-meta-until-quota.sh
#
# Butuh `.pypi-token` (satu baris token PyPI, tidak pernah di-commit) dan
# wheel yang sudah dibangun di `dist-vinbox/`.
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT" || exit 1

TOKEN_FILE=${TOKEN_FILE:-.pypi-token}
WHEEL=${WHEEL:-dist-vinbox/software_agent_sdk_vinbox-1.53.0-py3-none-any.whl}
ATTEMPTS=${ATTEMPTS:-72}
DELAY=${DELAY:-1200}

[ -f "$TOKEN_FILE" ] || { echo "ERROR: $TOKEN_FILE tidak ada"; exit 1; }
[ -f "$WHEEL" ] || { echo "ERROR: $WHEEL tidak ada; jalankan build dulu"; exit 1; }
python -m twine --version >/dev/null 2>&1 || {
    echo "ERROR: twine belum terpasang; jalankan: python -m pip install twine"
    exit 1
}

TOKEN=$(cat "$TOKEN_FILE")

meta_state() {
    python - <<'PY'
import json, urllib.request
try:
    data = json.load(urllib.request.urlopen(
        "https://pypi.org/pypi/software-agent-sdk-vinbox/json", timeout=30))
    print("version=" + data["info"]["version"])
except Exception:
    print("belum-ada")
PY
}

for attempt in $(seq 1 "$ATTEMPTS"); do
    state=$(meta_state | tail -1)
    echo "=== percobaan $attempt/$ATTEMPTS $(date -u +%H:%M:%SZ) | pypi: $state ==="
    if [ "$state" != "belum-ada" ]; then
        echo "=== selesai: proyek meta sudah ada di PyPI ($state) ==="
        exit 0
    fi

    python -m twine upload --repository-url https://upload.pypi.org/legacy/ \
        -u __token__ -p "$TOKEN" --non-interactive "$WHEEL"
    rc=$?

    if [ "$rc" -eq 0 ]; then
        echo "=== selesai: meta terunggah $(date -u +%H:%M:%SZ) ==="
        exit 0
    fi

    echo "=== belum bisa (rc=$rc), tidur ${DELAY}s ==="
    sleep "$DELAY"
done

echo "=== menyerah: $ATTEMPTS percobaan habis, kuota PyPI belum terbuka ==="
exit 1
