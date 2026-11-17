# VINBOX — runtime contract

This repository is **software-agent-sdk-vinbox** (`pip install
software-agent-sdk-vinbox`), retargeted to run **only inside the Vinbox
machine**. It is not a standalone agent product and it must never open a
desktop, a browser, or a model lane of its own.

## Why it exists

Vinbox already provides every surface the agent needs. HandPrint only describes
the flow and points at those surfaces; the actual eyes, hands, shell and model
lane live here, in this SDK.

| Capability | Owner inside Vinbox | Default |
|---|---|---|
| Eyes and hands (screenshot, click, type, scroll, tabs) | Vinbox Chromium over CDP | `VINBOX_CDP_URL=http://127.0.0.1:9222` |
| Shell | Vinbox pwsh | `VINBOX_SHELL_PATH=/usr/bin/pwsh` |
| Working directory | Vinbox program folder | `VINBOX_PROGRAM_FILE=/app/vinbox/app/program-file` |
| Model lane | Vinbox OpenAI-compatible bridge | `VINBOX_LLM_BASE_URL=http://127.0.0.1:4097/v1` |
| Lane behind the bridge | `opencode serve` / `llama-server` | `127.0.0.1:4096` / `127.0.0.1:8088` |
| Workspace UI | Vinbox dashboard (centre panel) | `VINBOX_UI_DIR=/app/vinbox/app/dashboard-7331` |
| Agent server (REST/WS) | this repo | `VINBOX_AGENT_SERVER_PORT=18000` |

HandPrint has **no screen of its own**. The only UI is Vinbox's dashboard. That
is the binding between the two projects: `handprint-vinbox` is the map of the
flow, this SDK is the part that actually sees and acts.

## The contract module

`vinbox-sdk/handprint/sdk/vinbox.py` is the single source of truth. It is
imported and applied automatically by `handprint.sdk`, so every component reads
the same values.

```python
from handprint.sdk import vinbox

vinbox.enabled()                 # True inside Vinbox (VINBOX_MODE=1)
vinbox.cdp_url()                 # http://127.0.0.1:9222
vinbox.browser_session_config()  # {"cdp_url": ..., "headless": False, ...}
vinbox.terminal_defaults()       # {"terminal_type": "powershell", ...}
vinbox.llm_kwargs()              # {"model": ..., "base_url": .../v1, "api_key": "vinbox-local"}
vinbox.ui_dir()                  # /app/vinbox/app/dashboard-7331
```

## Wiring that is already in place

* **Browser tool** (`handprint/tools/browser_use`): attaches to Vinbox's running
  Chromium through `cdp_url`; it does not launch a private browser. Profile path
  and executable fall back to Vinbox paths (`data/browser_profiles`,
  `/usr/bin/chromium`). A per-call config still overrides the defaults.
* **Terminal tool** (`handprint/tools/terminal`): defaults to the `powershell`
  backend with Vinbox's `pwsh`, and refuses to accept a workspace directory that
  does not exist inside the Vinbox tree — it creates/uses `app/program-file`.
* **Telemetry / marketplace**: cloud features of the upstream product. Inside
  Vinbox `DO_NOT_TRACK=1` is set by `vinbox.apply_env()`, so nothing leaves the
  machine.

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `VINBOX_MODE` | `1` | `0` disables the Vinbox contract (laptop debugging only) |
| `VINBOX_HOME` | `/app/vinbox` | Vinbox root |
| `VINBOX_CDP_URL` | `http://127.0.0.1:9222` | Chromium that Vinbox already runs |
| `VINBOX_PROFILES_DIR` | `<home>/data/browser_profiles` | Chromium profiles on the Linux volume |
| `VINBOX_CHROMIUM_PATH` | `/usr/bin/chromium` | Fallback browser binary |
| `VINBOX_SHELL_PATH` | `/usr/bin/pwsh` | Shell binary |
| `VINBOX_TERMINAL_TYPE` | `powershell` | Terminal backend |
| `VINBOX_PROGRAM_FILE` | `<home>/app/program-file` | Working directory |
| `VINBOX_LLM_BASE_URL` | `http://127.0.0.1:4097/v1` | Vinbox model bridge |
| `VINBOX_LLM_MODEL` | `vinbox` | Model selected in Vinbox's MODELS tab |
| `VINBOX_LLM_API_KEY` | `vinbox-local` | Local bridge key placeholder |
| `VINBOX_UI_DIR` | `<home>/app/dashboard-7331` | The only UI HandPrint uses |
| `VINBOX_AGENT_SERVER_PORT` | `18000` | REST/WS port exposed inside Vinbox |

## How Vinbox installs it

Only one distribution name is installed: **`software-agent-sdk-vinbox`**. It is a
meta package that pins the four Vinbox distributions on the same version:

| PyPI name | Folder |
|---|---|
| `handprint-vinbox-sdk` | `vinbox-sdk/` |
| `handprint-vinbox-tools` | `vinbox-tools/` |
| `handprint-vinbox-workspace` | `vinbox-workspace/` |
| `handprint-vinbox-agent-server` | `vinbox-agent-server/` |
| `software-agent-sdk-vinbox` (meta) | `vinbox-package/` |

```bash
pip install software-agent-sdk-vinbox
```

The folder name never decides what `pip` installs; the distribution name does.
That is why the folders were renamed to `vinbox-*` while the distributions keep
the `handprint-vinbox-*` name: there is exactly one place to install, and it can
only pull Vinbox builds.

Publishing order and the TestPyPI-first check live in
[PUBLISH-VINBOX.md](PUBLISH-VINBOX.md). The wheel contents are validated by
`scripts/check_vinbox_wheels.py` before any upload.

## What is deliberately not used

The package still ships the upstream Docker, Apptainer, remote-API and cloud
workspace classes, because they are part of the same module tree. Inside Vinbox
none of them is selected: the workspace is the local Vinbox tree, the browser is
Vinbox's Chromium, the shell is Vinbox's pwsh, and the model lane is Vinbox's
bridge. `ghcr.io/openhands/agent-server` image names that survive in those
classes point at the real upstream image and are never pulled by Vinbox.

## What must not be added back

* A bundled browser, Playwright Chromium download, or headless Chrome of its own.
* A second desktop, Xvfb, VNC, or any "HandPrint screen".
* A remote provider key, cloud login, or hosted marketplace registration.
* Raw source, tests, caches or `__pycache__` shipped into the Vinbox image —
  Vinbox installs wheels and binaries only.
