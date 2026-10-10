from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from handprint.sdk.agent import (
    Agent,
    AgentBase,
)
from handprint.sdk.banner import _print_banner
from handprint.sdk.context import AgentContext, load_memory
from handprint.sdk.context.condenser import (
    LLMSummarizingCondenser,
)
from handprint.sdk.conversation import (
    BaseConversation,
    Conversation,
    ConversationCallbackType,
    ConversationExecutionStatus,
    LocalConversation,
    RemoteConversation,
)
from handprint.sdk.conversation.conversation_stats import ConversationStats
from handprint.sdk.event import Event, HookExecutionEvent, LLMConvertibleEvent
from handprint.sdk.event.llm_convertible import MessageEvent
from handprint.sdk.io import FileStore, LocalFileStore
from handprint.sdk.llm import (
    LLM,
    LLM_PROFILE_SCHEMA_VERSION,
    FallbackStrategy,
    ImageContent,
    LLMProfileStore,
    LLMRegistry,
    LLMStreamChunk,
    Message,
    RedactedThinkingBlock,
    RegistryEvent,
    TextContent,
    ThinkingBlock,
    TokenCallbackType,
    TokenUsage,
)
from handprint.sdk.logger import get_logger
from handprint.sdk.mcp import (
    MCPClient,
    MCPToolDefinition,
    MCPToolObservation,
    create_mcp_tools,
)
from handprint.sdk.plugin import Plugin
from handprint.sdk.settings import (
    ACP_PROVIDERS,
    ACPAgentSettings,
    ACPFileSecretSpec,
    ACPModelOption,
    ACPProviderInfo,
    AgentSettingsBase,
    AgentSettingsConfig,
    CondenserSettings,
    ConversationSettings,
    HandprintAgentSettings,
    SettingsChoice,
    SettingsFieldSchema,
    SettingsSchema,
    SettingsSectionSchema,
    VerificationSettings,
    apply_agent_settings_diff,
    build_session_model_meta,
    default_agent_settings,
    detect_acp_provider_by_agent_name,
    export_agent_settings_schema,
    export_settings_schema,
    get_acp_provider,
    validate_agent_settings,
)
from handprint.sdk.settings.metadata import (
    SettingProminence,
    SettingsFieldMetadata,
    SettingsSectionMetadata,
    field_meta,
)
from handprint.sdk.tracks import (
    load_project_tracks,
    load_tracks_from_dir,
    load_user_tracks,
)
from handprint.sdk.subagent import (
    agent_definition_to_factory,
    discover_agents,
    load_agents_from_dir,
    load_project_agents,
    load_user_agents,
    register_agent,
)
from handprint.sdk.tool import (
    Action,
    Observation,
    Tool,
    ToolDefinition,
    list_registered_tools,
    register_tool,
    resolve_tool,
)
from handprint.sdk.utils import page_iterator
from handprint.sdk.workspace import (
    AsyncRemoteWorkspace,
    LocalWorkspace,
    RemoteWorkspace,
    Workspace,
)


try:
    __version__ = version("openhands-sdk")
except PackageNotFoundError:
    __version__ = "0.0.0"  # fallback for editable/unbuilt environments

# Print startup banner
_print_banner(__version__)


__all__ = [
    "LLM",
    "LLM_PROFILE_SCHEMA_VERSION",
    "LLMRegistry",
    "LLMProfileStore",
    "LLMStreamChunk",
    "FallbackStrategy",
    "TokenCallbackType",
    "TokenUsage",
    "ConversationStats",
    "RegistryEvent",
    "Message",
    "TextContent",
    "ImageContent",
    "ThinkingBlock",
    "RedactedThinkingBlock",
    "Tool",
    "ToolDefinition",
    "AgentBase",
    "Agent",
    "Action",
    "Observation",
    "MCPClient",
    "MCPToolDefinition",
    "MCPToolObservation",
    "MessageEvent",
    "HookExecutionEvent",
    "create_mcp_tools",
    "get_logger",
    "Conversation",
    "BaseConversation",
    "LocalConversation",
    "RemoteConversation",
    "ConversationExecutionStatus",
    "ConversationCallbackType",
    "Event",
    "LLMConvertibleEvent",
    "AgentContext",
    "LLMSummarizingCondenser",
    "CondenserSettings",
    "ConversationSettings",
    "VerificationSettings",
    "ACP_PROVIDERS",
    "ACPAgentSettings",
    "ACPFileSecretSpec",
    "ACPModelOption",
    "ACPProviderInfo",
    "AgentSettingsBase",
    "AgentSettingsConfig",
    "HandprintAgentSettings",
    "apply_agent_settings_diff",
    "build_session_model_meta",
    "default_agent_settings",
    "detect_acp_provider_by_agent_name",
    "export_agent_settings_schema",
    "get_acp_provider",
    "validate_agent_settings",
    "SettingsChoice",
    "SettingProminence",
    "SettingsFieldMetadata",
    "SettingsFieldSchema",
    "SettingsSchema",
    "SettingsSectionMetadata",
    "SettingsSectionSchema",
    "export_settings_schema",
    "field_meta",
    "FileStore",
    "LocalFileStore",
    "Plugin",
    "register_tool",
    "resolve_tool",
    "list_registered_tools",
    "Workspace",
    "LocalWorkspace",
    "RemoteWorkspace",
    "AsyncRemoteWorkspace",
    "register_agent",
    "load_project_agents",
    "load_user_agents",
    "load_agents_from_dir",
    "discover_agents",
    "agent_definition_to_factory",
    "load_memory",
    "load_project_tracks",
    "load_tracks_from_dir",
    "load_user_tracks",
    "page_iterator",
    "__version__",
]
