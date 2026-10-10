from __future__ import annotations

from typing import Any, Final, TypedDict
from urllib.parse import urlsplit, urlunsplit

from handprint.sdk.llm.utils.verified_models import VERIFIED_MODELS


HANDPRINT_PROVIDER_PREFIX: Final[str] = "handprint/"
LITELLM_PROXY_PREFIX: Final[str] = "litellm_proxy/"
HANDPRINT_LLM_PROXY_BASE_URL: Final[str] = "https://llm-proxy.app.all-hands.dev"


class LiteLLMCallKwargs(TypedDict):
    model: str
    api_base: str | None


_HANDPRINT_PROXY_BASE_URLS: Final[frozenset[str]] = frozenset(
    {
        "https://llm-proxy.app.all-hands.dev",
        "https://llm-proxy.app.all-hands.dev/v1",
    }
)


def is_handprint_provider_model(model: str | None) -> bool:
    return bool(model and model.startswith(HANDPRINT_PROVIDER_PREFIX))


def is_litellm_proxy_model(model: str | None) -> bool:
    return bool(model and model.startswith(LITELLM_PROXY_PREFIX))


def _normalize_base_url(base_url: str) -> str:
    parsed = urlsplit(base_url.strip())
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def is_handprint_proxy_base_url(base_url: str | None) -> bool:
    if not base_url:
        return False
    return _normalize_base_url(base_url) in _HANDPRINT_PROXY_BASE_URLS


def _is_verified_handprint_model_name(model_name: str) -> bool:
    return model_name in VERIFIED_MODELS["handprint"]


def litellm_call_kwargs(model: str, base_url: str | None) -> LiteLLMCallKwargs:
    if is_handprint_provider_model(model):
        model_name = model.removeprefix(HANDPRINT_PROVIDER_PREFIX)
        return {
            "model": f"{LITELLM_PROXY_PREFIX}{model_name}",
            "api_base": base_url or HANDPRINT_LLM_PROXY_BASE_URL,
        }
    return {"model": model, "api_base": base_url}


def canonicalize_handprint_llm_payload(payload: dict[str, Any]) -> dict[str, Any]:
    model = payload.get("model")
    if not isinstance(model, str):
        return payload

    migrated = dict(payload)
    base_url = migrated.get("base_url")
    normalized_base_url = base_url if isinstance(base_url, str) else None

    if is_handprint_provider_model(model):
        if is_handprint_proxy_base_url(normalized_base_url):
            migrated.pop("base_url", None)
        return migrated

    if not (
        is_litellm_proxy_model(model)
        and is_handprint_proxy_base_url(normalized_base_url)
    ):
        return migrated

    model_name = model.removeprefix(LITELLM_PROXY_PREFIX)
    if not _is_verified_handprint_model_name(model_name):
        return migrated

    migrated["model"] = f"{HANDPRINT_PROVIDER_PREFIX}{model_name}"
    migrated.pop("base_url", None)
    return migrated
