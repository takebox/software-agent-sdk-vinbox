"""Example: Loading Tracks from Disk (AgentTracks Standard)

This example demonstrates how to load tracks following the AgentTracks standard
from a directory on disk.

Tracks are modular, self-contained packages that extend an agent's capabilities
by providing specialized knowledge, workflows, and tools. They follow the
AgentTracks standard which includes:
- TRACK.md file with frontmatter metadata (name, description, triggers)
- Optional resource directories: scripts/, references/, assets/

The example_tracks/ directory contains two tracks:
- rot13-encryption: Has triggers (encrypt, decrypt) - listed in <available_tracks>
  AND content auto-injected when triggered
- code-style-guide: No triggers - listed in <available_tracks> for on-demand access

All TRACK.md files follow the AgentTracks progressive disclosure model:
they are listed in <available_tracks> with name, description, and location.
Tracks with triggers get the best of both worlds: automatic content injection
when triggered, plus the agent can proactively read them anytime.
"""

import os
import sys
from pathlib import Path

from pydantic import SecretStr

from handprint.sdk import LLM, Agent, AgentContext, Conversation
from handprint.sdk.tracks import (
    discover_track_resources,
    load_tracks_from_dir,
)
from handprint.sdk.tool import Tool
from handprint.tools.file_editor import FileEditorTool
from handprint.tools.terminal import TerminalTool


# Get the directory containing this script
script_dir = Path(__file__).parent
example_tracks_dir = script_dir / "example_tracks"

# =========================================================================
# Part 1: Loading Tracks from a Directory
# =========================================================================
print("=" * 80)
print("Part 1: Loading Tracks from a Directory")
print("=" * 80)

print(f"Loading tracks from: {example_tracks_dir}")

# Discover resources in the track directory
track_subdir = example_tracks_dir / "rot13-encryption"
resources = discover_track_resources(track_subdir)
print("\nDiscovered resources in rot13-encryption/:")
print(f"  - scripts: {resources.scripts}")
print(f"  - references: {resources.references}")
print(f"  - assets: {resources.assets}")

# Load tracks from the directory
repo_tracks, knowledge_tracks, agent_tracks = load_tracks_from_dir(example_tracks_dir)

print("\nLoaded tracks from directory:")
print(f"  - Repo tracks: {list(repo_tracks.keys())}")
print(f"  - Knowledge tracks: {list(knowledge_tracks.keys())}")
print(f"  - Agent tracks (TRACK.md): {list(agent_tracks.keys())}")

# Access the loaded track and show all AgentTracks standard fields
if agent_tracks:
    track_name = next(iter(agent_tracks))
    loaded_track = agent_tracks[track_name]
    print(f"\nDetails for '{track_name}' (AgentTracks standard fields):")
    print(f"  - Name: {loaded_track.name}")
    desc = loaded_track.description or ""
    print(f"  - Description: {desc[:70]}...")
    print(f"  - License: {loaded_track.license}")
    print(f"  - Compatibility: {loaded_track.compatibility}")
    print(f"  - Metadata: {loaded_track.metadata}")
    if loaded_track.resources:
        print("  - Resources:")
        print(f"    - Scripts: {loaded_track.resources.scripts}")
        print(f"    - References: {loaded_track.resources.references}")
        print(f"    - Assets: {loaded_track.resources.assets}")
        print(f"    - Track root: {loaded_track.resources.track_root}")

# =========================================================================
# Part 2: Using Tracks with an Agent
# =========================================================================
print("\n" + "=" * 80)
print("Part 2: Using Tracks with an Agent")
print("=" * 80)

# Check for API key
api_key = os.getenv("LLM_API_KEY")
if not api_key:
    print("Skipping agent demo (LLM_API_KEY not set)")
    print("\nTo run the full demo, set the LLM_API_KEY environment variable:")
    print("  export LLM_API_KEY=your-api-key")
    sys.exit(0)

# Configure LLM
model = os.getenv("LLM_MODEL", "gpt-5.5")
llm = LLM(
    usage_id="tracks-demo",
    model=model,
    api_key=SecretStr(api_key),
    base_url=os.getenv("LLM_BASE_URL"),
)

# Create agent context with loaded tracks
agent_context = AgentContext(
    tracks=list(agent_tracks.values()),
    # Disable public tracks for this demo to keep output focused
    load_public_tracks=False,
)

# Create agent with tools so it can read track resources
tools = [
    Tool(name=TerminalTool.name),
    Tool(name=FileEditorTool.name),
]
agent = Agent(llm=llm, tools=tools, agent_context=agent_context)

# Create conversation
conversation = Conversation(agent=agent, workspace=os.getcwd())

# Test the track (triggered by "encrypt" keyword)
# The track provides instructions and a script for ROT13 encryption
print("\nSending message with 'encrypt' keyword to trigger track...")
conversation.send_message("Encrypt the message 'hello world'.")
conversation.run()

print(f"\nTotal cost: ${llm.metrics.accumulated_cost:.4f}")
print(f"EXAMPLE_COST: {llm.metrics.accumulated_cost:.4f}")
