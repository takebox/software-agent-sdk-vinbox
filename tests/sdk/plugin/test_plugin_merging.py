"""Tests for plugin merging utilities."""

import pytest

from handprint.sdk.context import AgentContext
from handprint.sdk.mcp.config import MCPServer
from handprint.sdk.plugin import Plugin, PluginManifest
from handprint.sdk.tracks import Track


def mcp_config(
    servers: dict[str, MCPServer] | None = None,
) -> dict[str, MCPServer]:
    return servers or {}


class TestPluginAddTracksTo:
    """Tests for Plugin.add_tracks_to() method."""

    def test_add_tracks_to_empty_plugin(self, empty_plugin):
        """Test adding tracks from empty plugin returns unchanged context."""
        context = AgentContext(tracks=[])
        new_context = empty_plugin.add_tracks_to(context)
        assert new_context.tracks == []

    def test_add_tracks_to_none_context_empty_plugin(self, empty_plugin):
        """Test adding tracks with None context and empty plugin."""
        new_context = empty_plugin.add_tracks_to(None)
        assert isinstance(new_context, AgentContext)
        assert new_context.tracks == []

    def test_add_tracks_to_none_input(self, mock_plugin_with_tracks):
        """Test adding tracks with None input creates new context."""
        new_context = mock_plugin_with_tracks.add_tracks_to()
        assert isinstance(new_context, AgentContext)
        assert len(new_context.tracks) > 0

    def test_add_tracks_to_with_tracks(self, mock_plugin_with_tracks):
        """Test adding plugin tracks to context."""
        context = AgentContext(tracks=[])
        new_context = mock_plugin_with_tracks.add_tracks_to(context)
        assert len(new_context.tracks) == len(mock_plugin_with_tracks.tracks)

    def test_add_tracks_to_adds_new_track(self, mock_track, another_mock_track):
        """Test adding tracks adds new track when no conflict."""
        plugin = Plugin(
            manifest=PluginManifest(name="test", version="1.0.0", description="Test"),
            path="/tmp/test",
            tracks=[another_mock_track],
        )
        context = AgentContext(tracks=[mock_track])
        new_context = plugin.add_tracks_to(context)
        assert len(new_context.tracks) == 2
        track_names = {s.name for s in new_context.tracks}
        assert track_names == {mock_track.name, another_mock_track.name}

    def test_add_tracks_to_overrides_existing_track(self):
        """Test plugin track overrides existing track with same name."""
        original_track = Track(name="test-track", content="Original content")
        updated_track = Track(name="test-track", content="Updated content")
        plugin = Plugin(
            manifest=PluginManifest(name="test", version="1.0.0", description="Test"),
            path="/tmp/test",
            tracks=[updated_track],
        )
        context = AgentContext(tracks=[original_track])
        new_context = plugin.add_tracks_to(context)
        assert len(new_context.tracks) == 1
        assert new_context.tracks[0].content == "Updated content"

    def test_add_tracks_to_preserves_insertion_order(self):
        """Test add_tracks_to preserves order of existing tracks."""
        track_a = Track(name="track-a", content="A")
        track_b = Track(name="track-b", content="B")
        track_c = Track(name="track-c", content="C")
        plugin = Plugin(
            manifest=PluginManifest(name="test", version="1.0.0", description="Test"),
            path="/tmp/test",
            tracks=[track_c],
        )
        context = AgentContext(tracks=[track_a, track_b])
        new_context = plugin.add_tracks_to(context)
        track_names = [s.name for s in new_context.tracks]
        assert track_names == ["track-a", "track-b", "track-c"]

    def test_add_tracks_to_returns_new_context(self, mock_track):
        """Test add_tracks_to returns new context instance, not modifying original."""
        new_track = Track(name="new-track", content="New")
        plugin = Plugin(
            manifest=PluginManifest(name="test", version="1.0.0", description="Test"),
            path="/tmp/test",
            tracks=[new_track],
        )
        original_context = AgentContext(tracks=[mock_track])
        new_context = plugin.add_tracks_to(original_context)
        # Original context should be unchanged
        assert len(original_context.tracks) == 1
        assert len(new_context.tracks) == 2
        assert new_context is not original_context

    def test_add_tracks_to_enforces_max_tracks(self, mock_plugin_with_tracks):
        """Test add_tracks_to enforces max_tracks limit."""
        context = AgentContext(tracks=[])
        with pytest.raises(ValueError, match="exceeds maximum"):
            mock_plugin_with_tracks.add_tracks_to(context, max_tracks=0)

    def test_add_tracks_to_max_tracks_with_existing(self, mock_track):
        """Test max_tracks counts unique tracks after merge."""
        plugin_track_1 = Track(name="plugin-track-1", content="P1")
        plugin_track_2 = Track(name="plugin-track-2", content="P2")
        plugin = Plugin(
            manifest=PluginManifest(name="test", version="1.0.0", description="Test"),
            path="/tmp/test",
            tracks=[plugin_track_1, plugin_track_2],
        )
        context = AgentContext(tracks=[mock_track])

        # Limit of 3 should allow merge (1 existing + 2 new = 3)
        new_context = plugin.add_tracks_to(context, max_tracks=3)
        assert len(new_context.tracks) == 3

        # Limit of 2 should fail (3 > 2)
        with pytest.raises(ValueError, match="exceeds maximum"):
            plugin.add_tracks_to(context, max_tracks=2)

    def test_add_tracks_to_max_tracks_with_override(self):
        """Test max_tracks counts correctly when plugin overrides existing track."""
        existing_track = Track(name="shared-track", content="Old")
        context = AgentContext(tracks=[existing_track])

        plugin_track = Track(name="shared-track", content="New")
        plugin = Plugin(
            manifest=PluginManifest(name="test", version="1.0.0", description="Test"),
            path="/tmp/test",
            tracks=[plugin_track],
        )

        new_context = plugin.add_tracks_to(context, max_tracks=1)
        assert len(new_context.tracks) == 1
        assert new_context.tracks[0].content == "New"

    def test_add_tracks_to_preserves_context_fields(self, mock_plugin_with_tracks):
        """Test add_tracks_to preserves other AgentContext fields."""
        context = AgentContext(
            tracks=[],
            system_message_suffix="Custom suffix",
        )
        new_context = mock_plugin_with_tracks.add_tracks_to(context)
        assert new_context.system_message_suffix == context.system_message_suffix


class TestPluginAddMcpConfigTo:
    """Tests for Plugin.add_mcp_config_to() method."""

    def test_add_mcp_config_to_empty_plugin(self, empty_plugin):
        """Test adding MCP servers from empty plugin returns an empty map."""
        new_mcp = empty_plugin.add_mcp_config_to(mcp_config())
        assert new_mcp == {}

    def test_add_mcp_config_to_both_none(self, empty_plugin):
        """Test adding MCP servers with both None returns an empty map."""
        new_mcp = empty_plugin.add_mcp_config_to(None)
        assert new_mcp == {}

    def test_add_mcp_config_to_none_input(self, mock_plugin_with_mcp):
        """Test adding MCP servers with None input."""
        new_mcp = mock_plugin_with_mcp.add_mcp_config_to()
        assert new_mcp == mock_plugin_with_mcp.mcp_config

    def test_add_mcp_config_to_with_config(self, mock_plugin_with_mcp):
        """Test adding plugin MCP servers."""
        new_mcp = mock_plugin_with_mcp.add_mcp_config_to(mcp_config())
        assert new_mcp == mock_plugin_with_mcp.mcp_config

    def test_add_mcp_config_to_merges_servers(self):
        """Test add_mcp_config_to returns correctly merged MCP servers."""
        base_mcp = mcp_config({"server1": MCPServer(command="base")})
        plugin_mcp = mcp_config({"server2": MCPServer(command="plugin")})

        plugin = Plugin(
            manifest=PluginManifest(name="test", version="1.0.0", description="Test"),
            path="/tmp/test",
            mcp_config=plugin_mcp,
        )

        new_mcp = plugin.add_mcp_config_to(base_mcp)

        assert new_mcp["server1"].command == "base"
        assert new_mcp["server2"].command == "plugin"

    def test_add_mcp_config_to_plugin_overrides(self):
        """Test plugin MCP servers override base servers for same key."""
        base_mcp = mcp_config(
            {"server1": MCPServer(command="python", args=["-m", "base_server"])}
        )
        plugin_mcp = mcp_config(
            {"server1": MCPServer(command="python", args=["-m", "plugin_server"])}
        )

        plugin = Plugin(
            manifest=PluginManifest(name="test", version="1.0.0", description="Test"),
            path="/tmp/test",
            mcp_config=plugin_mcp,
        )

        new_mcp = plugin.add_mcp_config_to(base_mcp)
        assert new_mcp["server1"].args == ["-m", "plugin_server"]

    def test_add_mcp_config_to_does_not_modify_inputs(self):
        """Test add_mcp_config_to does not modify input maps."""
        base_mcp = mcp_config({"server1": MCPServer(command="python")})
        plugin_mcp = mcp_config({"server2": MCPServer(command="node")})
        original_base = dict(base_mcp)
        original_plugin = dict(plugin_mcp)

        plugin = Plugin(
            manifest=PluginManifest(name="test", version="1.0.0", description="Test"),
            path="/tmp/test",
            mcp_config=plugin_mcp,
        )

        plugin.add_mcp_config_to(base_mcp)

        assert base_mcp == original_base
        assert plugin_mcp == original_plugin

    def test_add_mcp_config_to_merges_mcp_config(self):
        """Test add_mcp_config_to merges native server maps by server name."""
        base_mcp = mcp_config({"server1": MCPServer(command="base")})
        plugin_mcp = mcp_config({"server2": MCPServer(command="plugin")})

        plugin = Plugin(
            manifest=PluginManifest(name="test", version="1.0.0", description="Test"),
            path="/tmp/test",
            mcp_config=plugin_mcp,
        )

        new_mcp = plugin.add_mcp_config_to(base_mcp)

        assert "server1" in new_mcp
        assert "server2" in new_mcp

    def test_add_mcp_config_to_mcp_config_plugin_overrides(self):
        """Test plugin MCP config overrides base config for the same server name."""
        base_mcp = mcp_config({"server1": MCPServer(command="base")})
        plugin_mcp = mcp_config({"server1": MCPServer(command="plugin")})

        plugin = Plugin(
            manifest=PluginManifest(name="test", version="1.0.0", description="Test"),
            path="/tmp/test",
            mcp_config=plugin_mcp,
        )

        new_mcp = plugin.add_mcp_config_to(base_mcp)

        assert new_mcp["server1"].command == "plugin"


# Fixtures


@pytest.fixture
def mock_track():
    """Create a mock track for testing."""
    return Track(
        name="test-track",
        content="Test track content",
    )


@pytest.fixture
def another_mock_track():
    """Create another mock track for testing."""
    return Track(
        name="another-track",
        content="Another track content",
    )


@pytest.fixture
def empty_plugin():
    """Create an empty plugin."""
    return Plugin(
        manifest=PluginManifest(
            name="empty", version="1.0.0", description="Empty plugin"
        ),
        path="/tmp/empty",
    )


@pytest.fixture
def mock_plugin_with_tracks(mock_track, another_mock_track):
    """Create a plugin with tracks."""
    return Plugin(
        manifest=PluginManifest(
            name="test-plugin", version="1.0.0", description="Test plugin"
        ),
        path="/tmp/test",
        tracks=[mock_track, another_mock_track],
    )


@pytest.fixture
def mock_plugin_with_mcp():
    """Create a plugin with MCP servers."""
    return Plugin(
        manifest=PluginManifest(
            name="mcp-plugin", version="1.0.0", description="MCP plugin"
        ),
        path="/tmp/mcp",
        mcp_config=mcp_config(
            {"server1": MCPServer(command="python", args=["-m", "server1"])}
        ),
    )
