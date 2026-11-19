# Menerbitkan paket Vinbox ke PyPI

Ada **lima** distribusi yang harus terbit. Nama di PyPI sengaja berbeda dari
proyek asal supaya tidak bentrok, dan supaya jelas bahwa isinya sudah
disesuaikan untuk Vinbox:

| # | Nama di PyPI | Folder sumber |
|---|---|---|
| 1 | `handprint-vinbox-sdk` | `vinbox-sdk/` |
| 2 | `handprint-vinbox-tools` | `vinbox-tools/` |
| 3 | `handprint-vinbox-workspace` | `vinbox-workspace/` |
| 4 | `handprint-vinbox-agent-server` | `vinbox-agent-server/` |
| 5 | `software-agent-sdk-vinbox` (meta) | `vinbox-package/` |

Versi: **1.53.1** untuk semuanya. Meta paket mengunci keempatnya di `==1.53.1`,
jadi urutan upload penting: **1–4 dulu, meta terakhir**.

Yang dipasang orang lewat `pip install software-agent-sdk-vinbox` adalah paket
meta itu. Paket meta menarik keempat paket Vinbox, bukan paket umum mana pun.

## 0. Siapkan token di file lokal (jangan di-commit)

Token tidak boleh masuk repo, README, skrip, atau log. Taruh di root repo
sebagai file yang sudah di-`gitignore`:

```
.pypi-test-token   # token TestPyPI (dipakai lebih dulu)
.pypi-token        # token PyPI (baru dipakai setelah TestPyPI lolos)
```

Isi file: satu baris token, contoh bentuknya `pypi-...`. Jangan beri komentar
atau spasi tambahan.

## 1. Bangun wheel

```bash
bash scripts/build_vinbox_packages.sh
```

Hasilnya di `dist-vinbox/`:

```
handprint_vinbox_sdk-1.53.1-py3-none-any.whl
handprint_vinbox_tools-1.53.1-py3-none-any.whl
handprint_vinbox_workspace-1.53.1-py3-none-any.whl
handprint_vinbox_agent_server-1.53.1-py3-none-any.whl
software_agent_sdk_vinbox-1.53.1-py3-none-any.whl
```

Periksa dulu isinya sebelum upload:

```bash
python scripts/check_vinbox_wheels.py dist-vinbox
```

Skrip itu menolak wheel yang memuat nama lama, tes, atau `__pycache__`.

## 2. Uji di TestPyPI lebih dulu

```bash
python -m pip install --upgrade twine

# empat paket dulu
python -m twine upload --repository-url https://test.pypi.org/legacy/ \
  -u __token__ -p "$(cat .pypi-test-token)" \
  dist-vinbox/handprint_vinbox_sdk-1.53.1-py3-none-any.whl \
  dist-vinbox/handprint_vinbox_tools-1.53.1-py3-none-any.whl \
  dist-vinbox/handprint_vinbox_workspace-1.53.1-py3-none-any.whl \
  dist-vinbox/handprint_vinbox_agent_server-1.53.1-py3-none-any.whl

# meta paket terakhir
python -m twine upload --repository-url https://test.pypi.org/legacy/ \
  -u __token__ -p "$(cat .pypi-test-token)" \
  dist-vinbox/software_agent_sdk_vinbox-1.53.1-py3-none-any.whl
```

`--repository-url` dipakai eksplisit supaya tidak bergantung pada `~/.pypirc`.

Uji pasang dari TestPyPI di venv bersih. `--extra-index-url` wajib karena
dependensi pihak ketiga tidak ada di TestPyPI.

> **Jebakan TestPyPI.** `--extra-index-url` menggabungkan kedua index, dan
> TestPyPI menyimpan proyek jiplakan bernama sama dengan versi yang lebih
> tinggi — misalnya `fastapi (=1.0)` yang sdist-nya rusak
> (`FileNotFoundError: DESCRIPTION.txt`). Resolusi gabungan akan memilih versi
> itu dan gagal, padahal paket kita benar. Jadi uji dengan cara ini:
>
> ```bash
> pip download --no-deps -d /tmp/w --index-url https://test.pypi.org/simple/ \
>   software-agent-sdk-vinbox==1.53.1 handprint-vinbox-sdk==1.53.1 \
>   handprint-vinbox-tools==1.53.1 handprint-vinbox-workspace==1.53.1 \
>   handprint-vinbox-agent-server==1.53.1
> pip install --find-links /tmp/w --index-url https://pypi.org/simple/ \
>   software-agent-sdk-vinbox==1.53.1
> ```
>
> Pada PyPI tidak ada masalah ini: `pip install software-agent-sdk-vinbox`
> biasa sudah benar.

```bash
python -m venv /tmp/vinbox-testpypi
source /tmp/vinbox-testpypi/bin/activate   # Windows: .venv\Scripts\activate

pip install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  software-agent-sdk-vinbox==1.53.1

agent-server --help
python -c "import handprint.sdk.vinbox as v; print(v.cdp_url(), v.llm_base_url())"
```

Keluaran yang diharapkan:

```
http://127.0.0.1:9222 http://127.0.0.1:4097/v1
```

Kalau langkah ini gagal, **jangan lanjut** ke PyPI. Perbaiki dulu.

## 3. Terbitkan ke PyPI

Setelah TestPyPI lolos, ulangi dengan token PyPI. Empat paket inti dulu, paket
meta terakhir, karena metanya mengunci keempatnya pada versi yang sama.

Paket meta adalah **proyek baru** di PyPI, dan PyPI membatasi pembuatan proyek
baru: responsnya `HTTPError: 429 Too Many Requests` dengan badan
`Too many new projects created` dan **tanpa** header `Retry-After`, jadi
jendela waktunya tidak bisa dibaca. Ini bukan token salah dan bukan paket
rusak — empat paket inti tetap terbit normal. Pakai skrip penunggu supaya
tidak perlu menebak:

```bash
bash scripts/publish-meta-until-quota.sh   # satu percobaan / 20 menit, ~24 jam
```

Skrip itu berhenti sendiri begitu PyPI menerima paketnya, dan aman diulang:
paket yang sudah terunggah ditolak sebagai `File already exists`, bukan
terbit dua kali.

```bash
python -m twine upload --repository-url https://upload.pypi.org/legacy/ \
  -u __token__ -p "$(cat .pypi-token)" \
  dist-vinbox/handprint_vinbox_sdk-1.53.1-py3-none-any.whl \
  dist-vinbox/handprint_vinbox_tools-1.53.1-py3-none-any.whl \
  dist-vinbox/handprint_vinbox_workspace-1.53.1-py3-none-any.whl \
  dist-vinbox/handprint_vinbox_agent_server-1.53.1-py3-none-any.whl

python -m twine upload --repository-url https://upload.pypi.org/legacy/ \
  -u __token__ -p "$(cat .pypi-token)" \
  dist-vinbox/software_agent_sdk_vinbox-1.53.1-py3-none-any.whl
```

## 4. Verifikasi dari PyPI

Di venv kosong, tanpa `--extra-index-url` dan tanpa wheel lokal:

```bash
pip install software-agent-sdk-vinbox==1.53.1
agent-server --version || agent-server --help
python -c "import handprint.sdk.vinbox as v; print(v.cdp_url(), v.llm_base_url())"
```

Yang harus terlihat:

- `pip list` memuat **lima** distribusi: `software-agent-sdk-vinbox` dan empat
  `handprint-vinbox-*`.
- Kontrak mencetak `http://127.0.0.1:9222 http://127.0.0.1:4097/v1`.
- `agent-server --help` keluar dengan status 0.
- Tidak ada paket bernama lama (lihat `FORBIDDEN_TEXT` di
  `scripts/check_vinbox_wheels.py`), dan tidak ada `software-agent-sdk` polos. Kalau
  salah satunya muncul, paket yang terbit salah — jangan lanjut.

Memasang `handprint-vinbox-agent-server` saja (tanpa meta) juga sah: hasilnya
tiga distribusi (`-agent-server`, `-sdk`, `-tools`), karena `-workspace` hanya
ditarik oleh meta paket.

## 5. Setelah terbit

Dockerfile Vinbox memakai:

```
ARG HANDPRINT_VINBOX_VERSION=1.53.1
pip install --no-index --find-links ... software-agent-sdk-vinbox==${HANDPRINT_VINBOX_VERSION}
```

Untuk versi berikutnya: naikkan versi di **kelima** `pyproject.toml`, jalankan
`uv lock`, bangun ulang, lalu terbitkan dengan urutan yang sama.

## Catatan

- `uv.lock` sudah memakai nama baru (`handprint-vinbox-*`) dan folder baru
  (`vinbox-*`). Jalankan `uv lock` lagi hanya kalau dependensi berubah.
- Jangan pernah meng-commit `.pypi-token`, `.pypi-test-token`, `~/.pypirc`, atau
  file `.env` berisi token.
- Kalau nama paket sudah dipakai orang lain di PyPI, ganti sufiksnya (misalnya
  `-vinbox1`) dan sesuaikan dependensi di meta paket.
