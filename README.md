# software-agent-sdk-vinbox

Runtime agent untuk **Vinbox**. Repo ini **hanya berjalan di dalam mesin
Vinbox** — bukan produk mandiri, bukan SDK umum, dan tidak pernah membuka
desktop, browser, atau jalur model sendiri.

```bash
pip install software-agent-sdk-vinbox
```

Perintah itu memasang empat paket sekaligus (lihat [Isi paket](#isi-paket)).
Sesudah itu `agent-server` hidup di dalam Vinbox dan memakai semua yang sudah
disediakan Vinbox.

## Kenapa repo ini terpisah

`handprint-vinbox` adalah **peta alur**: ia menunjukkan bahwa UI yang dipakai
adalah milik Vinbox. Repo ini adalah **bagian yang benar-benar melihat dan
bertindak**: mata, tangan, shell, dan jalur model. HandPrint tidak punya layar
sendiri; satu-satunya layar adalah dashboard Vinbox (`app/dashboard-7331`).

| Kemampuan | Pemilik di dalam Vinbox | Default |
|---|---|---|
| Mata & tangan (screenshot, klik, ketik, scroll, tab) | Chromium Vinbox lewat CDP | `VINBOX_CDP_URL=http://127.0.0.1:9222` |
| Shell | pwsh Vinbox, di `app/program-file` | `VINBOX_SHELL_PATH=/usr/bin/pwsh` |
| Direktori kerja | folder program Vinbox | `VINBOX_PROGRAM_FILE=/app/vinbox/app/program-file` |
| Jalur model | bridge OpenAI-compatible Vinbox | `VINBOX_LLM_BASE_URL=http://127.0.0.1:4097/v1` |
| Di balik bridge | `opencode serve` / `llama-server` | `127.0.0.1:4096` / `127.0.0.1:8088` |
| UI | dashboard Vinbox (panel tengah) | `VINBOX_UI_DIR=/app/vinbox/app/dashboard-7331` |
| Agent server (REST/WS) | repo ini | `VINBOX_AGENT_SERVER_PORT=18000` |

Kontrak itu tinggal di satu tempat: `vinbox-sdk/handprint/sdk/vinbox.py`.
Modul itu diimpor otomatis oleh `handprint.sdk`, jadi semua komponen membaca
nilai yang sama. Detail lengkap ada di [VINBOX.md](VINBOX.md).

## Isi paket

| Distribusi | Folder | Isi |
|---|---|---|
| `handprint-vinbox-sdk` | `vinbox-sdk/` | `handprint.sdk` — agent core, wiring LLM, kontrak `vinbox.py` |
| `handprint-vinbox-tools` | `vinbox-tools/` | `handprint.tools` — `browser_use` (mata & tangan), terminal pwsh, file editor |
| `handprint-vinbox-workspace` | `vinbox-workspace/` | `handprint.workspace` — workspace lokal di dalam tree Vinbox |
| `handprint-vinbox-agent-server` | `vinbox-agent-server/` | `handprint.agent_server` — REST/WS `agent-server`, loopback `127.0.0.1:18000` |
| `software-agent-sdk-vinbox` | `vinbox-package/` | meta paket; mengunci keempat paket di atas pada versi yang sama |

Versi kelimanya selalu sama (sekarang `1.53.0`).

## Menjalankan di dalam Vinbox

```bash
agent-server --host 127.0.0.1 --port 18000
```

Semua default lingkungan bisa dioverride lewat `VINBOX_*`:

| Variabel | Default |
|---|---|
| `VINBOX_MODE` | `1` (`0` hanya untuk debugging di laptop) |
| `VINBOX_HOME` | `/app/vinbox` |
| `VINBOX_CDP_URL` | `http://127.0.0.1:9222` |
| `VINBOX_PROFILES_DIR` | `<home>/data/browser_profiles` |
| `VINBOX_CHROMIUM_PATH` | `/usr/bin/chromium` |
| `VINBOX_SHELL_PATH` | `/usr/bin/pwsh` |
| `VINBOX_TERMINAL_TYPE` | `powershell` |
| `VINBOX_PROGRAM_FILE` | `<home>/app/program-file` |
| `VINBOX_LLM_BASE_URL` | `http://127.0.0.1:4097/v1` |
| `VINBOX_LLM_MODEL` | `vinbox` |
| `VINBOX_LLM_API_KEY` | `vinbox-local` |
| `VINBOX_UI_DIR` | `<home>/app/dashboard-7331` |
| `VINBOX_AGENT_SERVER_PORT` | `18000` |

Contoh memakai SDK di dalam proses Vinbox:

```python
from handprint.sdk import LLM, Agent, Conversation, Tool
from handprint.sdk import vinbox
from handprint.tools.terminal import TerminalTool

llm = LLM(**vinbox.llm_kwargs())          # bridge Vinbox, bukan provider luar
agent = Agent(llm=llm, tools=[Tool(name=TerminalTool.name)])

conversation = Conversation(agent=agent, workspace=str(vinbox.program_file()))
conversation.send_message("Tulis 3 fakta tentang proyek ini ke FACTS.txt.")
conversation.run()
```

`browser_use` menempel ke Chromium yang sudah dijalankan Vinbox (`cdp_url`),
bukan meluncurkan browser pribadi.

## Yang tidak boleh ditambahkan kembali

- Browser bundel, unduhan Playwright Chromium, atau Chrome headless sendiri.
- Desktop kedua, Xvfb, VNC, atau "layar HandPrint".
- Provider key eksternal, login cloud, atau pendaftaran marketplace.
- Sumber, tes, cache, atau `__pycache__` yang ikut masuk image Vinbox — Vinbox
  hanya memasang wheel.

## Pengembangan

```bash
uv lock                 # kunci dependensi (uv.lock dipakai CI dan uv sync)
uv sync                 # pasang seluruh workspace
python -m pytest tests/ # jalankan tes
```

Ganti nama folder paket tidak mengubah nama distribusi: folder `vinbox-sdk`
berisi distribusi `handprint-vinbox-sdk`, dan seterusnya. Yang dibaca `pip`
selalu nama distribusi, bukan nama folder.

## Menerbitkan ke PyPI

Ikuti [PUBLISH-VINBOX.md](PUBLISH-VINBOX.md). Urutannya: TestPyPI dulu, uji
`pip install` dari TestPyPI, baru PyPI. Empat paket dulu, meta paket terakhir.

## Lisensi

MIT. Repo ini diturunkan dari Handprint Software Agent SDK (MIT) dan telah
diubah agar hanya berjalan di dalam Vinbox.
