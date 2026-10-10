from pydantic import SecretStr

from handprint.agent_server.openai.service import _with_profile_llm_and_system_text
from handprint.sdk.llm import LLM
from handprint.sdk.settings import ACPAgentSettings, HandprintAgentSettings


def test_profile_llm_is_not_applied_to_acp_settings():
    updated = _with_profile_llm_and_system_text(
        ACPAgentSettings(acp_model="sonnet"),
        LLM(model="gpt-4o", api_key=SecretStr("sk-profile")),
        "Be terse.",
    )

    assert isinstance(updated, ACPAgentSettings)
    assert "llm" not in updated.model_fields_set
    assert updated.agent_context is not None
    assert updated.agent_context.system_message_suffix == "Be terse."


def test_profile_llm_is_applied_to_handprint_settings():
    updated = _with_profile_llm_and_system_text(
        HandprintAgentSettings(), LLM(model="gpt-4o"), ""
    )

    assert isinstance(updated, HandprintAgentSettings)
    assert updated.llm.model == "gpt-4o"
