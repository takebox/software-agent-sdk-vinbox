"""``secret_refs`` — the profile's allow-list over a conversation's secrets."""

from handprint.sdk.profiles import validate_agent_profile


def _handprint(**overrides):
    return validate_agent_profile(
        {"name": "explorer", "llm_profile_ref": "default", **overrides}
    )


def _acp(**overrides):
    return validate_agent_profile(
        {
            "name": "haijun",
            "agent_kind": "acp",
            "acp_server": "haijun-code",
            **overrides,
        }
    )


def test_defaults_to_unrestricted():
    assert _handprint().secret_refs is None
    assert _acp().secret_refs is None


class TestPersistence:
    def test_a_profile_without_the_key_loads_unrestricted(self):
        # Profiles written before the field existed carry no `secret_refs`.
        profile = validate_agent_profile(
            {"schema_version": 2, "name": "old", "llm_profile_ref": "default"}
        )
        assert profile.secret_refs is None

    def test_the_field_round_trips(self):
        profile = _handprint(secret_refs=["A", "B"])
        assert validate_agent_profile(profile.model_dump()).secret_refs == ["A", "B"]
