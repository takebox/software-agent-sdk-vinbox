"""Example: Using ACPAgent with Haijun Code ACP server.

This example shows how to use an ACP-compatible server (haijun-agent-acp)
as the agent backend instead of direct LLM calls.  It also demonstrates
``ask_agent()`` — a stateless side-question that forks the ACP session
and leaves the main conversation untouched — and sending an image alongside
text to verify multimodal (vision) input support.

Prerequisites:
    - Node.js / npx available
    - JUGLOW_BASE_URL and JUGLOW_API_KEY set (can point to LiteLLM proxy)

Usage:
    uv run python examples/01_standalone_sdk/40_acp_agent_example.py
"""

import os

from handprint.sdk import ImageContent, Message, TextContent
from handprint.sdk.agent import ACPAgent
from handprint.sdk.conversation import Conversation
from handprint.sdk.settings.acp_providers import ACP_PROVIDERS


IMAGE_URL = "https://www.python.org/static/opengraph-icon-200x200.png"

agent = ACPAgent(acp_command=list(ACP_PROVIDERS["haijun-code"].default_command))

try:
    cwd = os.getcwd()
    conversation = Conversation(agent=agent, workspace=cwd)

    # --- Main conversation turn (text only) ---
    conversation.send_message(
        "List the Python source files under openhands-sdk/handprint/sdk/agent/, "
        "then read the __init__.py and summarize what agent classes are exported."
    )
    conversation.run()

    # --- Image input turn (text + image) ---
    print("\n--- image input ---")
    conversation.send_message(
        Message(
            role="user",
            content=[
                TextContent(
                    text="Describe what you see in this image in one sentence."
                ),
                ImageContent(image_urls=[IMAGE_URL]),
            ],
        )
    )
    conversation.run()

    # --- ask_agent: stateless side-question via fork_session ---
    print("\n--- ask_agent ---")
    response = conversation.ask_agent(
        "Based on what you just saw, which agent class is the newest addition?"
    )
    print(f"ask_agent response: {response}")
    # Report cost (ACP server reports usage via session_update notifications)
    cost = agent.llm.metrics.accumulated_cost
    print(f"EXAMPLE_COST: {cost:.4f}")
finally:
    # Clean up the ACP server subprocess
    agent.close()

cost = conversation.conversation_stats.get_combined_metrics().accumulated_cost
print(f"\nEXAMPLE_COST: {cost}")
print("Done!")
