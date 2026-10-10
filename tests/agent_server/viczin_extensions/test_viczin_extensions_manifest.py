"""Tests for the ViczinExtensionManifest model and its field validation."""

from typing import Any

import pytest
from pydantic import ValidationError

from handprint.agent_server.viczin_extensions.manifest import (
    ViczinExtensionBackendArtifact,
    ViczinExtensionContributes,
    ViczinExtensionManifest,
    ViczinExtensionPage,
)


def _manifest(**overrides: Any) -> ViczinExtensionManifest:
    defaults: dict[str, Any] = dict(
        schema_version=1,
        name="my-extension",
        display_name="My Extension",
        version="1.0.0",
        entrypoint="dist/index.js",
    )
    defaults.update(overrides)
    return ViczinExtensionManifest(**defaults)


def test_minimal_manifest():
    manifest = _manifest()
    assert manifest.name == "my-extension"
    assert manifest.description == ""
    assert manifest.contributes.pages == []


def test_manifest_with_page_contribution():
    manifest = _manifest(
        contributes=ViczinExtensionContributes(
            pages=[
                ViczinExtensionPage(
                    id="dashboard", title="Dashboard", path="/dashboard"
                )
            ]
        )
    )
    assert manifest.contributes.pages[0].id == "dashboard"
    assert manifest.contributes.pages[0].title == "Dashboard"
    assert manifest.contributes.pages[0].path == "/dashboard"


def test_manifest_with_multiple_distinct_pages():
    manifest = _manifest(
        contributes=ViczinExtensionContributes(
            pages=[
                ViczinExtensionPage(
                    id="dashboard", title="Dashboard", path="/dashboard"
                ),
                ViczinExtensionPage(
                    id="settings", title="Settings", path="/dashboard/settings"
                ),
            ]
        )
    )
    ids = [p.id for p in manifest.contributes.pages]
    paths = [p.path for p in manifest.contributes.pages]
    assert ids == ["dashboard", "settings"]
    assert paths == ["/dashboard", "/dashboard/settings"]


@pytest.mark.parametrize(
    "name",
    ["CamelCase", "", "has_underscore", "../evil", "-leading-hyphen"],
)
def test_invalid_name_rejected(name: str):
    with pytest.raises(ValidationError, match="Invalid extension name"):
        _manifest(name=name)


@pytest.mark.parametrize(
    "page_id",
    ["CamelCase", "", "has_underscore", "../evil", "with space"],
)
def test_invalid_contribution_id_rejected(page_id: str):
    with pytest.raises(ValidationError, match="Invalid contribution id"):
        ViczinExtensionPage(id=page_id, title="Title", path="/valid")


@pytest.mark.parametrize(
    "path",
    [
        "dashboard",  # missing leading slash
        "",  # empty
        "/",  # root alone — no segment after the slash
        "/../etc/passwd",  # traversal
        "//double-slash",  # empty segment
        "/trailing/",  # trailing slash / empty final segment
        "/Bad-Case",  # uppercase not allowed
        "/foo--bar",  # double hyphen: no segment between them
        "/foo_bar",  # underscore not allowed
    ],
)
def test_invalid_page_path_rejected(path: str):
    with pytest.raises(ValidationError, match="Invalid page path"):
        ViczinExtensionPage(id="valid-id", title="Title", path=path)


def test_valid_multi_segment_page_path_accepted():
    page = ViczinExtensionPage(
        id="settings", title="Settings", path="/dashboard/settings"
    )
    assert page.path == "/dashboard/settings"


def test_duplicate_page_contribution_ids_rejected():
    with pytest.raises(ValidationError, match="Duplicate page contribution id"):
        ViczinExtensionContributes(
            pages=[
                ViczinExtensionPage(id="dup", title="A", path="/a"),
                ViczinExtensionPage(id="dup", title="B", path="/b"),
            ]
        )


def test_duplicate_page_paths_rejected():
    with pytest.raises(ValidationError, match="Duplicate page path"):
        ViczinExtensionContributes(
            pages=[
                ViczinExtensionPage(id="a", title="A", path="/dup"),
                ViczinExtensionPage(id="b", title="B", path="/dup"),
            ]
        )


def test_duplicate_page_contribution_ids_rejected_through_full_manifest():
    """The nested ``contributes.pages`` validator must still fire when built
    from a raw dict (as ``viczin-extension.json`` loads), not just when
    ``ViczinExtensionContributes`` is constructed directly in Python.
    """
    with pytest.raises(ValidationError, match="Duplicate page contribution id"):
        _manifest(
            contributes={
                "pages": [
                    {"id": "dup", "title": "A", "path": "/a"},
                    {"id": "dup", "title": "B", "path": "/b"},
                ]
            }
        )


def test_manifest_round_trips_through_json_dict():
    """``model_validate`` over a full, schema-shaped dict — the actual
    ``viczin-extension.json`` ingestion path — round-trips unchanged.
    """
    payload = {
        "schema_version": 1,
        "name": "my-extension",
        "display_name": "My Extension",
        "version": "1.0.0",
        "description": "Does things",
        "entrypoint": "dist/index.js",
        "contributes": {
            "pages": [
                {"id": "dashboard", "title": "Dashboard", "path": "/dashboard"},
            ]
        },
    }
    manifest = ViczinExtensionManifest.model_validate(payload)
    assert manifest.model_dump() == payload


def test_backend_artifact_accepts_local_or_remote_source():
    checksum = "a" * 64
    local = ViczinExtensionBackendArtifact(path="backend/tool.tar.gz", sha256=checksum)
    remote = ViczinExtensionBackendArtifact.model_validate(
        {
            "url": "https://github.com/example/tool/releases/download/v1/tool.tar.gz",
            "sha256": checksum,
            "strip_components": 1,
        }
    )
    assert local.path == "backend/tool.tar.gz"
    assert remote.path == ""
    assert remote.url is not None
    assert remote.url.startswith("https://github.com/")
    assert remote.strip_components == 1
    assert "path" in ViczinExtensionBackendArtifact.model_json_schema()["required"]


@pytest.mark.parametrize(
    "payload",
    [
        {"sha256": "a" * 64},
        {
            "path": "backend/tool.tar.gz",
            "url": "https://example.com/tool.tar.gz",
            "sha256": "a" * 64,
        },
        {"url": "http://example.com/tool.tar.gz", "sha256": "a" * 64},
        {"url": "https://user@example.com/tool.tar.gz", "sha256": "a" * 64},
        {
            "path": "backend/tool.tar.gz",
            "sha256": "a" * 64,
            "strip_components": 1,
        },
    ],
)
def test_backend_artifact_rejects_unsafe_or_ambiguous_source(payload: dict[str, Any]):
    with pytest.raises(ValidationError):
        ViczinExtensionBackendArtifact.model_validate(payload)


@pytest.mark.parametrize(
    "entrypoint",
    ["", "/absolute/index.js", "../escape/index.js", "nested/../../escape.js"],
)
def test_invalid_entrypoint_syntax_rejected(entrypoint: str):
    with pytest.raises(ValidationError, match="entrypoint"):
        _manifest(entrypoint=entrypoint)


@pytest.mark.parametrize(
    "missing_field",
    ["schema_version", "name", "display_name", "version", "entrypoint"],
)
def test_missing_required_field_rejected(missing_field: str):
    """Confirms these fields are genuinely required (no silent default),
    catching e.g. an accidental ``= None`` or ``default=""`` creeping in.
    """
    payload: dict[str, Any] = dict(
        schema_version=1,
        name="my-extension",
        display_name="My Extension",
        version="1.0.0",
        entrypoint="dist/index.js",
    )
    del payload[missing_field]
    with pytest.raises(ValidationError, match=missing_field):
        ViczinExtensionManifest(**payload)


def test_schema_version_rejects_non_integer():
    with pytest.raises(ValidationError, match="schema_version"):
        _manifest(schema_version="not-a-number")
