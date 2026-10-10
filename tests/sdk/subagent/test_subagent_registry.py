from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from handprint.sdk import LLM, Agent
from handprint.sdk.context.condenser import LLMSummarizingCondenser, NoOpCondenser
from handprint.sdk.hooks.config import HookConfig, HookDefinition, HookMatcher
from handprint.sdk.llm.llm_profile_store import LLMProfileStore
from handprint.sdk.mcp.config import MCPServer, dump_mcp_config
from handprint.sdk.subagent.registry import (
    _reset_registry_for_tests,
    agent_definition_to_factory,
    get_agent_factory,
    get_factory_info,
    register_agent,
    register_agent_if_absent,
    register_file_agents,
    register_plugin_agents,
)
from handprint.sdk.subagent.schema import AgentDefinition


def setup_function() -> None:
    _reset_registry_for_tests()


def teardown_function() -> None:
    _reset_registry_for_tests()


def _make_test_llm() -> LLM:
    """Create a real LLM instance for testing."""
    return LLM(
        model="gpt-4o",
        api_key=SecretStr("test-key"),
        usage_id="test-llm",
    )


def _create_track_file(tracks_dir: Path, name: str, content: str) -> None:
    """Create a track .md file in the given tracks directory."""
    track_file = tracks_dir / f"{name}.md"
    track_file.write_text(
        f"---\nname: {name}\ntriggers:\n  - {name}\n---\n\n{content}\n"
    )


def test_register_file_agents_project_priority(tmp_path: Path) -> None:
    """Project-level agents take priority over user-level agents with same name."""
    # Project .agents/
    project_agents_dir = tmp_path / ".agents" / "agents"
    project_agents_dir.mkdir(parents=True)
    (project_agents_dir / "shared-agent.md").write_text(
        "---\nname: shared-agent\ndescription: Project version\n---\n\nProject prompt."
    )

    # User ~/.agents/ (using a separate temp dir)
    user_home = tmp_path / "fake_home"
    user_home.mkdir(parents=True)
    user_agents_dir = user_home / ".agents" / "agents"
    user_agents_dir.mkdir(parents=True)
    (user_agents_dir / "shared-agent.md").write_text(
        "---\nname: shared-agent\ndescription: User version\n---\n\nUser prompt."
    )

    with patch("handprint.sdk.subagent.load.Path.home", return_value=user_home):
        registered = register_file_agents(tmp_path)

    assert "shared-agent" in registered
    # Verify the project version won
    factory = get_agent_factory("shared-agent")
    assert factory.definition.description == "Project version"


def test_register_file_agents_skips_programmatic(tmp_path: Path) -> None:
    """Does not overwrite agents registered programmatically."""

    # Register an agent programmatically first
    def existing_factory(llm: LLM) -> Agent:
        return cast(Agent, MagicMock())

    register_agent(
        name="existing-agent",
        factory_func=existing_factory,
        description="Programmatic version",
    )

    # Create file-based agent with same name
    agents_dir = tmp_path / ".agents" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "existing-agent.md").write_text(
        "---\nname: existing-agent\ndescription: File version\n---\n\nFile prompt."
    )

    with patch(
        "handprint.sdk.subagent.load.Path.home", return_value=tmp_path / "no_user"
    ):
        registered = register_file_agents(tmp_path)

    # File agent should NOT have been registered (programmatic wins)
    assert "existing-agent" not in registered
    # Verify the programmatic version is still there
    factory = get_agent_factory("existing-agent")
    assert factory.definition.description == "Programmatic version"


def test_register_plugin_agents(tmp_path: Path) -> None:
    """Plugin agents are registered via register_agent_if_absent."""
    plugin_agent = AgentDefinition(
        name="plugin-agent",
        description="From plugin",
        model="inherit",
        tools=["ReadTool"],
        system_prompt="Plugin prompt.",
    )

    registered = register_plugin_agents([plugin_agent], work_dir=tmp_path)

    assert registered == ["plugin-agent"]
    factory = get_agent_factory("plugin-agent")
    assert factory.definition.description == "From plugin"


def test_register_plugin_agents_skips_existing(tmp_path: Path) -> None:
    """Plugin agents don't overwrite programmatically registered agents."""

    def existing_factory(llm: LLM) -> Agent:
        return cast(Agent, MagicMock())

    register_agent(
        name="my-agent",
        factory_func=existing_factory,
        description="Programmatic",
    )

    plugin_agent = AgentDefinition(
        name="my-agent",
        description="Plugin version",
        model="inherit",
        tools=[],
        system_prompt="",
    )

    registered = register_plugin_agents([plugin_agent], work_dir=tmp_path)
    assert registered == []
    # Programmatic version still there
    factory = get_agent_factory("my-agent")
    assert factory.definition.description == "Programmatic"


def test_register_agent_if_absent_existing() -> None:
    """register_agent_if_absent returns False for existing agents."""

    def factory1(llm: LLM) -> Agent:  # type: ignore[unused-argument]
        return cast(Agent, MagicMock())

    def factory2(llm: LLM) -> Agent:  # type: ignore[unused-argument]
        return cast(Agent, MagicMock())

    register_agent(name="dup_agent", factory_func=factory1, description="First")

    result = register_agent_if_absent(
        name="dup_agent",
        factory_func=factory2,
        description="Second",
    )
    assert result is False

    # First registration should be preserved
    factory = get_agent_factory("dup_agent")
    assert factory.definition.description == "First"


def test_agent_definition_to_factory_basic() -> None:
    """Factory creates Agent with correct tools, system prompt, and LLM."""
    agent_def = AgentDefinition(
        name="test-agent",
        description="A test agent",
        model="inherit",
        tools=[],
        system_prompt="You are a test agent.",
    )

    factory = agent_definition_to_factory(agent_def)
    llm = _make_test_llm()
    agent = factory(llm)

    assert isinstance(agent, Agent)
    # Check tools are empty
    assert agent.tools == []
    # Check track (system prompt as always-active track)
    assert agent.agent_context is not None
    assert agent.agent_context.system_message_suffix == "You are a test agent."


def test_agent_definition_to_factory_model_inherit() -> None:
    """Model 'inherit' preserves the parent LLM."""
    agent_def = AgentDefinition(
        name="inherit-agent",
        description="Uses parent model",
        model="inherit",
        tools=[],
        system_prompt="Test prompt.",
    )

    factory = agent_definition_to_factory(agent_def)
    llm = _make_test_llm()
    agent = factory(llm)

    assert agent.llm is llm
    assert agent.llm.model == "gpt-4o"


def test_agent_definition_to_factory_model_override() -> None:
    """Non-inherit model that isn't a stored profile raises ValueError."""
    agent_def = AgentDefinition(
        name="override-agent",
        description="Uses specific model",
        model="haijun-codtral",
        tools=[],
        system_prompt="Test prompt.",
    )

    factory = agent_definition_to_factory(agent_def)
    llm = _make_test_llm()

    with pytest.raises(ValueError, match="not found in profile store"):
        factory(llm)


def test_agent_definition_to_factory_no_system_prompt() -> None:
    """Factory with empty system prompt creates agent without agent_context."""
    agent_def = AgentDefinition(
        name="no-prompt-agent",
        description="No prompt",
        model="inherit",
        system_prompt="",
    )

    factory = agent_definition_to_factory(agent_def)
    llm = _make_test_llm()
    agent = factory(llm)

    assert agent.agent_context is None


def test_agent_definition_to_factory_with_tracks(tmp_path: Path) -> None:
    """Factory resolves track names and passes them to AgentContext."""
    # Create a track file in project directory
    tracks_dir = tmp_path / ".agents" / "tracks"
    tracks_dir.mkdir(parents=True)
    _create_track_file(tracks_dir, "test-track", "Track content here.")

    agent_def = AgentDefinition(
        name="tracked-agent",
        description="Agent with tracks",
        model="inherit",
        tools=[],
        tracks=["test-track"],
        system_prompt="You are a tracked agent.",
    )

    factory = agent_definition_to_factory(agent_def, work_dir=tmp_path)
    llm = _make_test_llm()
    agent = factory(llm)

    assert agent.agent_context is not None
    assert len(agent.agent_context.tracks) == 1
    assert agent.agent_context.tracks[0].name == "test-track"
    assert "Track content here." in agent.agent_context.tracks[0].content
    assert agent.agent_context.system_message_suffix == "You are a tracked agent."


def test_agent_definition_to_factory_tracks_only_no_prompt(tmp_path: Path) -> None:
    """Factory with tracks but no system prompt still creates AgentContext."""
    tracks_dir = tmp_path / ".agents" / "tracks"
    tracks_dir.mkdir(parents=True)
    _create_track_file(tracks_dir, "only-track", "Only track content.")

    agent_def = AgentDefinition(
        name="tracks-only-agent",
        description="Agent with tracks but no prompt",
        model="inherit",
        tools=[],
        tracks=["only-track"],
        system_prompt="",
    )

    factory = agent_definition_to_factory(agent_def, work_dir=tmp_path)
    llm = _make_test_llm()
    agent = factory(llm)

    assert agent.agent_context is not None
    assert len(agent.agent_context.tracks) == 1
    assert agent.agent_context.tracks[0].name == "only-track"
    assert agent.agent_context.system_message_suffix is None


def test_agent_definition_to_factory_no_tracks_no_prompt() -> None:
    """Factory with no tracks and no prompt creates no AgentContext."""
    agent_def = AgentDefinition(
        name="empty-agent",
        description="No tracks no prompt",
        model="inherit",
        tools=[],
        tracks=[],
        system_prompt="",
    )

    factory = agent_definition_to_factory(agent_def)
    llm = _make_test_llm()
    agent = factory(llm)

    assert agent.agent_context is None


def test_agent_definition_to_factory_track_not_found() -> None:
    """Factory raises ValueError when a track name is not found."""
    agent_def = AgentDefinition(
        name="missing-track-agent",
        description="Agent with missing track",
        model="inherit",
        tracks=["nonexistent-track"],
    )

    with pytest.raises(ValueError, match="Track 'nonexistent-track' not found"):
        agent_definition_to_factory(agent_def)


def test_agent_definition_to_factory_tracks_project_over_user(tmp_path: Path) -> None:
    """Project tracks take priority over user tracks with the same name."""
    # Create project-level track
    project_tracks_dir = tmp_path / ".agents" / "tracks"
    project_tracks_dir.mkdir(parents=True)
    _create_track_file(project_tracks_dir, "shared-track", "Project version.")

    # Create user-level track with same name
    user_home = tmp_path / "fake_home"
    user_tracks_dir = user_home / ".agents" / "tracks"
    user_tracks_dir.mkdir(parents=True)
    _create_track_file(user_tracks_dir, "shared-track", "User version.")

    agent_def = AgentDefinition(
        name="priority-agent",
        tracks=["shared-track"],
    )

    with patch("handprint.sdk.tracks.track.Path.home", return_value=user_home):
        factory = agent_definition_to_factory(agent_def, work_dir=tmp_path)

    llm = _make_test_llm()
    agent = factory(llm)

    assert agent.agent_context is not None
    assert len(agent.agent_context.tracks) == 1
    # Project version should win
    assert "Project version." in agent.agent_context.tracks[0].content


def test_factory_info() -> None:
    """get_factory_info returns formatted listing of registered agents."""
    info = get_factory_info()
    assert "No user-registered agents" in info

    # Register some agents
    def factory_a(llm: LLM) -> Agent:  # type: ignore[unused-argument]
        return cast(Agent, MagicMock())

    def factory_b(llm: LLM) -> Agent:  # type: ignore[unused-argument]
        return cast(Agent, MagicMock())

    register_agent(name="alpha-agent", factory_func=factory_a, description="Alpha desc")
    register_agent(name="beta-agent", factory_func=factory_b, description="Beta desc")

    info = get_factory_info()
    assert "No user-registered agents" not in info
    assert "**alpha-agent**: Alpha desc" in info
    assert "**beta-agent**: Beta desc" in info
    # Verify alphabetical ordering: alpha before beta
    assert info.index("alpha-agent") < info.index("beta-agent")


def test_factory_info_mixed_tools_and_no_tools() -> None:
    """get_factory_info correctly shows tools only for agents that have them."""

    def dummy(llm: LLM) -> Agent:  # type: ignore[unused-argument]
        return cast(Agent, MagicMock())

    agent_with = AgentDefinition(
        name="with-tools",
        description="Has tools",
        tools=["TerminalTool"],
    )
    agent_without = AgentDefinition(
        name="without-tools",
        description="No tools",
        tools=[],
    )
    register_agent(name="with-tools", factory_func=dummy, description=agent_with)
    register_agent(name="without-tools", factory_func=dummy, description=agent_without)

    info = get_factory_info()
    assert info == (
        "- **with-tools**: Has tools (tools: TerminalTool)\n"
        "- **without-tools**: No tools"
    )


def test_factory_info_single_agent() -> None:
    """get_factory_info works correctly with a single registered agent."""

    def dummy(llm: LLM) -> Agent:  # type: ignore[unused-argument]
        return cast(Agent, MagicMock())

    register_agent(name="solo-agent", factory_func=dummy, description="Only agent")

    info = get_factory_info()
    assert info == "- **solo-agent**: Only agent"


@pytest.mark.parametrize("name", [None, "", "default", "alpha"])
def test_error_default_factory_empty(name: str | None) -> None:
    """Ensure default agent factory is used when no type is provided."""
    with pytest.raises(ValueError, match=f"Unknown agent '{name}'"):
        _ = get_agent_factory(name)


def test_register_and_retrieve_custom_agent_factory() -> None:
    """User-registered agent factories should be retrievable by name."""

    def dummy_factory(llm: LLM) -> Agent:  # type: ignore[unused-argument]
        return cast(Agent, MagicMock())

    register_agent(
        name="custom_agent",
        factory_func=dummy_factory,
        description="Custom agent for testing",
    )

    factory = get_agent_factory("custom_agent")
    assert factory.definition.description == "Custom agent for testing"
    assert factory.factory_func is dummy_factory


def test_unknown_agent_type_raises_value_error() -> None:
    """Retrieving an unknown agent type should provide a helpful error."""
    with pytest.raises(ValueError) as excinfo:
        get_agent_factory("missing")

    assert "Unknown agent 'missing'" in str(excinfo.value)


def test_register_agent_if_absent_new() -> None:
    """register_agent_if_absent returns True for new agents."""

    def dummy_factory(llm: LLM) -> Agent:  # type: ignore[unused-argument]
        return cast(Agent, MagicMock())

    result = register_agent_if_absent(
        name="new_agent",
        factory_func=dummy_factory,
        description="New agent",
    )
    assert result is True

    factory = get_agent_factory("new_agent")
    assert factory.definition.description == "New agent"


def test_agent_definition_to_factory_model_profile(tmp_path: Path) -> None:
    """Profile name loads a complete LLM from the profile store."""
    store = LLMProfileStore(base_dir=tmp_path)
    profile_llm = LLM(
        model="haijun-codtral",
        api_key=SecretStr("profile-key"),
        usage_id="profile-llm",
        temperature=0.3,
    )
    store.save("fast-gpt", profile_llm, include_secrets=True)

    agent_def = AgentDefinition(
        name="profile-agent",
        description="Uses a profile",
        model="fast-gpt",
        tools=[],
        system_prompt="Profile test.",
    )

    factory = agent_definition_to_factory(agent_def)
    parent_llm = _make_test_llm()
    with patch(
        "handprint.sdk.subagent.registry._get_profile_store", return_value=store
    ):
        agent = factory(parent_llm)

    # The agent's LLM should come from the profile, not the parent
    assert agent.llm is not parent_llm
    assert agent.llm.model == "haijun-codtral"
    assert agent.llm.temperature == 0.3
    assert agent.llm.stream is False
    # Metrics must be independent from the parent LLM
    assert agent.llm.metrics is not parent_llm.metrics


def test_agent_definition_to_factory_model_profile_with_json_suffix(
    tmp_path: Path,
) -> None:
    """Profile name with .json suffix is accepted and loads correctly."""
    store = LLMProfileStore(base_dir=tmp_path)
    profile_llm = LLM(
        model="haijun-codtral",
        api_key=SecretStr("profile-key"),
        usage_id="profile-llm",
        temperature=0.3,
    )
    store.save("fast-gpt", profile_llm, include_secrets=True)

    agent_def = AgentDefinition(
        name="profile-agent",
        description="Uses a profile with .json suffix",
        model="fast-gpt.json",
        tools=[],
        system_prompt="Profile test.",
    )

    factory = agent_definition_to_factory(agent_def)
    parent_llm = _make_test_llm()
    with patch(
        "handprint.sdk.subagent.registry._get_profile_store", return_value=store
    ):
        agent = factory(parent_llm)

    assert agent.llm is not parent_llm
    assert agent.llm.model == "haijun-codtral"
    assert agent.llm.temperature == 0.3


def test_agent_definition_to_factory_model_profile_not_found(tmp_path: Path) -> None:
    """Missing profile raises ValueError."""
    store = LLMProfileStore(base_dir=tmp_path)

    agent_def = AgentDefinition(
        name="missing-profile-agent",
        description="Profile does not exist",
        model="nonexistent.json",
        tools=[],
        system_prompt="",
    )

    factory = agent_definition_to_factory(agent_def)
    parent_llm = _make_test_llm()

    with patch(
        "handprint.sdk.subagent.registry._get_profile_store", return_value=store
    ):
        with pytest.raises(ValueError, match="nonexistent"):
            factory(parent_llm)


def test_agent_definition_to_factory_model_profile_custom_store(tmp_path: Path) -> None:
    """Patched profile store is used by the factory."""
    custom_store = LLMProfileStore(base_dir=tmp_path)
    profile_llm = LLM(
        model="gpt-4o-mini",
        api_key=SecretStr("custom-store-key"),
        usage_id="custom-store-llm",
    )
    custom_store.save("my-profile", profile_llm, include_secrets=True)

    agent_def = AgentDefinition(
        name="custom-store-agent",
        description="Uses custom store",
        model="my-profile",
        tools=[],
        system_prompt="",
    )

    factory = agent_definition_to_factory(agent_def)
    parent_llm = _make_test_llm()
    with patch(
        "handprint.sdk.subagent.registry._get_profile_store", return_value=custom_store
    ):
        agent = factory(parent_llm)

    assert agent.llm.model == "gpt-4o-mini"
    assert agent.llm.stream is False
    # Metrics must be independent from the parent LLM
    assert agent.llm.metrics is not parent_llm.metrics


def test_agent_definition_to_factory_profile_store_dir(tmp_path: Path) -> None:
    """profile_store_dir on AgentDefinition is used by the factory."""
    store = LLMProfileStore(base_dir=tmp_path)
    profile_llm = LLM(
        model="gpt-4o-mini",
        api_key=SecretStr("dir-key"),
        usage_id="dir-llm",
    )
    store.save("my-profile", profile_llm, include_secrets=True)
    agent_def = AgentDefinition(
        name="dir-agent",
        description="Uses profile_store_dir",
        model="my-profile",
        tools=[],
        system_prompt="",
        profile_store_dir=str(tmp_path),
    )

    factory = agent_definition_to_factory(agent_def)
    parent_llm = _make_test_llm()
    agent = factory(parent_llm)

    assert agent.llm.model == "gpt-4o-mini"


def test_agent_definition_to_factory_profile_store_dir_not_found(
    tmp_path: Path,
) -> None:
    """Missing profile in custom profile_store_dir raises ValueError."""
    agent_def = AgentDefinition(
        name="missing-dir-agent",
        model="nonexistent",
        tools=[],
        system_prompt="",
        profile_store_dir=str(tmp_path),
    )

    factory = agent_definition_to_factory(agent_def)
    parent_llm = _make_test_llm()

    with pytest.raises(ValueError, match="nonexistent"):
        factory(parent_llm)


def test_agent_definition_to_factory_profile_store_dir_none_uses_default(
    tmp_path: Path,
) -> None:
    """When profile_store_dir is None, the default cached store is used."""
    store = LLMProfileStore(base_dir=tmp_path)
    profile_llm = LLM(
        model="haijun-codtral",
        api_key=SecretStr("default-key"),
        usage_id="default-llm",
    )
    store.save("default-profile", profile_llm, include_secrets=True)

    agent_def = AgentDefinition(
        name="default-store-agent",
        model="default-profile",
        tools=[],
        system_prompt="",
        profile_store_dir=None,
    )

    factory = agent_definition_to_factory(agent_def)
    parent_llm = _make_test_llm()

    with patch(
        "handprint.sdk.subagent.registry._get_profile_store", return_value=store
    ):
        agent = factory(parent_llm)

    assert agent.llm.model == "haijun-codtral"


def test_register_agent_with_hook_config() -> None:
    """register_agent stores hook_config in the AgentFactory via AgentDefinition."""
    hook_config = HookConfig(
        pre_tool_use=[
            HookMatcher(
                matcher="terminal",
                hooks=[HookDefinition(command="./validate.sh")],
            )
        ]
    )

    def dummy_factory(llm: LLM) -> Agent:  # type: ignore[unused-argument]
        return cast(Agent, MagicMock())

    agent_def = AgentDefinition(
        name="hooked-agent",
        description="Agent with hooks",
        hooks=hook_config,
    )

    register_agent(
        name="hooked-agent",
        factory_func=dummy_factory,
        description=agent_def,
    )

    factory = get_agent_factory("hooked-agent")
    assert factory.definition.hooks is not None
    assert len(factory.definition.hooks.pre_tool_use) == 1
    assert factory.definition.hooks.pre_tool_use[0].matcher == "terminal"


def test_register_agent_hook_config_defaults_to_none() -> None:
    """AgentFactory.hook_config defaults to None when not provided."""

    def dummy_factory(llm: LLM) -> Agent:  # type: ignore[unused-argument]
        return cast(Agent, MagicMock())

    register_agent(
        name="no-hooks-agent",
        factory_func=dummy_factory,
        description="Agent without hooks",
    )

    factory = get_agent_factory("no-hooks-agent")
    assert factory.definition.hooks is None


def test_register_file_agents_with_hooks(tmp_path: Path) -> None:
    """File-based agents with hooks have hook_config stored in the factory."""
    agents_dir = tmp_path / ".agents" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "hooked.md").write_text(
        "---\n"
        "name: hooked-file-agent\n"
        "description: File agent with hooks\n"
        "hooks:\n"
        "  pre_tool_use:\n"
        "    - matcher: '*'\n"
        "      hooks:\n"
        "        - command: ./log.sh\n"
        "---\n\n"
        "You are an agent with hooks.\n"
    )

    with patch(
        "handprint.sdk.subagent.load.Path.home", return_value=tmp_path / "no_user"
    ):
        registered = register_file_agents(tmp_path)

    assert "hooked-file-agent" in registered
    factory = get_agent_factory("hooked-file-agent")
    assert factory.definition.hooks is not None
    assert len(factory.definition.hooks.pre_tool_use) == 1


def test_register_plugin_agents_with_hooks() -> None:
    """Plugin agents with hooks have hook_config stored in the factory."""
    hook_config = HookConfig(
        stop=[
            HookMatcher(
                matcher="*",
                hooks=[HookDefinition(command="./check_stop.sh")],
            )
        ]
    )
    plugin_agent = AgentDefinition(
        name="plugin-hooked",
        description="Plugin agent with hooks",
        model="inherit",
        tools=[],
        system_prompt="Plugin prompt.",
        hooks=hook_config,
    )

    registered = register_plugin_agents([plugin_agent])
    assert "plugin-hooked" in registered

    factory = get_agent_factory("plugin-hooked")
    assert factory.definition.hooks is not None
    assert len(factory.definition.hooks.stop) == 1


def test_end_to_end_md_to_factory_to_registry(tmp_path: Path) -> None:
    """End-to-end: .md file -> AgentDefinition.load() -> factory -> register -> get."""
    md_file = tmp_path / "test-agent.md"
    md_file.write_text(
        "---\n"
        "name: e2e-test-agent\n"
        "description: End-to-end test agent\n"
        "model: inherit\n"
        "---\n\n"
        "You are a test agent for end-to-end testing.\n"
        "Focus on correctness and clarity.\n"
    )

    # Load from file
    agent_def = AgentDefinition.load(md_file)
    assert agent_def.name == "e2e-test-agent"
    assert agent_def.description == "End-to-end test agent"

    # Convert to factory
    factory = agent_definition_to_factory(agent_def)

    # Register
    result = register_agent_if_absent(
        name=agent_def.name,
        factory_func=factory,
        description=agent_def.description,
    )
    assert result is True

    # Retrieve and verify
    retrieved = get_agent_factory("e2e-test-agent")
    assert retrieved.definition.description == "End-to-end test agent"

    # Create agent from factory (with real LLM)
    test_llm = LLM(
        model="gpt-4o",
        api_key=SecretStr("test-key"),
        usage_id="test-llm",
    )
    agent = retrieved.factory_func(test_llm)
    assert isinstance(agent, Agent)


def test_agent_definition_to_factory_mcp_config() -> None:
    """Factory passes mcp_config to the Agent."""
    agent_def = AgentDefinition(
        name="mcp-agent",
        description="Agent with MCP servers",
        model="inherit",
        tools=[],
        system_prompt="",
        mcp_config={
            "fetch": MCPServer(command="uvx", args=["mcp-server-fetch"]),
        },
    )

    factory = agent_definition_to_factory(agent_def)
    llm = _make_test_llm()
    agent = factory(llm)

    assert dump_mcp_config(agent.mcp_config) == {
        "fetch": {"command": "uvx", "args": ["mcp-server-fetch"]}
    }


def test_agent_definition_to_factory_no_mcp_config() -> None:
    """Factory without mcp_config passes an empty server map."""
    agent_def = AgentDefinition(
        name="no-mcp-agent",
        model="inherit",
        tools=[],
        system_prompt="",
    )

    factory = agent_definition_to_factory(agent_def)
    llm = _make_test_llm()
    agent = factory(llm)

    assert agent.mcp_config == {}


def test_register_file_agents_passes_mcp_config_to_agent(tmp_path: Path) -> None:
    """Integration: mcp_config in markdown flows through registry to Agent."""
    agents_dir = tmp_path / ".agents" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "mcp-agent.md").write_text(
        "---\n"
        "name: mcp-agent\n"
        "description: Agent with MCP servers\n"
        "mcp_config:\n"
        "  fetch:\n"
        "    command: uvx\n"
        "    args: [mcp-server-fetch]\n"
        "---\n\n"
        "Agent with MCP.\n"
    )

    with patch(
        "handprint.sdk.subagent.load.Path.home", return_value=tmp_path / "no_user"
    ):
        registered = register_file_agents(tmp_path)

    assert "mcp-agent" in registered

    factory = get_agent_factory("mcp-agent")
    llm = _make_test_llm()
    agent = factory.factory_func(llm)

    assert dump_mcp_config(agent.mcp_config) == {
        "fetch": {"command": "uvx", "args": ["mcp-server-fetch"]}
    }


def test_factory_attaches_default_condenser() -> None:
    """Sub-agents get a summarizing condenser by default (parity with the top-level
    agent) so deep runs auto-compact instead of erroring on context overflow."""
    factory = agent_definition_to_factory(AgentDefinition(name="gp"))
    agent = factory(_make_test_llm())
    assert isinstance(agent.condenser, LLMSummarizingCondenser)


def test_factory_condenser_uses_distinct_usage_id() -> None:
    """The condenser LLM must use a distinct usage_id or its tokens get deduped out
    of conversation stats (first-write-wins on usage_id)."""
    factory = agent_definition_to_factory(AgentDefinition(name="gp"))
    agent = factory(_make_test_llm())
    assert isinstance(agent.condenser, LLMSummarizingCondenser)
    assert agent.condenser.llm.usage_id == "condenser"
    assert agent.llm.usage_id != agent.condenser.llm.usage_id


def test_factory_noop_condenser_disables_condensation() -> None:
    factory = agent_definition_to_factory(
        AgentDefinition(name="x", condenser=NoOpCondenser())
    )
    assert isinstance(factory(_make_test_llm()).condenser, NoOpCondenser)


def test_factory_explicit_condenser_passthrough() -> None:
    custom = LLMSummarizingCondenser(
        llm=_make_test_llm().model_copy(update={"usage_id": "custom-condenser"}),
        max_size=40,
        keep_first=2,
    )
    factory = agent_definition_to_factory(AgentDefinition(name="x", condenser=custom))
    agent = factory(_make_test_llm())
    assert isinstance(agent.condenser, LLMSummarizingCondenser)
    assert agent.condenser.max_size == 40


def test_factory_explicit_condenser_fresh_per_spawn() -> None:
    """Explicit condensers are copied per spawn so sub-agents don't share one
    Metrics object (cross-contamination/race), and a colliding usage_id is
    normalized so condenser tokens aren't deduped out of stats."""
    custom = LLMSummarizingCondenser(
        llm=_make_test_llm(),  # same usage_id as the agent -> must be normalized
        max_size=40,
        keep_first=2,
    )
    factory = agent_definition_to_factory(AgentDefinition(name="x", condenser=custom))
    a1 = factory(_make_test_llm())
    a2 = factory(_make_test_llm())

    c1, c2 = a1.condenser, a2.condenser
    assert isinstance(c1, LLMSummarizingCondenser)
    assert isinstance(c2, LLMSummarizingCondenser)
    # Fresh per spawn: distinct condenser, LLM, and Metrics objects.
    assert c1 is not c2
    assert c1.llm is not c2.llm
    assert c1.llm.metrics is not c2.llm.metrics
    # Colliding usage_id normalized; config preserved through the copy.
    assert c1.llm.usage_id == "condenser"
    assert c1.llm.usage_id != a1.llm.usage_id
    assert c1.max_size == 40


def test_factory_explicit_condenser_preserves_distinct_usage_id() -> None:
    """A condenser usage_id that already differs from the agent's is kept."""
    custom = LLMSummarizingCondenser(
        llm=_make_test_llm().model_copy(update={"usage_id": "my-condenser"}),
        max_size=40,
        keep_first=2,
    )
    factory = agent_definition_to_factory(AgentDefinition(name="x", condenser=custom))
    agent = factory(_make_test_llm())
    assert isinstance(agent.condenser, LLMSummarizingCondenser)
    assert agent.condenser.llm.usage_id == "my-condenser"
