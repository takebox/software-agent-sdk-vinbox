"""Task tool package for sub-agent delegation.

This package provides a TaskToolSet tool to delegate tasks to subagent.

Tools:
    - task: Launch and run a (blocking) sub-agent task.

Usage:
    from handprint.tools.task import TaskToolSet

    agent = Agent(
        llm=llm,
        tools=[
            Tool(name=TerminalTool.name),
            Tool(name=TaskToolSet.name),
        ],
    )
"""

from handprint.tools.task.definition import (
    TaskAction,
    TaskObservation,
    TaskTool,
    TaskToolSet,
)
from handprint.tools.task.impl import TaskExecutor


__all__ = [
    "TaskAction",
    "TaskExecutor",
    "TaskObservation",
    "TaskTool",
    "TaskToolSet",
]
