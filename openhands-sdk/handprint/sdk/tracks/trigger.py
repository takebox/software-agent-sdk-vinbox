"""Trigger types for tracks.

This module defines different trigger types that determine when a track
should be activated.
"""

from abc import ABC
from typing import Literal

from pydantic import BaseModel


class BaseTrigger(BaseModel, ABC):
    """Base class for all trigger types."""

    pass


class KeywordTrigger(BaseTrigger):
    """Trigger for keyword-based tracks.

    These tracks are activated when specific keywords appear in the user's query.
    """

    type: Literal["keyword"] = "keyword"
    keywords: list[str]


class TaskTrigger(BaseTrigger):
    """Trigger for task-specific tracks.

    These tracks are activated for specific task types and can modify prompts.
    """

    type: Literal["task"] = "task"
    triggers: list[str]


class PathTrigger(BaseTrigger):
    """Trigger for path-scoped tracks ("rules").

    These tracks are activated when the agent touches a file whose path matches
    one of the ``paths`` glob patterns (gitignore-style ``**`` semantics).
    """

    type: Literal["path"] = "path"
    paths: list[str]
