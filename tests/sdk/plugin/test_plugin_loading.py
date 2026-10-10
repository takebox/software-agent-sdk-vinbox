"""Tests for Plugin loading functionality."""

from pathlib import Path

import pytest

from handprint.sdk.mcp.config import dump_mcp_config
from handprint.sdk.plugin import (
    HaijunCodePluginFormat,
    Plugin,
    PluginManifest,
    detect_format,
)
from handprint.sdk.plugin.types import (
    CommandDefinition,
    PluginAuthor,
)


class TestPluginManifest:
    """Tests for PluginManifest parsing."""

    def test_basic_manifest(self):
        """Test parsing a basic manifest."""
        manifest = PluginManifest(
            name="test-plugin",
            version="1.0.0",
            description="A test plugin",
        )
        assert manifest.name == "test-plugin"
        assert manifest.version == "1.0.0"
        assert manifest.description == "A test plugin"
        assert manifest.author is None

    def test_manifest_with_author_object(self):
        """Test parsing manifest with author as object."""
        from handprint.sdk.plugin.types import PluginAuthor

        manifest = PluginManifest(
            name="test-plugin",
            author=PluginAuthor(name="Test Author", email="test@example.com"),
        )
        assert manifest.author is not None
        assert manifest.author.name == "Test Author"
        assert manifest.author.email == "test@example.com"

    def test_manifest_with_entry_command(self):
        """Test parsing manifest with entry_command field."""
        manifest = PluginManifest(
            name="city-weather",
            version="1.0.0",
            entry_command="now",
        )
        assert manifest.name == "city-weather"
        assert manifest.entry_command == "now"

    def test_manifest_without_entry_command(self):
        """Test that entry_command defaults to None."""
        manifest = PluginManifest(name="test-plugin")
        assert manifest.entry_command is None


class TestPluginLoading:
    """Tests for Plugin.load() functionality."""

    def test_load_plugin_with_manifest(self, tmp_path: Path):
        """Test loading a plugin with a manifest file."""
        # Create plugin structure
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()

        # Write manifest
        manifest_file = manifest_dir / "plugin.json"
        manifest_file.write_text(
            """{
            "name": "test-plugin",
            "version": "2.0.0",
            "description": "A test plugin"
        }"""
        )

        # Load plugin
        plugin = Plugin.load(plugin_dir)

        assert plugin.name == "test-plugin"
        assert plugin.version == "2.0.0"
        assert plugin.description == "A test plugin"

    def test_load_plugin_with_haijun_plugin_dir(self, tmp_path: Path):
        """Test loading a plugin with .haijun-plugin directory."""
        plugin_dir = tmp_path / "haijun-plugin"
        plugin_dir.mkdir()
        manifest_dir = plugin_dir / ".haijun-plugin"
        manifest_dir.mkdir()

        manifest_file = manifest_dir / "plugin.json"
        manifest_file.write_text(
            """{
            "name": "haijun-plugin",
            "version": "1.0.0"
        }"""
        )

        plugin = Plugin.load(plugin_dir)
        assert plugin.name == "haijun-plugin"

    def test_load_plugin_without_manifest(self, tmp_path: Path):
        """Test loading a plugin without manifest (infers from directory name)."""
        plugin_dir = tmp_path / "inferred-plugin"
        plugin_dir.mkdir()

        plugin = Plugin.load(plugin_dir)

        assert plugin.name == "inferred-plugin"
        assert plugin.version == "1.0.0"

    def test_load_plugin_with_tracks(self, tmp_path: Path):
        """Test loading a plugin with tracks."""
        plugin_dir = tmp_path / "track-plugin"
        plugin_dir.mkdir()

        # Create tracks directory
        tracks_dir = plugin_dir / "tracks"
        tracks_dir.mkdir()

        # Create a track
        track_dir = tracks_dir / "test-track"
        track_dir.mkdir()
        track_md = track_dir / "TRACK.md"
        track_md.write_text(
            """---
name: test-track
description: A test track
---

This is a test track content.
"""
        )

        plugin = Plugin.load(plugin_dir)

        assert len(plugin.tracks) == 1
        assert plugin.tracks[0].name == "test-track"

    def test_load_single_track_plugin_root_track_md(self, tmp_path: Path):
        """A TRACK.md at the plugin root loads as a single-track plugin.

        Mirrors Haijun Code's single-track-plugin behavior (v2.1.142+): when a
        plugin has no tracks/ directory, a root TRACK.md is loaded as the
        plugin's track. This is how standalone Agent Tracks are published as
        plugins without an extra nesting level.
        """
        plugin_dir = tmp_path / "solo-track"
        plugin_dir.mkdir()
        manifest_dir = plugin_dir / ".haijun-plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(
            '{"name": "solo-track", "version": "1.0.0"}'
        )
        (plugin_dir / "TRACK.md").write_text(
            """---
name: solo-track
description: A standalone track published as a single-track plugin.
---

Body of the solo track.
"""
        )

        plugin = Plugin.load(plugin_dir)

        assert plugin.name == "solo-track"
        assert len(plugin.tracks) == 1
        assert plugin.tracks[0].name == "solo-track"

    def test_load_single_track_plugin_without_manifest(self, tmp_path: Path):
        """Root TRACK.md loads even when plugin.json is absent."""
        plugin_dir = tmp_path / "inferred-solo"
        plugin_dir.mkdir()
        (plugin_dir / "TRACK.md").write_text(
            """---
name: inferred-solo
description: Root track with no manifest.
---

Body.
"""
        )

        plugin = Plugin.load(plugin_dir)

        assert plugin.name == "inferred-solo"
        assert len(plugin.tracks) == 1
        assert plugin.tracks[0].name == "inferred-solo"

    def test_tracks_dir_takes_precedence_over_root_track_md(self, tmp_path: Path):
        """When a tracks/ directory exists, it wins over a root TRACK.md.

        Matches Haijun Code: the root TRACK.md is only a fallback used when
        there is no tracks/ directory.
        """
        plugin_dir = tmp_path / "both"
        plugin_dir.mkdir()
        # Root TRACK.md that must be IGNORED because tracks/ exists.
        (plugin_dir / "TRACK.md").write_text(
            "---\nname: root-ignored\ndescription: should not load\n---\nbody\n"
        )
        track_dir = plugin_dir / "tracks" / "nested"
        track_dir.mkdir(parents=True)
        (track_dir / "TRACK.md").write_text(
            "---\nname: nested\ndescription: the real one\n---\nbody\n"
        )

        plugin = Plugin.load(plugin_dir)

        names = {s.name for s in plugin.tracks}
        assert names == {"nested"}
        assert "root-ignored" not in names

    def test_load_plugin_no_tracks_anywhere(self, tmp_path: Path):
        """A plugin with neither tracks/ nor a root TRACK.md loads zero tracks."""
        plugin_dir = tmp_path / "empty"
        plugin_dir.mkdir()
        (plugin_dir / "README.md").write_text("# not a track\n")

        plugin = Plugin.load(plugin_dir)

        assert plugin.tracks == []

    def test_tracks_dir_nested_md_and_relaxed_names(self, tmp_path: Path):
        """Nested .md files are track resources, not tracks; names are relaxed."""
        plugin_dir = tmp_path / "nested"
        track_dir = plugin_dir / "tracks" / "Summarize_Tool"
        (track_dir / "references").mkdir(parents=True)
        (track_dir / "TRACK.md").write_text(
            "---\nname: Summarize_Tool\ndescription: d\n---\nbody\n"
        )
        (track_dir / "references" / "notes.md").write_text("# notes\n")
        (plugin_dir / "tracks" / "shared").mkdir()
        (plugin_dir / "tracks" / "shared" / "notes.md").write_text("# notes\n")
        (plugin_dir / "tracks" / "loose.md").write_text("loose track\n")
        (plugin_dir / "tracks" / "readme.md").write_text("# readme\n")

        plugin = Plugin.load(plugin_dir)

        assert [s.name for s in plugin.tracks] == ["Summarize_Tool", "loose"]

    def test_tracks_dir_bad_track_skips_only_itself(self, tmp_path: Path):
        """A track that fails to load does not abort the remaining tracks."""
        plugin_dir = tmp_path / "partial"
        tracks_dir = plugin_dir / "tracks"
        (tracks_dir / "broken").mkdir(parents=True)
        (tracks_dir / "broken" / "TRACK.md").write_bytes(b"\xff\xfe\xfa")
        (tracks_dir / "good").mkdir()
        (tracks_dir / "good" / "TRACK.md").write_text(
            "---\nname: good\ndescription: d\n---\nbody\n"
        )

        plugin = Plugin.load(plugin_dir)

        assert [s.name for s in plugin.tracks] == ["good"]

    def test_load_plugin_with_hooks(self, tmp_path: Path):
        """Test loading a plugin with hooks."""
        plugin_dir = tmp_path / "hook-plugin"
        plugin_dir.mkdir()

        # Create hooks directory
        hooks_dir = plugin_dir / "hooks"
        hooks_dir.mkdir()

        # Create hooks.json
        hooks_json = hooks_dir / "hooks.json"
        hooks_json.write_text(
            """{
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "echo test"
                            }
                        ]
                    }
                ]
            }
        }"""
        )

        plugin = Plugin.load(plugin_dir)

        assert plugin.hooks is not None
        assert not plugin.hooks.is_empty()
        assert len(plugin.hooks.pre_tool_use) == 1

    def test_load_plugin_with_agents(self, tmp_path: Path):
        """Test loading a plugin with agent definitions."""
        plugin_dir = tmp_path / "agent-plugin"
        plugin_dir.mkdir()

        # Create agents directory
        agents_dir = plugin_dir / "agents"
        agents_dir.mkdir()

        # Create an agent
        agent_md = agents_dir / "test-agent.md"
        agent_md.write_text(
            """---
name: test-agent
description: A test agent. <example>When user asks about testing</example>
model: inherit
tools:
  - Read
  - Write
---

You are a test agent. Help users with testing.
"""
        )

        plugin = Plugin.load(plugin_dir)

        assert len(plugin.agents) == 1
        agent = plugin.agents[0]
        assert agent.name == "test-agent"
        assert agent.model == "inherit"
        assert "Read" in agent.tools
        assert "Write" in agent.tools
        assert len(agent.when_to_use_examples) == 1
        assert "When user asks about testing" in agent.when_to_use_examples[0]
        assert "You are a test agent" in agent.system_prompt

    def test_load_plugin_with_commands(self, tmp_path: Path):
        """Test loading a plugin with command definitions."""
        plugin_dir = tmp_path / "command-plugin"
        plugin_dir.mkdir()

        # Create commands directory
        commands_dir = plugin_dir / "commands"
        commands_dir.mkdir()

        # Create a command
        command_md = commands_dir / "review.md"
        command_md.write_text(
            """---
description: Review code changes
argument-hint: <file-or-directory>
allowed-tools:
  - Read
  - Grep
---

Review the specified code and provide feedback.
"""
        )

        plugin = Plugin.load(plugin_dir)

        assert len(plugin.commands) == 1
        command = plugin.commands[0]
        assert command.name == "review"
        assert command.description == "Review code changes"
        assert command.argument_hint == "<file-or-directory>"
        assert "Read" in command.allowed_tools
        assert "Review the specified code" in command.content

    def test_load_plugin_with_entry_command(self, tmp_path: Path):
        """Test loading a plugin with entry_command in manifest."""
        plugin_dir = tmp_path / "city-weather"
        plugin_dir.mkdir()
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()

        # Write manifest with entry_command
        manifest_file = manifest_dir / "plugin.json"
        manifest_file.write_text(
            """{
            "name": "city-weather",
            "version": "1.0.0",
            "description": "Get current weather for any city",
            "entry_command": "now"
        }"""
        )

        plugin = Plugin.load(plugin_dir)

        assert plugin.name == "city-weather"
        assert plugin.manifest.entry_command == "now"
        assert plugin.entry_slash_command == "/city-weather:now"

    def test_load_plugin_without_entry_command(self, tmp_path: Path):
        """Test that entry_slash_command returns None when no entry_command is set."""
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()

        plugin = Plugin.load(plugin_dir)

        assert plugin.manifest.entry_command is None
        assert plugin.entry_slash_command is None

    def test_command_to_track_conversion(self, tmp_path: Path):
        """Test converting a command to a keyword-triggered track."""
        from handprint.sdk.tracks.trigger import KeywordTrigger

        plugin_dir = tmp_path / "city-weather"
        plugin_dir.mkdir()
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()
        manifest_file = manifest_dir / "plugin.json"
        manifest_file.write_text('{"name": "city-weather", "version": "1.0.0"}')

        commands_dir = plugin_dir / "commands"
        commands_dir.mkdir()
        command_md = commands_dir / "now.md"
        command_md.write_text(
            """---
description: Get current weather for a city
argument-hint: <city-name>
allowed-tools:
  - tavily_search
---

Fetch and display the current weather for the specified city.
"""
        )

        plugin = Plugin.load(plugin_dir)
        assert len(plugin.commands) == 1

        # Convert command to track
        command = plugin.commands[0]
        track = command.to_track("city-weather")

        # Verify track properties
        assert track.name == "city-weather:now"
        assert track.description == "Get current weather for a city"
        assert track.allowed_tools is not None
        assert "tavily_search" in track.allowed_tools

        # Verify trigger format
        assert isinstance(track.trigger, KeywordTrigger)
        assert "/city-weather:now" in track.trigger.keywords

        # Verify content includes argument hint
        assert "$ARGUMENTS" in track.content
        assert "Fetch and display the current weather" in track.content

    def test_get_all_tracks_with_commands(self, tmp_path: Path):
        """Test get_all_tracks returns both tracks and command-derived tracks."""
        from handprint.sdk.tracks.trigger import KeywordTrigger

        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()
        manifest_file = manifest_dir / "plugin.json"
        manifest_file.write_text('{"name": "test-plugin", "version": "1.0.0"}')

        # Create tracks directory with a track
        tracks_dir = plugin_dir / "tracks"
        tracks_dir.mkdir()
        track_dir = tracks_dir / "my-track"
        track_dir.mkdir()
        track_md = track_dir / "TRACK.md"
        track_md.write_text(
            """---
name: my-track
description: A regular track
---

This is a regular track content.
"""
        )

        # Create commands directory with a command
        commands_dir = plugin_dir / "commands"
        commands_dir.mkdir()
        command_md = commands_dir / "greet.md"
        command_md.write_text(
            """---
description: Greet someone
argument-hint: <name>
---

Say hello to the specified person.
"""
        )

        plugin = Plugin.load(plugin_dir)

        # Verify separate counts
        assert len(plugin.tracks) == 1
        assert len(plugin.commands) == 1

        # Verify combined tracks
        all_tracks = plugin.get_all_tracks()
        assert len(all_tracks) == 2

        # Find the regular track and command-derived track
        track_names = {s.name for s in all_tracks}
        assert "my-track" in track_names
        assert "test-plugin:greet" in track_names

        # Verify command-derived track has keyword trigger
        command_track = next(s for s in all_tracks if s.name == "test-plugin:greet")
        assert isinstance(command_track.trigger, KeywordTrigger)
        assert "/test-plugin:greet" in command_track.trigger.keywords

    def test_get_all_tracks_empty_commands(self, tmp_path: Path):
        """Test get_all_tracks with no commands."""
        plugin_dir = tmp_path / "no-commands"
        plugin_dir.mkdir()

        # Create tracks directory with a track only
        tracks_dir = plugin_dir / "tracks"
        tracks_dir.mkdir()
        track_dir = tracks_dir / "only-track"
        track_dir.mkdir()
        track_md = track_dir / "TRACK.md"
        track_md.write_text(
            """---
name: only-track
description: The only track
---

Content for the only track.
"""
        )

        plugin = Plugin.load(plugin_dir)

        all_tracks = plugin.get_all_tracks()
        assert len(all_tracks) == 1
        assert all_tracks[0].name == "only-track"

    def test_load_all_plugins(self, tmp_path: Path):
        """Test loading all plugins from a directory."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        # Create multiple plugins
        for i in range(3):
            plugin_dir = plugins_dir / f"plugin-{i}"
            plugin_dir.mkdir()
            manifest_dir = plugin_dir / ".plugin"
            manifest_dir.mkdir()
            manifest_file = manifest_dir / "plugin.json"
            manifest_file.write_text(f'{{"name": "plugin-{i}"}}')

        plugins = Plugin.load_all(plugins_dir)

        assert len(plugins) == 3
        names = {p.name for p in plugins}
        assert names == {"plugin-0", "plugin-1", "plugin-2"}

    def test_load_nonexistent_plugin(self, tmp_path: Path):
        """Test loading a nonexistent plugin raises error."""
        with pytest.raises(FileNotFoundError):
            Plugin.load(tmp_path / "nonexistent")

    def test_load_plugin_with_invalid_manifest(self, tmp_path: Path):
        """Test loading a plugin with invalid manifest raises error."""
        plugin_dir = tmp_path / "invalid-plugin"
        plugin_dir.mkdir()
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()

        manifest_file = manifest_dir / "plugin.json"
        manifest_file.write_text("not valid json")

        with pytest.raises(ValueError, match="Invalid JSON"):
            Plugin.load(plugin_dir)

    def test_load_all_nonexistent_directory(self, tmp_path: Path):
        """Test load_all with nonexistent directory returns empty list."""
        plugins = Plugin.load_all(tmp_path / "nonexistent")
        assert plugins == []

    def test_load_all_with_failing_plugin(self, tmp_path: Path):
        """Test load_all continues when a plugin fails to load (lines 197-198)."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        # Create a valid plugin
        valid_dir = plugins_dir / "valid-plugin"
        valid_dir.mkdir()
        manifest_dir = valid_dir / ".plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text('{"name": "valid-plugin"}')

        # Create an invalid plugin (will fail to load)
        invalid_dir = plugins_dir / "invalid-plugin"
        invalid_dir.mkdir()
        invalid_manifest_dir = invalid_dir / ".plugin"
        invalid_manifest_dir.mkdir()
        (invalid_manifest_dir / "plugin.json").write_text("not valid json")

        plugins = Plugin.load_all(plugins_dir)

        # Should load the valid plugin and skip the invalid one
        assert len(plugins) == 1
        assert plugins[0].name == "valid-plugin"

    def test_load_plugin_with_author_string(self, tmp_path: Path):
        """Test loading manifest with author as string (line 225)."""
        plugin_dir = tmp_path / "author-plugin"
        plugin_dir.mkdir()
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()

        # Write manifest with author as string
        manifest_file = manifest_dir / "plugin.json"
        manifest_file.write_text(
            """{
            "name": "author-plugin",
            "version": "1.0.0",
            "author": "Test Author <test@example.com>"
        }"""
        )

        plugin = Plugin.load(plugin_dir)

        assert plugin.name == "author-plugin"
        assert plugin.manifest.author is not None
        assert plugin.manifest.author.name == "Test Author"
        assert plugin.manifest.author.email == "test@example.com"

    def test_load_plugin_with_manifest_parse_error(self, tmp_path: Path):
        """Test loading manifest with parse error (lines 230-231)."""
        plugin_dir = tmp_path / "error-plugin"
        plugin_dir.mkdir()
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()

        # Write manifest with missing required field or wrong type
        # This will parse as JSON but fail Pydantic validation
        manifest_file = manifest_dir / "plugin.json"
        manifest_file.write_text('{"name": 123}')  # name should be string

        with pytest.raises(ValueError, match="Failed to parse manifest"):
            Plugin.load(plugin_dir)


class TestPluginAuthor:
    """Tests for PluginAuthor parsing."""

    def test_from_string_with_email(self):
        """Test parsing author string with email (lines 22-25)."""
        author = PluginAuthor.from_string("John Doe <john@example.com>")
        assert author.name == "John Doe"
        assert author.email == "john@example.com"

    def test_from_string_without_email(self):
        """Test parsing author string without email (line 26)."""
        author = PluginAuthor.from_string("John Doe")
        assert author.name == "John Doe"
        assert author.email is None

    def test_from_string_with_whitespace(self):
        """Test parsing author string with extra whitespace."""
        author = PluginAuthor.from_string("  John Doe  <  john@example.com  >  ")
        assert author.name == "John Doe"
        assert author.email == "john@example.com"

    def test_with_url(self):
        """Test PluginAuthor with url field."""
        author = PluginAuthor(
            name="John Doe",
            email="john@example.com",
            url="https://github.com/johndoe",
        )
        assert author.name == "John Doe"
        assert author.email == "john@example.com"
        assert author.url == "https://github.com/johndoe"

    def test_url_defaults_to_none(self):
        """Test that url field defaults to None."""
        author = PluginAuthor(name="John Doe")
        assert author.url is None


class TestCommandDefinition:
    """Tests for CommandDefinition loading."""

    def test_load_command_basic(self, tmp_path: Path):
        """Test loading a basic command definition (lines 184-218)."""
        command_md = tmp_path / "review.md"
        command_md.write_text(
            """---
description: Review code
argument-hint: <file>
allowed-tools:
  - Read
  - Grep
---

Review the specified file.
"""
        )

        command = CommandDefinition.load(command_md)

        assert command.name == "review"
        assert command.description == "Review code"
        assert command.argument_hint == "<file>"
        assert command.allowed_tools == ["Read", "Grep"]
        assert command.content == "Review the specified file."

    def test_load_command_with_argument_hint_list(self, tmp_path: Path):
        """Test loading command with argument-hint as list."""
        command_md = tmp_path / "multi-arg.md"
        command_md.write_text(
            """---
description: Multi arg command
argument-hint:
  - <file>
  - <options>
---

Content.
"""
        )

        command = CommandDefinition.load(command_md)
        assert command.argument_hint == "<file> <options>"

    def test_load_command_with_camel_case_fields(self, tmp_path: Path):
        """Test loading command with camelCase field names."""
        command_md = tmp_path / "camel.md"
        command_md.write_text(
            """---
description: Camel case command
argumentHint: <arg>
allowedTools:
  - Tool1
---

Content.
"""
        )

        command = CommandDefinition.load(command_md)
        assert command.argument_hint == "<arg>"
        assert command.allowed_tools == ["Tool1"]

    def test_load_command_with_allowed_tools_as_string(self, tmp_path: Path):
        """Test loading command with allowed-tools as string."""
        command_md = tmp_path / "single-tool.md"
        command_md.write_text(
            """---
description: Single tool
allowed-tools: Read
---

Content.
"""
        )

        command = CommandDefinition.load(command_md)
        assert command.allowed_tools == ["Read"]

    def test_load_command_defaults(self, tmp_path: Path):
        """Test command defaults when fields not provided."""
        command_md = tmp_path / "minimal.md"
        command_md.write_text(
            """---
---

Just instructions.
"""
        )

        command = CommandDefinition.load(command_md)
        assert command.name == "minimal"
        assert command.description == ""
        assert command.argument_hint is None
        assert command.allowed_tools == []

    def test_load_command_with_metadata(self, tmp_path: Path):
        """Test loading command with extra metadata."""
        command_md = tmp_path / "meta.md"
        command_md.write_text(
            """---
description: Meta command
custom_field: custom_value
---

Content.
"""
        )

        command = CommandDefinition.load(command_md)
        assert command.metadata.get("custom_field") == "custom_value"


class TestPluginMcpConfigLoading:
    """Tests for Plugin MCP config loading and variable expansion.

    These tests verify that MCP config variables are handled correctly
    during plugin loading, specifically that variables with defaults
    are NOT prematurely expanded.
    """

    def test_plugin_mcp_config_preserve_unexpanded_variables(self, tmp_path: Path):
        """Test that MCP server variables WITHOUT defaults are preserved.

        Variables like ${VAR} should remain as placeholders after plugin loading
        so they can be expanded later with per-conversation secrets.
        """
        import json

        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()

        # Create minimal manifest
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(
            json.dumps({"name": "test-plugin", "version": "1.0.0"})
        )

        # Create MCP config with unexpanded variable (no default)
        mcp_json = plugin_dir / ".mcp.json"
        mcp_json.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "test-server": {
                            "url": "https://example.com",
                            "headers": {"Authorization": "Bearer ${SECRET_TOKEN}"},
                        }
                    }
                }
            )
        )

        plugin = Plugin.load(plugin_dir)

        # Variable without default should remain as placeholder
        auth_header = dump_mcp_config(plugin.mcp_config)["test-server"]["headers"][
            "Authorization"
        ]
        assert auth_header == "Bearer ${SECRET_TOKEN}", (
            f"Expected placeholder to be preserved, got '{auth_header}'"
        )

    def test_plugin_mcp_config_preserve_variables_with_defaults(self, tmp_path: Path):
        """Test that MCP server variables WITH defaults are preserved as placeholders.

        Variables like ${VAR:-default} should remain as placeholders after plugin
        loading so they can be expanded later with per-conversation secrets.

        This is a regression test for the double-expansion bug where variables
        with defaults were prematurely replaced with their default values during
        plugin loading.

        Expected: The placeholder ${VAR:-default} should be preserved, NOT replaced
        with the default value during plugin loading.
        """
        import json

        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()

        # Create minimal manifest
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(
            json.dumps({"name": "test-plugin", "version": "1.0.0"})
        )

        # Create MCP config with variable that has a default
        mcp_json = plugin_dir / ".mcp.json"
        mcp_json.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "test-server": {
                            "url": "https://example.com",
                            "headers": {
                                "Authorization": "Bearer ${SECRET_TOKEN:-fallback}"
                            },
                        }
                    }
                }
            )
        )

        plugin = Plugin.load(plugin_dir)

        # CRITICAL: Variable with default should be preserved as a placeholder,
        # NOT replaced with "fallback" during plugin loading
        auth_header = dump_mcp_config(plugin.mcp_config)["test-server"]["headers"][
            "Authorization"
        ]

        # This assertion will FAIL with the current implementation
        expected = "Bearer ${SECRET_TOKEN:-fallback}"
        assert auth_header == expected, (
            f"Expected placeholder '{expected}' to be preserved, "
            f"but got '{auth_header}'. "
            "This is the double-expansion bug: the default value was applied "
            "during plugin loading instead of being deferred."
        )

    def test_plugin_mcp_config_drops_unknown_server_fields(self, tmp_path: Path):
        """Plugin .mcp.json loading tolerates fields from newer MCP schemas."""
        import json

        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()

        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(
            json.dumps({"name": "test-plugin", "version": "1.0.0"})
        )

        (plugin_dir / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "test-server": {
                            "type": "shttp",
                            "url": "https://example.com/mcp",
                            "future_field": "ignored",
                        }
                    }
                }
            )
        )

        plugin = Plugin.load(plugin_dir)

        assert dump_mcp_config(plugin.mcp_config) == {
            "test-server": {
                "transport": "http",
                "url": "https://example.com/mcp",
            }
        }

    def test_plugin_mcp_track_root_is_expanded(self, tmp_path: Path):
        """Test that TRACK_ROOT is correctly expanded during plugin loading.

        ${TRACK_ROOT} is a special variable that should be expanded to the
        plugin directory path during loading.
        """
        import json

        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()

        # Create minimal manifest
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(
            json.dumps({"name": "test-plugin", "version": "1.0.0"})
        )

        # Create MCP config with TRACK_ROOT variable
        mcp_json = plugin_dir / ".mcp.json"
        mcp_json.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "test-server": {
                            "command": "${TRACK_ROOT}/scripts/server.py",
                        }
                    }
                }
            )
        )

        plugin = Plugin.load(plugin_dir)

        # TRACK_ROOT should be expanded to the plugin directory
        command = dump_mcp_config(plugin.mcp_config)["test-server"]["command"]
        assert str(plugin_dir) in command
        assert "${TRACK_ROOT}" not in command


class TestRootTrackMcpHandling:
    """Tests for proper MCP config handling in root TRACK.md plugins.

    These tests verify the fix for issues where root .mcp.json files were
    being loaded twice with different semantics, causing failures and
    inconsistencies.
    """

    def test_malformed_root_mcp_json_does_not_drop_track(self, tmp_path: Path):
        """Issue #1: Malformed root .mcp.json should not silently drop the track.

        Before fix: Plugin-level loader tolerates malformed .mcp.json (logs warning),
        but track-level loader raises TrackValidationError, caught by broad except,
        returning [] - track silently dropped.

        After fix: skip_mcp=True prevents double-loading, track loads successfully.
        """
        import json

        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()

        # Create minimal manifest
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(
            json.dumps({"name": "test-plugin", "version": "1.0.0"})
        )

        # Create valid root TRACK.md
        (plugin_dir / "TRACK.md").write_text(
            """---
name: test-track
description: A test track
---

# Test Track

This is a test track.
"""
        )

        # Create MALFORMED root .mcp.json (invalid JSON)
        (plugin_dir / ".mcp.json").write_text('{ "mcpServers": { invalid json }')

        # Load the plugin
        plugin = Plugin.load(plugin_dir)

        # The track should still load (MCP loading is skipped for root tracks)
        assert len(plugin.tracks) == 1
        assert plugin.tracks[0].name == "test-track"
        # Plugin-level MCP config should be empty (malformed file tolerated)
        assert plugin.mcp_config == {}

    def test_root_mcp_json_not_double_loaded(self, tmp_path: Path):
        """Issue #2: Root .mcp.json should not be loaded twice with different semantics.

        Before fix: Same file loaded by both _load_plugin_mcp_config
        (expand_defaults=False) and Track.load (expand_defaults=True).

        After fix: Only loaded once at plugin level, track uses skip_mcp=True.
        """
        import json

        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()

        # Create minimal manifest
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(
            json.dumps({"name": "test-plugin", "version": "1.0.0"})
        )

        # Create root TRACK.md
        (plugin_dir / "TRACK.md").write_text(
            """---
name: test-track
description: A test track
---

# Test Track
"""
        )

        # Create root .mcp.json with variable placeholder
        (plugin_dir / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "test-server": {
                            "command": "server",
                            "args": ["--token", "${DB_TOKEN:-DEFAULT_TOKEN}"],
                        }
                    }
                }
            )
        )

        # Load the plugin
        plugin = Plugin.load(plugin_dir)

        # Plugin-level MCP preserves placeholders (expand_defaults=False)
        mcp_dump = dump_mcp_config(plugin.mcp_config)
        assert "${DB_TOKEN:-DEFAULT_TOKEN}" in mcp_dump["test-server"]["args"]

        # Track should have loaded successfully with skip_mcp=True
        assert len(plugin.tracks) == 1
        assert plugin.tracks[0].name == "test-track"
        # Track's mcp_tools should be None (not loaded due to skip_mcp=True)
        assert plugin.tracks[0].mcp_tools is None

    def test_root_track_resources_not_duplicated(self, tmp_path: Path):
        """Issue #3: Resources should not be discovered twice for root tracks.

        Before fix: discover_track_resources called both by Track.load() and
        by plugin loader (redundant).

        After fix: Only Track.load() discovers resources, plugin loader doesn't
        call discover_track_resources.
        """
        import json

        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()

        # Create minimal manifest
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(
            json.dumps({"name": "test-plugin", "version": "1.0.0"})
        )

        # Create root TRACK.md
        (plugin_dir / "TRACK.md").write_text(
            """---
name: test-track
description: A test track
---

# Test Track
"""
        )

        # Create some resources
        (plugin_dir / "test.txt").write_text("test resource")
        assets_dir = plugin_dir / "assets"
        assets_dir.mkdir()
        (assets_dir / "asset.txt").write_text("asset content")

        # Load the plugin
        plugin = Plugin.load(plugin_dir)

        # Resources should be discovered and attached
        assert len(plugin.tracks) == 1
        assert plugin.tracks[0].resources is not None
        assert plugin.tracks[0].resources.assets == ["asset.txt"]
        # This test passes if no exception is raised - the fix prevents the
        # redundant call but the end result is the same

    def test_nested_track_with_own_mcp_json_still_loads(self, tmp_path: Path):
        """Verify nested tracks with their own .mcp.json still work correctly.

        Nested tracks should continue to load their own .mcp.json normally
        (not skipped) since they're in a different directory than the plugin root.
        """
        import json

        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()

        # Create minimal manifest
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(
            json.dumps({"name": "test-plugin", "version": "1.0.0"})
        )

        # Create nested track with its own .mcp.json
        tracks_dir = plugin_dir / "tracks"
        tracks_dir.mkdir()
        track_dir = tracks_dir / "nested-track"
        track_dir.mkdir()

        (track_dir / "TRACK.md").write_text(
            """---
name: nested-track
description: A nested track
---

# Nested Track
"""
        )

        (track_dir / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "nested-server": {
                            "command": "nested-server",
                        }
                    }
                }
            )
        )

        # Load the plugin
        plugin = Plugin.load(plugin_dir)

        # Track should load with its own MCP config
        assert len(plugin.tracks) == 1
        assert plugin.tracks[0].name == "nested-track"
        # Nested track SHOULD have mcp_tools (not skipped)
        assert plugin.tracks[0].mcp_tools is not None
        assert "nested-server" in plugin.tracks[0].mcp_tools


class TestDetectFormat:
    """Tests for the plugin-format selection contract (detect_format()).

    detect_format() is the seam that decides which PluginFormat loads a plugin
    directory. Today only the Haijun Code layout is registered, so it is the
    fallback for every directory; these tests pin that precedence so the future
    Agent Plugins format (root plugin.json) can be slotted ahead of it without
    silently changing the Haijun Code behavior.
    """

    def test_detects_haijun_code_for_nested_manifest(self, tmp_path: Path):
        """A directory with a nested .haijun-plugin manifest selects Haijun Code."""
        plugin_dir = tmp_path / "with-manifest"
        manifest_dir = plugin_dir / ".haijun-plugin"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "plugin.json").write_text('{"name": "with-manifest"}')

        fmt = detect_format(plugin_dir)

        assert isinstance(fmt, HaijunCodePluginFormat)
        assert fmt.name == "haijun-code"

    def test_detects_haijun_code_for_bare_dir(self, tmp_path: Path):
        """A directory with no manifest still falls back to Haijun Code."""
        plugin_dir = tmp_path / "bare-plugin"
        plugin_dir.mkdir()

        assert isinstance(detect_format(plugin_dir), HaijunCodePluginFormat)

    def test_detected_format_loads_equivalent_plugin(self, tmp_path: Path):
        """The strategy from detect_format() loads the same plugin as Plugin.load()."""
        plugin_dir = tmp_path / "roundtrip"
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "plugin.json").write_text(
            '{"name": "roundtrip", "version": "3.1.4"}'
        )

        # Plugin.load() must resolve first: the strategy operates on the resolved
        # dir, and path is stored resolved on the returned Plugin.
        resolved_dir = plugin_dir.resolve()
        via_strategy = detect_format(resolved_dir).load(resolved_dir)
        via_load = Plugin.load(plugin_dir)

        assert via_strategy.name == via_load.name == "roundtrip"
        assert via_strategy.version == via_load.version == "3.1.4"
        assert via_strategy.path == via_load.path

    def test_strategy_load_raises_for_missing_dir(self, tmp_path: Path):
        """The direct strategy API guards a missing dir, like Plugin.load()."""
        missing = tmp_path / "does-not-exist"

        with pytest.raises(FileNotFoundError):
            detect_format(missing).load(missing)

    def test_subclass_without_name_is_rejected(self):
        """A PluginFormat subclass must declare a class-level ``name``."""
        from handprint.sdk.plugin.format.base import PluginFormat

        with pytest.raises(TypeError, match="name"):

            class _NamelessFormat(PluginFormat):  # pyright: ignore[reportUnusedClass]
                @classmethod
                def detect(cls, plugin_dir: Path) -> bool:
                    return False

                def load_manifest(self, plugin_dir: Path) -> PluginManifest:
                    raise NotImplementedError

                def load_mcp_config(self, plugin_dir: Path):
                    raise NotImplementedError

                def load_hooks(self, plugin_dir: Path):
                    raise NotImplementedError

                def load_agents(self, plugin_dir: Path):
                    raise NotImplementedError

                def load_commands(self, plugin_dir: Path):
                    raise NotImplementedError
