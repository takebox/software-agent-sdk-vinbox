# Development Guide

## Setup

```bash
git clone https://github.com/takebox/software-agent-sdk-vinbox.git
cd software-agent-sdk-vinbox
make build
```

Python 3.12+ is required. `uv` manages the workspace and the lock file
(`uv.lock` is committed and CI uses `uv sync --frozen`).

## Repository boundaries

This repository is the runtime that runs **inside Vinbox**: the Python SDK, the
tools (browser_use over CDP, pwsh terminal, file editing), the local workspace,
and the Agent Server that listens on loopback `127.0.0.1:18000`. Everything it
needs already exists in the Vinbox machine — Chromium on CDP `9222`, `pwsh`,
the model bridge on `4097`, and the dashboard at `app/dashboard-7331`. The
single source of truth for those values is
[`vinbox-sdk/handprint/sdk/vinbox.py`](vinbox-sdk/handprint/sdk/vinbox.py); read
[VINBOX.md](VINBOX.md) before adding a path, port, or provider.

The UI reference and the flow map live in
[`takebox/handprint-vinbox`](https://github.com/takebox/handprint-vinbox), which
ships no runtime. Do not add a browser bundle, a desktop shell, a static server,
or an external model provider here. Follow
[`.agents/tracks/custom-codereview-guide.md`](.agents/tracks/custom-codereview-guide.md)
for every PR.

## Code Quality

```bash
make format                              # Format code
make lint                                # Lint code
uv run pre-commit run --all-files        # Run all checks
```

Pre-commit hooks run automatically on commit with type checking and linting.

## Testing

```bash
uv run pytest                            # All tests
uv run pytest tests/sdk/                 # SDK tests only
uv run pytest tests/tools/               # Tools tests only
```

## Project Structure

```
software-agent-sdk-vinbox/
├── vinbox-sdk/          # Core SDK package
├── vinbox-tools/        # Built-in tools
├── vinbox-workspace/    # Workspace management
├── vinbox-agent-server/ # Agent server
├── examples/               # Usage examples
└── tests/                  # Test suites
```

## Contributing

1. Create a new branch
2. Make your changes
3. Run tests and checks
4. Push and create a pull request

For questions, join our [Slack community](https://handprint.dev/joinslack).

## LLM message construction invariant

**Every LLM request built in this repository must place a `system` message before
the first `user` message.**

The canonical enforcement lives in `Agent.init_state()`
(`vinbox-sdk/handprint/sdk/agent/agent.py`): it guarantees the `SystemPromptEvent`
sits at the head of the event stream (index 0/1) and raises `AssertionError` if a user
`MessageEvent` appears before it. `LLMConvertibleEvent.events_to_messages()`
(`vinbox-sdk/handprint/sdk/event/base.py`) projects the event stream to messages in
order, preserving the system lead-in on the main agent loop.

This applies to **all** standalone LLM calls, not just the agent loop: condensers, goal
judges, agent-server profile pre-flight pings, security analyzers, title generation,
cleanup prompts, hook prompts, toolshield analyzers, and vision inspect. Each must begin
its message list with a `system` role.

### Why it matters

- **Consistent steering:** standalone calls that omit a system message lose the shared
  context/format expectations other paths get.
- **Correct transport serialization:** on the OpenAI Responses API,
  `Message.to_responses_value()` returns a string for `system` (→ `instructions`) and a
  dict list for `user` (→ `input`). Sending steering instructions as a lone `user`
  message conflates "how" with "what", and a lone `system` message serializes to
  `instructions` with empty `input`.
- **Subscription/Codex transport** prepends system chunks onto the first user message;
  a missing system lead-in produces a bare, unsteered request.

### Documented exceptions

- **ACP agents:** the real system prompt and tools are managed by the ACP server, not by
  an SDK-constructed message list; the SDK emits a placeholder `SystemPromptEvent` for
  the visualizer.
- **Subscription/Codex transport** (`transform_for_subscription`): system chunks are
  prepended *into* the first user message's content because Codex-style endpoints reject
  long/complex `instructions` — ordering intent preserved, shape flattened.

### Reviewer checklist

The first message role must be `system`, or there must be a documented exception above.
