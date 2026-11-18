"""Vinbox runtime contract for the HandPrint agent runtime.

This repository is installed INSIDE Vinbox. It is not a standalone product and
it never boots its own desktop, its own browser, or its own model lane. Every
capability comes from the Vinbox machine that already runs around it:

* eyes and hands  -> Vinbox's Chromium, reached over CDP (default 127.0.0.1:9222)
* shell           -> Vinbox's pwsh, working inside app/program-file
* model lane      -> Vinbox's OpenAI-compatible bridge (default 127.0.0.1:4097/v1),
                     which forwards to opencode serve (4096) or llama-server (8088)
* workspace UI    -> Vinbox's dashboard at app/dashboard-7331 (HandPrint has no
                     screen of its own; the centre panel is always Vinbox)

Set ``VINBOX_MODE=0`` only when debugging this package on a developer laptop.
Every value below can be overridden with the matching ``VINBOX_*`` variable, so
the container, compose file and the Haijun consciousness all agree on one
contract instead of hardcoding paths in several places.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Final


__all__ = [
    "enabled",
    "home",
    "cdp_url",
    "browser_session_config",
    "profiles_dir",
    "chromium_path",
    "program_file",
    "shell_path",
    "terminal_type",
    "terminal_defaults",
    "llm_base_url",
    "llm_model",
    "llm_api_key",
    "llm_kwargs",
    "ui_dir",
    "agent_server_port",
    "apply_env",
]

#: Port of the agent server this package exposes inside Vinbox.
_DEFAULT_AGENT_SERVER_PORT: Final[int] = 18000


def _env(name: str, default: str) -> str:
    value = os.environ.get(f"VINBOX_{name}")
    if value is None or not value.strip():
        return default
    return value.strip()


def enabled() -> bool:
    """True when running inside Vinbox (the only supported deployment)."""
    mode = os.environ.get("VINBOX_MODE", "1")
    return mode.strip().lower() not in {"0", "false", "no"}


def home() -> Path:
    return Path(_env("HOME", "/app/vinbox"))


def cdp_url() -> str:
    """CDP endpoint of the Chromium that Vinbox already runs."""
    return _env("CDP_URL", "http://127.0.0.1:9222")


def profiles_dir() -> Path:
    """Chromium profile root on Vinbox's Linux volume (never a Windows mount)."""
    return Path(_env("PROFILES_DIR", str(home() / "data" / "browser_profiles")))


def chromium_path() -> str:
    return _env("CHROMIUM_PATH", "/usr/bin/chromium")


def program_file() -> Path:
    return Path(_env("PROGRAM_FILE", str(home() / "app" / "program-file")))


def shell_path() -> str:
    return _env("SHELL_PATH", "/usr/bin/pwsh")


def terminal_type() -> str:
    """Vinbox always talks through pwsh, never tmux/subprocess bash."""
    return _env("TERMINAL_TYPE", "powershell")


def ui_dir() -> Path:
    """Vinbox dashboard that HandPrint works inside (its only screen)."""
    return Path(_env("UI_DIR", str(home() / "app" / "dashboard-7331")))


def llm_base_url() -> str:
    """Vinbox model bridge: the only model lane this runtime may use."""
    return _env("LLM_BASE_URL", "http://127.0.0.1:4097/v1")


def llm_model() -> str:
    return _env("LLM_MODEL", "vinbox")


def llm_api_key() -> str:
    # The bridge is local and keyless; a placeholder keeps OpenAI clients happy.
    return _env("LLM_API_KEY", "vinbox-local")


def agent_server_port() -> int:
    raw = os.environ.get("VINBOX_AGENT_SERVER_PORT", str(_DEFAULT_AGENT_SERVER_PORT))
    try:
        return int(raw)
    except ValueError:
        return _DEFAULT_AGENT_SERVER_PORT


def browser_session_config() -> dict[str, Any]:
    """Attach to Vinbox's Chromium instead of launching a private browser.

    ``cdp_url`` is what makes this "eyes and hands inside Vinbox": browser-use
    connects to the already-running Chromium (the one shown in the centre panel)
    and drives it. Nothing else is overridden here: ``executable_path`` and
    ``user_data_dir`` stay as the launcher defaults (a detected Chromium and a
    per-executor profile directory under :func:`profiles_dir`) so a run that
    falls back to launching a browser still gets a unique profile.
    """
    return {"cdp_url": cdp_url()}


def terminal_defaults() -> dict[str, Any]:
    return {
        "terminal_type": terminal_type(),
        "shell_path": shell_path(),
        "working_dir": str(program_file()),
    }


def llm_kwargs() -> dict[str, Any]:
    """Keyword arguments for ``handprint.sdk.LLM`` pointing at Vinbox's lane."""
    return {
        "model": llm_model(),
        "base_url": llm_base_url(),
        "api_key": llm_api_key(),
    }


def apply_env() -> None:
    """Default environment for anything in this runtime that reads env vars.

    Called on import of :mod:`handprint.sdk`. Uses ``setdefault`` so an explicit
    operator value always wins.
    """
    if not enabled():
        return
    os.environ.setdefault("VINBOX_HOME", str(home()))
    os.environ.setdefault("VINBOX_CDP_URL", cdp_url())
    os.environ.setdefault("VINBOX_PROGRAM_FILE", str(program_file()))
    os.environ.setdefault("VINBOX_UI_DIR", str(ui_dir()))
    os.environ.setdefault("VINBOX_LLM_BASE_URL", llm_base_url())
    # Telemetry and marketplace are cloud features of the upstream product.
    # Inside Vinbox they stay off: nothing leaves the machine.
    os.environ.setdefault("DO_NOT_TRACK", "1")
