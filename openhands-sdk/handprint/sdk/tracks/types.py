from datetime import UTC, datetime

from pydantic import BaseModel, Field


class InputMetadata(BaseModel):
    """Metadata for task track inputs."""

    name: str = Field(description="Name of the input parameter")
    description: str = Field(description="Description of the input parameter")


class TrackKnowledge(BaseModel):
    """Represents knowledge from a triggered track."""

    name: str = Field(description="The name of the track that was triggered")
    trigger: str = Field(description="The word that triggered this track")
    content: str = Field(description="The actual content/knowledge from the track")
    location: str | None = Field(
        default=None,
        description="Path to the TRACK.md file (for resolving relative resource paths)",
    )


class TrackResponse(BaseModel):
    """Response model for tracks endpoint.

    Note: This model only includes basic metadata that can be determined
    without parsing track content. Use the separate content API
    to get detailed track information.
    """

    name: str = Field(description="The name of the track")
    path: str = Field(description="The path or identifier of the track")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when the track was created",
    )


class TrackContentResponse(BaseModel):
    """Response model for individual track content endpoint."""

    content: str = Field(description="The full content of the track")
    path: str = Field(description="The path or identifier of the track")
    triggers: list[str] = Field(
        description="List of triggers associated with the track"
    )
    git_provider: str | None = Field(
        None,
        description="Git provider if the track is sourced from a Git repository",
    )
