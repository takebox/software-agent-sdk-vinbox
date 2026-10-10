"""Tests for track serialization using trigger composition."""

import json

from pydantic import BaseModel, Field, SecretStr

from handprint.sdk.mcp.config import MCPServer
from handprint.sdk.tracks import (
    KeywordTrigger,
    Track,
    TaskTrigger,
)
from handprint.sdk.tracks.types import InputMetadata
from handprint.sdk.utils.models import HandprintModel


def test_repo_track_serialization():
    """Test Track with trigger=None (always-active) serialization."""
    # Create a Track with trigger=None (always-active)
    repo_track = Track(
        name="test-repo",
        content="Repository-specific instructions",
        source="test-repo.md",
        trigger=None,
    )

    # Test serialization
    serialized = repo_track.model_dump()
    assert serialized["trigger"] is None
    assert serialized["name"] == "test-repo"
    assert serialized["content"] == "Repository-specific instructions"
    assert serialized["source"] == "test-repo.md"
    assert serialized["mcp_tools"] is None

    # Test JSON serialization
    json_str = repo_track.model_dump_json()
    assert isinstance(json_str, str)
    parsed = json.loads(json_str)
    assert parsed["trigger"] is None

    # Test deserialization
    deserialized = Track.model_validate(serialized)
    assert deserialized.trigger is None
    assert deserialized == repo_track


def test_knowledge_track_serialization():
    """Test Track with KeywordTrigger serialization and deserialization."""
    # Create a Track with KeywordTrigger
    knowledge_track = Track(
        name="test-knowledge",
        content="Knowledge-based instructions",
        source="test-knowledge.md",
        trigger=KeywordTrigger(keywords=["python", "testing"]),
    )

    # Test serialization
    serialized = knowledge_track.model_dump()
    assert serialized["trigger"]["type"] == "keyword"
    assert serialized["name"] == "test-knowledge"
    assert serialized["content"] == "Knowledge-based instructions"
    assert serialized["trigger"]["keywords"] == ["python", "testing"]

    # Test JSON serialization
    json_str = knowledge_track.model_dump_json()
    assert isinstance(json_str, str)
    parsed = json.loads(json_str)
    assert parsed["trigger"]["type"] == "keyword"

    # Test deserialization
    deserialized = Track.model_validate(serialized)
    assert deserialized == knowledge_track


def test_task_track_serialization():
    """Test Track with TaskTrigger serialization and deserialization."""
    # Create a Track with TaskTrigger
    task_track = Track(
        name="test-task",
        content="Task-based instructions with ${variable}",
        source="test-task.md",
        trigger=TaskTrigger(triggers=["task", "automation"]),
        inputs=[
            InputMetadata(name="variable", description="A test variable"),
        ],
    )

    # Test serialization
    serialized = task_track.model_dump()
    assert serialized["trigger"]["type"] == "task"
    assert serialized["name"] == "test-task"
    assert "Task-based instructions with ${variable}" in serialized["content"]
    assert serialized["trigger"]["triggers"] == ["task", "automation"]
    assert len(serialized["inputs"]) == 1
    assert serialized["inputs"][0]["name"] == "variable"

    # Test JSON serialization
    json_str = task_track.model_dump_json()
    assert isinstance(json_str, str)
    parsed = json.loads(json_str)
    assert parsed["trigger"]["type"] == "task"

    # Test deserialization
    deserialized = Track.model_validate(serialized)
    assert deserialized == task_track


def test_track_union_serialization_roundtrip():
    """Test complete serialization roundtrip for all trigger types."""
    # Test data for each trigger type
    test_cases = [
        Track(
            name="repo-test",
            content="Repo content",
            source="repo.md",
            trigger=None,
        ),
        Track(
            name="knowledge-test",
            content="Knowledge content",
            source="knowledge.md",
            trigger=KeywordTrigger(keywords=["test"]),
        ),
        Track(
            name="task-test",
            content="Task content with ${var}",
            source="task.md",
            trigger=TaskTrigger(triggers=["task"]),
            inputs=[InputMetadata(name="var", description="Test variable")],
        ),
    ]

    for original_track in test_cases:
        # Serialize to dict
        serialized = original_track.model_dump()

        # Serialize to JSON string
        json_str = original_track.model_dump_json()

        # Deserialize from dict
        deserialized_from_dict = Track.model_validate(serialized)

        # Deserialize from JSON string
        deserialized_from_json = Track.model_validate_json(json_str)

        # Verify all versions are equivalent
        assert deserialized_from_dict == original_track
        assert deserialized_from_json == original_track


def test_track_union_polymorphic_list():
    """Test that a list of Tracks can contain different trigger types."""
    # Create a list with different trigger types
    tracks = [
        Track(
            name="repo1",
            content="Repo content",
            source="repo1.md",
            trigger=None,
        ),
        Track(
            name="knowledge1",
            content="Knowledge content",
            source="knowledge1.md",
            trigger=KeywordTrigger(keywords=["test"]),
        ),
        Track(
            name="task1",
            content="Task content",
            source="task1.md",
            trigger=TaskTrigger(triggers=["task"]),
        ),
    ]

    # Serialize the list
    serialized_list = [track.model_dump() for track in tracks]

    # Verify each item has correct trigger type
    assert serialized_list[0]["trigger"] is None  # Always-active track
    assert serialized_list[1]["trigger"]["type"] == "keyword"
    assert serialized_list[2]["trigger"]["type"] == "task"

    # Test JSON serialization of the list
    json_str = json.dumps(serialized_list)
    parsed_list = json.loads(json_str)

    assert len(parsed_list) == 3
    assert parsed_list[0]["trigger"] is None  # Always-active track
    assert parsed_list[1]["trigger"]["type"] == "keyword"
    assert parsed_list[2]["trigger"]["type"] == "task"

    # reconstruct the list from serialized data
    deserialized_list = [Track.model_validate(item) for item in serialized_list]

    assert len(deserialized_list) == 3
    assert deserialized_list[0].trigger is None
    assert isinstance(deserialized_list[1].trigger, KeywordTrigger)
    assert isinstance(deserialized_list[2].trigger, TaskTrigger)
    assert deserialized_list[0] == tracks[0]
    assert deserialized_list[1] == tracks[1]
    assert deserialized_list[2] == tracks[2]


def test_discriminated_union_with_handprint_model():
    """Test trigger discrimination functionality with HandprintModel."""

    class TestModel(HandprintModel):
        tracks: list[Track] = Field(default_factory=list)

    # Create test data with different trigger types
    test_data = {
        "tracks": [
            {
                "kind": "Track",
                "name": "test-repo",
                "content": "Repo content",
                "source": "repo.md",
                "trigger": None,  # Always-active track
                "mcp_tools": None,
            },
            {
                "kind": "Track",
                "name": "test-knowledge",
                "content": "Knowledge content",
                "source": "knowledge.md",
                "trigger": {"type": "keyword", "keywords": ["test"]},
            },
            {
                "kind": "Track",
                "name": "test-task",
                "content": "Task content",
                "source": "task.md",
                "trigger": {"type": "task", "triggers": ["task"]},
                "inputs": [],
            },
        ]
    }

    # Validate the model - this tests the trigger discrimination
    model = TestModel.model_validate(test_data)

    # Verify each track was correctly discriminated
    assert len(model.tracks) == 3
    assert model.tracks[0].trigger is None
    assert isinstance(model.tracks[1].trigger, KeywordTrigger)
    assert isinstance(model.tracks[2].trigger, TaskTrigger)

    # Verify trigger types are correct
    # First track is always-active (trigger is None)
    assert model.tracks[1].trigger.type == "keyword"
    assert model.tracks[2].trigger.type == "task"


def test_discriminated_union_with_pydantic_model():
    """Test trigger discrimination functionality with Pydantic BaseModel."""

    class TestModel(BaseModel):
        tracks: list[Track] = Field(default_factory=list)

    # Create test data with different trigger types
    test_data = {
        "tracks": [
            {
                "name": "test-repo",
                "content": "Repo content",
                "source": "repo.md",
                "trigger": None,  # Always-active track
                "mcp_tools": None,
            },
            {
                "name": "test-knowledge",
                "content": "Knowledge content",
                "source": "knowledge.md",
                "trigger": {"type": "keyword", "keywords": ["test"]},
            },
            {
                "name": "test-task",
                "content": "Task content",
                "source": "task.md",
                "trigger": {"type": "task", "triggers": ["task"]},
                "inputs": [],
            },
        ]
    }

    # Validate the model - this tests the trigger discrimination
    model = TestModel.model_validate(test_data)

    # Verify each track was correctly discriminated
    assert len(model.tracks) == 3
    assert model.tracks[0].trigger is None
    assert isinstance(model.tracks[1].trigger, KeywordTrigger)
    assert isinstance(model.tracks[2].trigger, TaskTrigger)

    # Verify trigger types are correct
    # First track is always-active (trigger is None)
    assert model.tracks[1].trigger.type == "keyword"
    assert model.tracks[2].trigger.type == "task"


# A clearly identifiable secret value for the mcp_tools masking tests.
_MCP_SECRET = "ghp_SUPER_SECRET_TOKEN_SHOULD_NOT_LEAK"


def _track_with_mcp_secret() -> Track:
    return Track(
        name="leaky",
        content="do stuff",
        mcp_tools={
            "svc": MCPServer(
                url="https://x.test",
                headers={"Authorization": SecretStr(f"Bearer {_MCP_SECRET}")},
                env={"API_KEY": SecretStr(_MCP_SECRET)},
            )
        },
    )


def test_mcp_tools_secrets_redacted_by_default():
    """mcp_tools env/headers carry MCP credentials; they must be redacted at
    rest, just like settings mcp_config -- not dumped in plaintext."""
    track = _track_with_mcp_secret()

    dumped = json.dumps(track.model_dump(mode="json"))
    assert _MCP_SECRET not in dumped

    json_dumped = track.model_dump_json()
    assert _MCP_SECRET not in json_dumped


def test_mcp_tools_secrets_exposed_under_expose_secrets():
    """Opt-in exposure surfaces the real values (parity with mcp_config)."""
    track = _track_with_mcp_secret()

    exposed = json.dumps(
        track.model_dump(mode="json", context={"expose_secrets": "plaintext"})
    )
    assert _MCP_SECRET in exposed


def test_mcp_tools_secrets_encrypted_under_cipher():
    """With a cipher in context, secrets are encrypted (not plaintext, not
    dropped) so they can be decrypted on restore."""
    from handprint.sdk.utils.cipher import Cipher

    track = _track_with_mcp_secret()
    cipher = Cipher(secret_key="test-encryption-key")

    encrypted = json.dumps(
        track.model_dump(
            mode="json", context={"expose_secrets": "encrypted", "cipher": cipher}
        )
    )
    assert _MCP_SECRET not in encrypted
    # The server/env/header keys survive and only secret values are transformed.
    assert '"svc"' in encrypted
    assert "Authorization" in encrypted
    assert "headers" in encrypted
    assert "API_KEY" in encrypted


def test_mcp_tools_real_values_remain_accessible_in_memory():
    """Masking is serialization-only: the live attribute keeps real values so
    runtime MCP usage is unaffected."""
    track = _track_with_mcp_secret()

    assert track.mcp_tools is not None
    env = track.mcp_tools["svc"].env
    assert env is not None
    assert env["API_KEY"].get_secret_value() == _MCP_SECRET


def test_mcp_tools_none_round_trips_unchanged():
    """A track without mcp_tools still serializes mcp_tools as None."""
    track = Track(name="clean", content="hello")
    dumped = track.model_dump(mode="json")
    assert dumped["mcp_tools"] is None
    assert Track.model_validate(dumped) == track
