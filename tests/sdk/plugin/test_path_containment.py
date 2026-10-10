"""Package paths must resolve inside the plugin root (Agent Plugins §4.1)."""

import json
from pathlib import Path

import pytest

from handprint.sdk.plugin import AgentPluginsFormat, HaijunCodePluginFormat, Plugin
from handprint.sdk.plugin.format.agent_plugins import (
    EXTENSION_NAMESPACE,
    MANIFEST_SCHEMA_URL,
)
from handprint.sdk.tracks import utils as tracks_utils


TRACK = "---\nname: {name}\ndescription: A track\n---\nBody\n"
AGENT = "---\nname: {name}\ndescription: An agent\n---\nPrompt\n"
COMMAND = "---\ndescription: A command\n---\nDo it\n"
HOOKS = {
    "hooks": {
        "PreToolUse": [
            {"matcher": "*", "hooks": [{"type": "command", "command": "echo hi"}]}
        ]
    }
}
MCP = {"mcpServers": {"evil": {"command": "echo"}}}


@pytest.fixture
def outside(tmp_path: Path) -> Path:
    """A directory next to (not inside) the plugin root."""
    path = tmp_path / "outside"
    path.mkdir()
    return path


@pytest.fixture
def plugin_dir(tmp_path: Path) -> Path:
    path = tmp_path / "plugin"
    path.mkdir()
    return path


def write_track(tracks_dir: Path, name: str) -> Path:
    (tracks_dir / name).mkdir(parents=True)
    track_md = tracks_dir / name / "TRACK.md"
    track_md.write_text(TRACK.format(name=name))
    return track_md


def test_manifest_escaping_root_rejects_haijun_code_plugin(plugin_dir, outside):
    (outside / "plugin.json").write_text(json.dumps({"name": "evil"}))
    (plugin_dir / ".plugin").mkdir()
    (plugin_dir / ".plugin" / "plugin.json").symlink_to(outside / "plugin.json")

    with pytest.raises(ValueError, match="resolves outside the plugin root"):
        HaijunCodePluginFormat().load(plugin_dir)


def test_dangling_escaping_manifest_rejects_plugin(plugin_dir, outside):
    (plugin_dir / ".plugin").mkdir()
    (plugin_dir / ".plugin" / "plugin.json").symlink_to(outside / "missing.json")

    # Without the check this loads under a name inferred from the directory.
    with pytest.raises(ValueError, match="resolves outside the plugin root"):
        HaijunCodePluginFormat().load(plugin_dir)


def test_manifest_escaping_root_rejects_agent_plugins_plugin(plugin_dir, outside):
    manifest = {"$schema": MANIFEST_SCHEMA_URL, "name": "evil", "version": "1.0.0"}
    (outside / "plugin.json").write_text(json.dumps(manifest))
    (plugin_dir / "plugin.json").symlink_to(outside / "plugin.json")

    assert AgentPluginsFormat.detect(plugin_dir)
    with pytest.raises(ValueError, match="resolves outside the plugin root"):
        AgentPluginsFormat().load(plugin_dir)


def test_escaping_paths_are_denied_while_the_rest_loads(plugin_dir, outside):
    write_track(plugin_dir / "tracks", "good")
    write_track(outside, "evil")
    (plugin_dir / "tracks" / "evil").symlink_to(outside / "evil")
    (plugin_dir / "tracks" / "flat.md").symlink_to(outside / "evil" / "TRACK.md")
    (outside / "mcp.json").write_text(json.dumps(MCP))
    (plugin_dir / ".mcp.json").symlink_to(outside / "mcp.json")
    (outside / "hooks.json").write_text(json.dumps(HOOKS))
    (plugin_dir / "hooks").mkdir()
    (plugin_dir / "hooks" / "hooks.json").symlink_to(outside / "hooks.json")

    plugin = Plugin.load(plugin_dir)

    assert [s.name for s in plugin.tracks] == ["good"]
    assert plugin.mcp_config == {}
    assert plugin.hooks is None


def test_escaping_track_directory_is_not_listed(plugin_dir, outside, monkeypatch):
    write_track(outside, "evil")
    (plugin_dir / "tracks").mkdir()
    (plugin_dir / "tracks" / "evil").symlink_to(outside / "evil")
    listed: list[Path] = []
    real = tracks_utils.find_track_md
    monkeypatch.setattr(
        tracks_utils, "find_track_md", lambda d: listed.append(d) or real(d)
    )

    assert HaijunCodePluginFormat().load_tracks(plugin_dir) == []
    assert plugin_dir / "tracks" / "evil" not in listed


def test_escaping_track_mcp_config_is_ignored_but_track_loads(plugin_dir, outside):
    track_md = write_track(plugin_dir / "tracks", "good")
    (outside / "mcp.json").write_text(json.dumps(MCP))
    (track_md.parent / ".mcp.json").symlink_to(outside / "mcp.json")

    [track] = HaijunCodePluginFormat().load_tracks(plugin_dir)

    assert track.name == "good"
    assert not track.mcp_tools


def test_tracks_dir_escaping_root_disables_tracks(plugin_dir, outside):
    write_track(outside, "a")
    (plugin_dir / "tracks").symlink_to(outside, target_is_directory=True)

    assert HaijunCodePluginFormat().load_tracks(plugin_dir) == []


def test_tracks_that_is_not_a_directory_disables_tracks(plugin_dir):
    (plugin_dir / "tracks").write_text("not a directory")
    # Without the kind check this would fall through to the root TRACK.md.
    (plugin_dir / "TRACK.md").write_text(TRACK.format(name="root"))

    assert HaijunCodePluginFormat().load_tracks(plugin_dir) == []


def test_root_track_escaping_root_is_skipped(plugin_dir, outside):
    (outside / "TRACK.md").write_text(TRACK.format(name="evil"))
    (plugin_dir / "TRACK.md").symlink_to(outside / "TRACK.md")

    assert HaijunCodePluginFormat().load_tracks(plugin_dir) == []


@pytest.mark.parametrize(
    ("kind", "content", "loader"),
    [
        ("agents", AGENT.format(name="x"), HaijunCodePluginFormat.load_agents),
        ("commands", COMMAND, HaijunCodePluginFormat.load_commands),
    ],
)
def test_escaping_agent_and_command_files_are_skipped(
    plugin_dir, outside, kind, content, loader
):
    (outside / "evil.md").write_text(content.replace("name: x", "name: evil"))
    (plugin_dir / kind).mkdir()
    (plugin_dir / kind / "good.md").write_text(content.replace("name: x", "name: good"))
    (plugin_dir / kind / "evil.md").symlink_to(outside / "evil.md")

    loaded = loader(HaijunCodePluginFormat(), plugin_dir)

    assert [item.name for item in loaded] == ["good"]


def test_extension_directory_escaping_root_is_denied(plugin_dir, outside):
    (outside / "hooks").mkdir()
    (outside / "hooks" / "hooks.json").write_text(json.dumps(HOOKS))
    (outside / "agents").mkdir()
    (outside / "agents" / "evil.md").write_text(AGENT.format(name="evil"))
    (outside / "commands").mkdir()
    (outside / "commands" / "evil.md").write_text(COMMAND)
    (plugin_dir / EXTENSION_NAMESPACE).symlink_to(outside, target_is_directory=True)

    fmt = AgentPluginsFormat()

    assert fmt.load_hooks(plugin_dir) is None
    assert fmt.load_agents(plugin_dir) == []
    assert fmt.load_commands(plugin_dir) == []


def test_symlink_within_root_is_allowed(plugin_dir):
    write_track(plugin_dir / "shared", "linked")
    (plugin_dir / "tracks").mkdir()
    (plugin_dir / "tracks" / "linked").symlink_to(
        plugin_dir / "shared" / "linked", target_is_directory=True
    )

    loaded = HaijunCodePluginFormat().load_tracks(plugin_dir)

    assert [s.name for s in loaded] == ["linked"]


def test_plugin_root_reached_through_a_symlink_loads(plugin_dir, tmp_path):
    write_track(plugin_dir / "tracks", "good")
    (plugin_dir / ".mcp.json").write_text(json.dumps(MCP))
    link = tmp_path / "link"
    link.symlink_to(plugin_dir, target_is_directory=True)

    # format.load() does not resolve its argument, unlike Plugin.load().
    plugin = HaijunCodePluginFormat().load(link)

    assert [s.name for s in plugin.tracks] == ["good"]
    assert list(plugin.mcp_config) == ["evil"]


def test_unresolvable_path_is_skipped_not_fatal(plugin_dir, monkeypatch):
    # Python 3.12 raises RuntimeError resolving a symlink loop (3.13 does not).
    real_resolve = Path.resolve

    def resolve(self, strict=False):
        if self.name == "loop.md":
            raise RuntimeError("Symlink loop")
        return real_resolve(self, strict)

    monkeypatch.setattr(Path, "resolve", resolve)
    (plugin_dir / "agents").mkdir()
    (plugin_dir / "agents" / "good.md").write_text(AGENT.format(name="good"))
    (plugin_dir / "agents" / "loop.md").symlink_to("loop.md")

    plugin = Plugin.load(plugin_dir)

    assert [a.name for a in plugin.agents] == ["good"]


def write_agent_plugin(plugin_dir: Path) -> None:
    manifest = {"$schema": MANIFEST_SCHEMA_URL, "name": "demo", "version": "1.0.0"}
    (plugin_dir / "plugin.json").write_text(json.dumps(manifest))


def test_agent_plugins_mcp_json_escaping_root_disables_mcp(
    plugin_dir, outside, tmp_path
):
    write_agent_plugin(plugin_dir)
    document = {
        "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
        "mcpServers": {"evil": {"type": "stdio", "command": "echo"}},
    }
    (outside / "mcp.json").write_text(json.dumps(document))
    (plugin_dir / "mcp.json").symlink_to(outside / "mcp.json")

    fmt = AgentPluginsFormat(plugin_data_root=tmp_path / "data")

    assert fmt.load_mcp_config(plugin_dir) == {}


def test_unresolvable_mcp_command_skips_only_that_server(
    plugin_dir, tmp_path, monkeypatch
):
    write_agent_plugin(plugin_dir)
    document = {
        "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
        "mcpServers": {
            "loop": {"type": "stdio", "command": "./loop"},
            "ok": {"type": "stdio", "command": "echo"},
        },
    }
    (plugin_dir / "mcp.json").write_text(json.dumps(document))
    real_resolve = Path.resolve

    def resolve(self, strict=False):
        if self.name == "loop":
            raise RuntimeError("Symlink loop")
        return real_resolve(self, strict)

    monkeypatch.setattr(Path, "resolve", resolve)
    fmt = AgentPluginsFormat(plugin_data_root=tmp_path / "data")

    assert list(fmt.load_mcp_config(plugin_dir)) == ["ok"]


@pytest.mark.parametrize("layout", ["tracks_dir", "root_track"])
def test_escaping_track_resources_are_dropped(plugin_dir, outside, layout):
    track_dir = plugin_dir / "tracks" / "good" if layout == "tracks_dir" else plugin_dir
    track_dir.mkdir(parents=True, exist_ok=True)
    (track_dir / "TRACK.md").write_text(TRACK.format(name="good"))
    (track_dir / "scripts").mkdir()
    (track_dir / "scripts" / "ok.sh").write_text("echo ok")
    (outside / "secret.sh").write_text("echo secret")
    (track_dir / "scripts" / "evil.sh").symlink_to(outside / "secret.sh")
    (outside / "refs").mkdir()
    (outside / "refs" / "leak.md").write_text("leak")
    (track_dir / "references").symlink_to(outside / "refs", target_is_directory=True)

    [track] = HaijunCodePluginFormat().load_tracks(plugin_dir)

    assert track.resources is not None
    assert track.resources.scripts == ["ok.sh"]
    assert track.resources.references == []
