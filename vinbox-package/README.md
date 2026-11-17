# software-agent-sdk-vinbox

Meta package that installs the complete HandPrint agent runtime **for Vinbox**.

It pulls in four distributions. Nothing here is a standalone product: the runtime
only works inside the Vinbox machine, using Vinbox's Chromium (CDP), Vinbox's
pwsh, Vinbox's model bridge, and Vinbox's dashboard as its only UI.

| Distribution | Isi |
|---|---|
| `handprint-vinbox-sdk` | `handprint.sdk` — agent core, LLM bridge wiring, kontrak `vinbox.py` |
| `handprint-vinbox-tools` | `handprint.tools` — `browser_use` (mata & tangan), terminal pwsh, file editor |
| `handprint-vinbox-workspace` | `handprint.workspace` — workspace lokal di dalam tree Vinbox |
| `handprint-vinbox-agent-server` | `handprint.agent_server` — REST/WS `agent-server`, loopback `127.0.0.1:18000` |

## Install

```bash
pip install software-agent-sdk-vinbox==1.53.0
```

Itu memasang keempat paket di atas sekaligus.

## Jalankan di dalam Vinbox

```bash
agent-server --host 127.0.0.1 --port 18000
```

Default lingkungan (bisa dioverride lewat `VINBOX_*`):

| Variabel | Default |
|---|---|
| `VINBOX_MODE` | `1` |
| `VINBOX_CDP_URL` | `http://127.0.0.1:9222` |
| `VINBOX_LLM_BASE_URL` | `http://127.0.0.1:4097/v1` |
| `VINBOX_PROGRAM_FILE` | `/app/vinbox/app/program-file` |
| `VINBOX_UI_DIR` | `/app/vinbox/app/dashboard-7331` |
| `VINBOX_SHELL_PATH` | `/usr/bin/pwsh` |

HandPrint tidak punya layar sendiri: UI-nya adalah dashboard Vinbox
(`app/dashboard-7331`). Repro ini tidak membawa browser, desktop, atau model
lokal sendiri.

## Lisensi

MIT, mengikuti proyek asal. Kode telah diubah untuk lingkungan Vinbox.
