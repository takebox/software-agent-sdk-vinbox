---
title: Context
description: Tracks and knowledge that agents can rely on during conversations. Provides repository context and structured knowledge.
---

# Context

Context provides tracks and knowledge the agent can rely on during a conversation.

## Key Components

- **AgentContext**: Composes tracks and runtime context; pass to Agent to condition behavior
- **Track**: Embeds structured knowledge with different trigger types:
  - **trigger=None**: Activates for all conversations (repository-wide context)
  - **KeywordTrigger**: Activates when specific keywords appear in user messages
  - **TaskTrigger**: Activates based on task-specific conditions

## Quick Example

```python
from handprint.sdk.context import AgentContext, KeywordTrigger, Track

agent_context = AgentContext(
    tracks=[
        Track(
            name="repo-guidelines",
            content="Repository-wide coding standards and best practices.",
            source="AGENTS.md",
            trigger=None,  # Always-active track
        ),
        Track(
            name="flarglebargle",
            content="If the user says flarglebargle, compliment them.",
            source="flarglebargle.md",
            trigger=KeywordTrigger(keywords=["flarglebargle"]),
        ),
    ],
    # current_datetime defaults to datetime.now() for time awareness
)
```
