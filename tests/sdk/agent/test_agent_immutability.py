"""Tests for the Agent immutability contract."""

import pytest
from pydantic import ValidationError

from handprint.sdk.agent.agent import Agent
from handprint.sdk.llm import LLM


def test_agent_is_frozen():
    agent = Agent(llm=LLM(model="gpt-4o-mini", usage_id="test-llm"), tools=[])

    with pytest.raises(ValidationError, match="Instance is frozen"):
        agent.agent_context = None
