from pydantic import SecretStr

from handprint.sdk.launch import LaunchRuntime, preview_launch
from handprint.sdk.profiles.agent_profile import ACPAgentProfile, HandprintAgentProfile
from handprint.sdk.settings.model import HandprintAgentSettings
from handprint.sdk.tracks import Track
from tests.sdk.launch import fakes


CATALOG = [Track(name="alpha", content="a"), Track(name="beta", content="b")]


def test_a_dangling_mcp_ref_still_reports_the_llm_and_tracks():
    profile = HandprintAgentProfile(
        name="p",
        llm_profile_ref="default",
        mcp_server_refs=["missing"],
        disabled_tracks=["beta"],
    )
    stores = fakes.stores(
        llms={"default": fakes.llm(api_key=SecretStr("sk"))}, tracks=CATALOG
    )

    report = preview_launch(profile, stores, LaunchRuntime())

    assert report.valid is False
    assert report.dangling_mcp_server_refs == ["missing"]
    assert report.llm_profile_resolved is True
    assert report.llm_api_key_set is True
    assert report.resolved_tracks == ["alpha"]


def test_resolved_settings_match_what_the_launch_builds():
    profile = ACPAgentProfile(name="a", acp_server="haijun-code")

    report = preview_launch(
        profile,
        fakes.stores(tracks=CATALOG),
        LaunchRuntime(acp_track_sourcing="native"),
        load_memory=True,
    )

    assert report.valid is True
    assert report.resolved_settings is not None
    context = report.resolved_settings["agent_context"]
    assert report.resolved_tracks == context["tracks"] == []
    assert context["load_memory"] is True


def test_settings_that_cannot_build_an_agent_are_reported(monkeypatch):
    def fail(self):
        raise ValueError("OpenAI subscription login is required")

    monkeypatch.setattr(HandprintAgentSettings, "create_agent", fail)

    report = preview_launch(
        HandprintAgentProfile(name="p", llm_profile_ref="default"),
        fakes.stores(),
        LaunchRuntime(),
    )

    assert report.valid is False
    assert any("subscription login" in error for error in report.errors)
