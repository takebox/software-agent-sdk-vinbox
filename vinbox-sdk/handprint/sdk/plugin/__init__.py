"""Plugin module for Handprint SDK.

This module provides support for loading and managing plugins that bundle
tracks, hooks, MCP configurations, agents, and commands together.

It also provides support for plugin marketplaces - directories that list
available plugins with their metadata and source locations.

Additionally, it provides utilities for managing installed plugins in the
user's home directory (~/.handprint/plugins/installed/).

Note: Marketplace classes live in ``handprint.sdk.marketplace``.
"""

from handprint.sdk.plugin.discovery import (
    load_available_plugins,
    load_project_plugins,
    load_user_plugins,
)
from handprint.sdk.plugin.fetch import (
    PluginFetchError,
    fetch_plugin_with_resolution,
)
from handprint.sdk.plugin.format import (
    AgentPluginsFormat,
    HaijunCodePluginFormat,
    PluginFormat,
    detect_format,
)
from handprint.sdk.plugin.format.agent_plugins_mcp import get_plugin_data_dir
from handprint.sdk.plugin.installed import (
    InstalledPluginInfo,
    disable_plugin,
    enable_plugin,
    get_installed_plugin,
    get_installed_plugins_dir,
    install_plugin,
    list_installed_plugins,
    load_installed_plugins,
    uninstall_plugin,
    update_plugin,
)
from handprint.sdk.plugin.loader import load_plugins
from handprint.sdk.plugin.plugin import Plugin
from handprint.sdk.plugin.source import (
    GitHubURLComponents,
    is_local_path,
    parse_github_url,
    resolve_source_path,
    validate_source_path,
)
from handprint.sdk.plugin.types import (
    CommandDefinition,
    PluginAuthor,
    PluginManifest,
    PluginSource,
    ResolvedPluginSource,
)


__all__ = [
    # Plugin classes
    "Plugin",
    "PluginFetchError",
    "PluginManifest",
    "PluginAuthor",
    "PluginSource",
    "ResolvedPluginSource",
    "CommandDefinition",
    # Plugin format strategies
    "PluginFormat",
    "AgentPluginsFormat",
    "HaijunCodePluginFormat",
    "detect_format",
    # Plugin loading
    "load_plugins",
    "fetch_plugin_with_resolution",
    # Local plugin discovery (ambient auto-load)
    "load_user_plugins",
    "load_project_plugins",
    "load_available_plugins",
    # Source path utilities
    "GitHubURLComponents",
    "parse_github_url",
    "is_local_path",
    "validate_source_path",
    "resolve_source_path",
    # Installed plugins management
    "InstalledPluginInfo",
    "install_plugin",
    "uninstall_plugin",
    "list_installed_plugins",
    "load_installed_plugins",
    "get_installed_plugins_dir",
    "get_installed_plugin",
    "get_plugin_data_dir",
    "enable_plugin",
    "disable_plugin",
    "update_plugin",
]
