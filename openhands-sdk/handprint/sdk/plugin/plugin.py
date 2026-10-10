"""Plugin class for loading and managing plugins.

``Plugin`` is the format-neutral, in-memory model plus its format-agnostic
behavior (merging tracks / MCP config into an agent). Reading a plugin directory
off disk is delegated to a :class:`~handprint.sdk.plugin.format.PluginFormat`
strategy (see ``format.py``); ``Plugin.load()`` is a thin dispatcher that detects
the on-disk format and returns a normalized ``Plugin``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from handprint.sdk.hooks import HookConfig
from handprint.sdk.logger import get_logger
from handprint.sdk.mcp.config import MCPServer
from handprint.sdk.plugin.fetch import fetch_plugin
from handprint.sdk.plugin.format import detect_format
from handprint.sdk.plugin.types import (
    CommandDefinition,
    PluginManifest,
)
from handprint.sdk.tracks.track import Track
from handprint.sdk.subagent.schema import AgentDefinition


if TYPE_CHECKING:
    from handprint.sdk.context import AgentContext

logger = get_logger(__name__)


class Plugin(BaseModel):
    """A plugin that bundles tracks, hooks, MCP config, agents, and commands.

    Plugins follow the Haijun Code plugin structure for compatibility:

    ```
    plugin-name/
    ├── .haijun-plugin/           # or .plugin/
    │   └── plugin.json          # Plugin metadata
    ├── commands/                # Slash commands (optional)
    ├── agents/                  # Specialized agents (optional)
    ├── tracks/                  # Agent Tracks (optional)
    ├── hooks/                   # Event handlers (optional)
    │   └── hooks.json
    ├── .mcp.json                # External tool configuration (optional)
    └── README.md                # Plugin documentation
    ```
    """

    manifest: PluginManifest = Field(description="Plugin manifest from plugin.json")
    path: str = Field(description="Path to the plugin directory")
    tracks: list[Track] = Field(
        default_factory=list, description="Tracks loaded from tracks/ directory"
    )
    hooks: HookConfig | None = Field(
        default=None, description="Hook configuration from hooks/hooks.json"
    )
    mcp_config: dict[str, MCPServer] = Field(
        default_factory=dict, description="MCP servers from .mcp.json"
    )
    agents: list[AgentDefinition] = Field(
        default_factory=list, description="Agent definitions from agents/ directory"
    )
    commands: list[CommandDefinition] = Field(
        default_factory=list, description="Command definitions from commands/ directory"
    )

    @property
    def name(self) -> str:
        """Get the plugin name."""
        return self.manifest.name

    @property
    def version(self) -> str:
        """Get the plugin version."""
        return self.manifest.version

    @property
    def description(self) -> str:
        """Get the plugin description."""
        return self.manifest.description

    @property
    def entry_slash_command(self) -> str | None:
        """Get the full slash command for the entry point, if defined.

        Returns the slash command in format /<plugin-name>:<command-name>,
        or None if no entry_command is defined in the manifest.

        Example:
            >>> plugin = Plugin.load(path)
            >>> plugin.entry_slash_command
            '/city-weather:now'
        """
        if not self.manifest.entry_command:
            return None
        return f"/{self.name}:{self.manifest.entry_command}"

    def get_all_tracks(self) -> list[Track]:
        """Get all tracks including those converted from commands.

        Returns tracks from both the tracks/ directory and commands/ directory.
        Commands are converted to keyword-triggered tracks using the format
        /<plugin-name>:<command-name>.

        Returns:
            Combined list of tracks (original + command-derived tracks).
        """
        all_tracks = list(self.tracks)

        # Convert commands to tracks with keyword triggers
        for command in self.commands:
            track = command.to_track(self.name)
            all_tracks.append(track)

        return all_tracks

    def add_tracks_to(
        self,
        agent_context: AgentContext | None = None,
        max_tracks: int | None = None,
    ) -> AgentContext:
        """Add this plugin's tracks to an agent context.

        Plugin tracks override existing tracks with the same name.
        Includes both explicit tracks and command-derived tracks.

        Args:
            agent_context: Existing agent context (or None to create new)
            max_tracks: Optional max total tracks (raises ValueError if exceeded)

        Returns:
            New AgentContext with this plugin's tracks added

        Raises:
            ValueError: If max_tracks limit would be exceeded

        Example:
            >>> plugin = Plugin.load(Plugin.fetch("github:owner/plugin"))
            >>> new_context = plugin.add_tracks_to(agent.agent_context, max_tracks=100)
            >>> agent = agent.model_copy(update={"agent_context": new_context})
        """
        # Import at runtime to avoid circular import
        from handprint.sdk.context import AgentContext

        existing_tracks = agent_context.tracks if agent_context else []

        # Get all tracks including command-derived tracks
        all_tracks = self.get_all_tracks()

        tracks_by_name = {s.name: s for s in existing_tracks}
        for track in all_tracks:
            if track.name in tracks_by_name:
                logger.warning(f"Plugin track '{track.name}' overrides existing track")
            tracks_by_name[track.name] = track

        if max_tracks is not None and len(tracks_by_name) > max_tracks:
            raise ValueError(
                f"Total tracks ({len(tracks_by_name)}) exceeds maximum ({max_tracks})"
            )

        merged_tracks = list(tracks_by_name.values())

        if agent_context:
            return agent_context.model_copy(update={"tracks": merged_tracks})
        return AgentContext(tracks=merged_tracks)

    def add_mcp_config_to(
        self,
        mcp_config: dict[str, MCPServer] | None = None,
    ) -> dict[str, MCPServer]:
        """Add this plugin's MCP config to an MCP config map.

        Plugin MCP servers override existing servers with the same name.

        Merge semantics: servers are merged by server name, and the
        plugin wins when the same server is present in both configs.

        Args:
            mcp_config: Existing MCP servers (or None to create a new map)

        Returns:
            New MCP server map with this plugin's servers added

        Example:
            >>> plugin = Plugin.load(Plugin.fetch("github:owner/plugin"))
            >>> new_mcp = plugin.add_mcp_config_to(agent.mcp_config)
            >>> agent = agent.model_copy(update={"mcp_config": new_mcp})
        """
        existing_servers = mcp_config or {}
        plugin_servers = self.mcp_config
        for server_name in plugin_servers:
            if server_name in existing_servers:
                logger.warning(
                    f"Plugin MCP server '{server_name}' overrides existing server"
                )
        return {**existing_servers, **plugin_servers}

    @classmethod
    def fetch(
        cls,
        source: str,
        cache_dir: Path | None = None,
        ref: str | None = None,
        update: bool = True,
        repo_path: str | None = None,
    ) -> Path:
        """Fetch a plugin from a remote source and return the local cached path.

        This method fetches plugins from remote sources (GitHub repositories, git URLs)
        and caches them locally. Use the returned path with Plugin.load() to load
        the plugin.

        Args:
            source: Plugin source - can be:
                - Any git URL (GitHub, GitLab, Bitbucket, Codeberg, self-hosted, etc.)
                  e.g., "https://gitlab.com/org/repo", "git@bitbucket.org:team/repo.git"
                - "github:owner/repo" - GitHub shorthand (convenience syntax)
                - "/local/path" - Local path (returned as-is)
            cache_dir: Directory for caching. Defaults to ~/.handprint/cache/plugins/
            ref: Optional branch, tag, or commit to checkout.
            update: If True and cache exists, update it. If False, use cached as-is.
            repo_path: Subdirectory path within the git repository
                (e.g., 'plugins/my-plugin' for monorepos). Only relevant for git
                sources, not local paths. If specified, the returned path will
                point to this subdirectory instead of the repository root.

        Returns:
            Path to the local plugin directory (ready for Plugin.load()).
            If repo_path is specified, returns the path to that subdirectory.

        Raises:
            PluginFetchError: If fetching fails or repo_path doesn't exist.

        Example:
            >>> path = Plugin.fetch("github:owner/my-plugin")
            >>> plugin = Plugin.load(path)

            >>> # With specific version
            >>> path = Plugin.fetch("github:owner/my-plugin", ref="v1.0.0")
            >>> plugin = Plugin.load(path)

            >>> # Fetch a plugin from a subdirectory in a monorepo
            >>> path = Plugin.fetch("github:owner/monorepo", repo_path="plugins/sub")
            >>> plugin = Plugin.load(path)

            >>> # Fetch and load in one step
            >>> plugin = Plugin.load(Plugin.fetch("github:owner/my-plugin"))
        """
        return fetch_plugin(
            source, cache_dir=cache_dir, ref=ref, update=update, repo_path=repo_path
        )

    @classmethod
    def load(cls, plugin_path: str | Path) -> Plugin:
        """Load a plugin from a directory.

        Args:
            plugin_path: Path to the plugin directory.

        Returns:
            Loaded Plugin instance.

        Raises:
            FileNotFoundError: If the plugin directory doesn't exist.
            ValueError: If the plugin manifest is invalid.
        """
        plugin_dir = Path(plugin_path).resolve()
        if not plugin_dir.is_dir():
            raise FileNotFoundError(f"Plugin directory not found: {plugin_dir}")

        return detect_format(plugin_dir).load(plugin_dir)

    @classmethod
    def load_all(cls, plugins_dir: str | Path) -> list[Plugin]:
        """Load all plugins from a directory.

        Args:
            plugins_dir: Path to directory containing plugin subdirectories.

        Returns:
            List of loaded Plugin instances.
        """
        plugins_path = Path(plugins_dir).resolve()
        if not plugins_path.is_dir():
            logger.warning(f"Plugins directory not found: {plugins_path}")
            return []

        plugins: list[Plugin] = []
        for item in sorted(plugins_path.iterdir()):
            if item.is_dir():
                try:
                    plugin = cls.load(item)
                    plugins.append(plugin)
                    logger.debug(f"Loaded plugin: {plugin.name} from {item}")
                except Exception as e:
                    logger.warning(f"Failed to load plugin from {item}: {e}")

        return plugins
