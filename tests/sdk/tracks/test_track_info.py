"""Tests for Track.to_track_info() and related methods."""

from typing import Literal, get_args

from handprint.sdk.tracks import (
    KeywordTrigger,
    Track,
    TaskTrigger,
)
from handprint.sdk.tracks.track import TrackInfo


TrackType = Literal["repo", "knowledge", "agenttracks"]


class TestTrackGetTrackType:
    """Tests for Track.get_track_type() method."""

    def test_repo_track_type(self):
        """Test that a track with trigger=None returns 'repo' type."""
        track = Track(
            name="test-repo",
            content="Repository instructions",
            trigger=None,
        )
        assert track.get_track_type() == "repo"

    def test_knowledge_track_type_with_keyword_trigger(self):
        """Test that a track with KeywordTrigger returns 'knowledge' type."""
        track = Track(
            name="test-knowledge",
            content="Knowledge instructions",
            trigger=KeywordTrigger(keywords=["python", "testing"]),
        )
        assert track.get_track_type() == "knowledge"

    def test_knowledge_track_type_with_task_trigger(self):
        """Test that a track with TaskTrigger returns 'knowledge' type."""
        track = Track(
            name="test-task",
            content="Task instructions",
            trigger=TaskTrigger(triggers=["task"]),
        )
        assert track.get_track_type() == "knowledge"

    def test_agent_track_type(self):
        """Test that an AgentTracks format track returns 'agenttracks' type."""
        track = Track(
            name="test-agent",
            content="Agent instructions",
            trigger=None,
            is_agenttracks_format=True,
        )
        assert track.get_track_type() == "agenttracks"

    def test_agent_track_type_with_trigger(self):
        """Test that AgentTracks format takes precedence over trigger type."""
        track = Track(
            name="test-agent",
            content="Agent instructions",
            trigger=KeywordTrigger(keywords=["test"]),
            is_agenttracks_format=True,
        )
        # AgentTracks format should return 'agenttracks' even with triggers
        assert track.get_track_type() == "agenttracks"


class TestTrackGetTriggers:
    """Tests for Track.get_triggers() method."""

    def test_no_triggers(self):
        """Test that a track with trigger=None returns empty list."""
        track = Track(
            name="test-repo",
            content="Repository instructions",
            trigger=None,
        )
        assert track.get_triggers() == []

    def test_keyword_triggers(self):
        """Test that KeywordTrigger returns its keywords."""
        track = Track(
            name="test-knowledge",
            content="Knowledge instructions",
            trigger=KeywordTrigger(keywords=["python", "testing", "pytest"]),
        )
        assert track.get_triggers() == ["python", "testing", "pytest"]

    def test_task_triggers(self):
        """Test that TaskTrigger returns its triggers."""
        track = Track(
            name="test-task",
            content="Task instructions",
            trigger=TaskTrigger(triggers=["/deploy", "/build"]),
        )
        assert track.get_triggers() == ["/deploy", "/build"]

    def test_empty_keyword_triggers(self):
        """Test KeywordTrigger with empty keywords list."""
        track = Track(
            name="test-empty",
            content="Instructions",
            trigger=KeywordTrigger(keywords=[]),
        )
        assert track.get_triggers() == []


class TestTrackToTrackInfo:
    """Tests for Track.to_track_info() method."""

    def test_repo_track_to_info(self):
        """Test conversion of repo track to TrackInfo."""
        track = Track(
            name="test-repo",
            content="Repository instructions",
            source="/path/to/track.md",
            description="A test repository track",
            trigger=None,
        )
        info = track.to_track_info()

        assert isinstance(info, TrackInfo)
        assert info.name == "test-repo"
        assert info.type == "repo"
        assert info.content == "Repository instructions"
        assert info.triggers == []
        assert info.source == "/path/to/track.md"
        assert info.description == "A test repository track"
        assert info.is_agenttracks_format is False

    def test_knowledge_track_to_info(self):
        """Test conversion of knowledge track to TrackInfo."""
        track = Track(
            name="test-knowledge",
            content="Knowledge instructions",
            source="/path/to/knowledge.md",
            trigger=KeywordTrigger(keywords=["python", "coding"]),
        )
        info = track.to_track_info()

        assert isinstance(info, TrackInfo)
        assert info.name == "test-knowledge"
        assert info.type == "knowledge"
        assert info.content == "Knowledge instructions"
        assert info.triggers == ["python", "coding"]
        assert info.source == "/path/to/knowledge.md"
        assert info.description is None
        assert info.is_agenttracks_format is False

    def test_agent_track_to_info(self):
        """Test conversion of AgentTracks format track to TrackInfo."""
        track = Track(
            name="pdf-tools",
            content="PDF processing instructions",
            source="/tracks/pdf-tools/TRACK.md",
            description="Tools for working with PDF files",
            trigger=None,
            is_agenttracks_format=True,
        )
        info = track.to_track_info()

        assert isinstance(info, TrackInfo)
        assert info.name == "pdf-tools"
        assert info.type == "agenttracks"
        assert info.content == "PDF processing instructions"
        assert info.triggers == []
        assert info.source == "/tracks/pdf-tools/TRACK.md"
        assert info.description == "Tools for working with PDF files"
        assert info.is_agenttracks_format is True
        assert info.disable_model_invocation is False

    def test_agent_track_to_info_preserves_disable_model_invocation(self):
        """AgentTracks direct-invocation metadata should survive serialization."""
        track = Track(
            name="trigger-only",
            content="Trigger-only instructions",
            source="/tracks/trigger-only/TRACK.md",
            description="Trigger-only track",
            trigger=KeywordTrigger(keywords=["trigger-only"]),
            is_agenttracks_format=True,
            disable_model_invocation=True,
        )
        info = track.to_track_info()

        assert info.disable_model_invocation is True

    def test_task_track_to_info(self):
        """Test conversion of task track to TrackInfo."""
        track = Track(
            name="deploy-task",
            content="Deployment instructions with ${env}",
            source="/tasks/deploy.md",
            trigger=TaskTrigger(triggers=["/deploy"]),
        )
        info = track.to_track_info()

        assert isinstance(info, TrackInfo)
        assert info.name == "deploy-task"
        assert info.type == "knowledge"
        # TaskTrigger appends guidance about variables to the content
        assert "Deployment instructions with ${env}" in info.content
        assert info.triggers == ["/deploy"]
        assert info.source == "/tasks/deploy.md"

    def test_track_info_with_none_values(self):
        """Test TrackInfo handles None values correctly."""
        track = Track(
            name="minimal",
            content="Minimal content",
            trigger=None,
        )
        info = track.to_track_info()

        assert info.name == "minimal"
        assert info.type == "repo"
        assert info.content == "Minimal content"
        assert info.triggers == []
        assert info.source is None
        assert info.description is None
        assert info.is_agenttracks_format is False


class TestTrackInfoDataclass:
    """Tests for the TrackInfo dataclass itself."""

    def test_track_info_creation(self):
        """Test direct creation of TrackInfo."""
        info = TrackInfo(
            name="test",
            type="repo",
            content="content",
            triggers=[],
            source=None,
            description=None,
            is_agenttracks_format=False,
        )
        assert info.name == "test"
        assert info.type == "repo"

    def test_track_info_with_all_types(self):
        """Test TrackInfo accepts all valid type values."""
        for track_type in get_args(TrackType):
            info = TrackInfo(
                name="test",
                type=track_type,
                content="content",
                triggers=[],
                source=None,
                description=None,
                is_agenttracks_format=False,
            )
            assert info.type == track_type

    def test_track_info_equality(self):
        """Test TrackInfo equality comparison."""
        info1 = TrackInfo(
            name="test",
            type="repo",
            content="content",
            triggers=["a", "b"],
            source="/path",
            description="desc",
            is_agenttracks_format=True,
        )
        info2 = TrackInfo(
            name="test",
            type="repo",
            content="content",
            triggers=["a", "b"],
            source="/path",
            description="desc",
            is_agenttracks_format=True,
        )
        assert info1 == info2

    def test_track_info_inequality(self):
        """Test TrackInfo inequality comparison."""
        info1 = TrackInfo(
            name="test1",
            type="repo",
            content="content",
            triggers=[],
            source=None,
            description=None,
            is_agenttracks_format=False,
        )
        info2 = TrackInfo(
            name="test2",
            type="repo",
            content="content",
            triggers=[],
            source=None,
            description=None,
            is_agenttracks_format=False,
        )
        assert info1 != info2
