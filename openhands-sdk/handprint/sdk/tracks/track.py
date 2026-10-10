import io
import json
import os
import re
import threading
import time
from collections.abc import Iterable, Mapping
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, ClassVar, Final, Literal, Union
from xml.sax.saxutils import escape as xml_escape

import frontmatter
import yaml
from pydantic import (
    BaseModel,
    Field,
    SerializationInfo,
    ValidationInfo,
    field_serializer,
    field_validator,
    model_validator,
)

from handprint.sdk.logger import get_logger
from handprint.sdk.mcp.config import MCPServer, coerce_mcp_config, dump_mcp_config
from handprint.sdk.tracks.exceptions import TrackError, TrackValidationError
from handprint.sdk.tracks.execute import render_content_with_commands
from handprint.sdk.tracks.trigger import (
    KeywordTrigger,
    PathTrigger,
    TaskTrigger,
)
from handprint.sdk.tracks.types import InputMetadata
from handprint.sdk.tracks.utils import (
    discover_track_resources,
    find_mcp_config,
    find_nested_third_party_files,
    find_regular_md_files,
    find_track_md_directories,
    find_third_party_files,
    get_tracks_cache_dir,
    is_tracks_repo_pinned,
    load_and_categorize,
    load_mcp_config,
    update_tracks_repository,
    validate_track_name,
)
from handprint.sdk.utils import DEFAULT_TRUNCATE_NOTICE, maybe_truncate
from handprint.sdk.utils.path import get_user_persistence_dir, to_posix_path


logger = get_logger(__name__)


# One glob token per match; longest operator first so `**/` and `**` beat `*`.
_GLOB_TOKENS: Final[re.Pattern[str]] = re.compile(r"\*\*/|\*\*|\*|\?|[^*?]+")
_GLOB_TO_REGEX: Final[dict[str, str]] = {
    "**/": "(?:.*/)?",  # any number of leading path segments (including zero)
    "**": ".*",  # anything, crossing `/` separators
    "*": "[^/]*",  # any run within a single segment
    "?": "[^/]",  # a single non-separator character
}


@lru_cache(maxsize=512)
def _compile_path_glob(pattern: str) -> re.Pattern[str]:
    """Compile a gitignore-style path glob into an anchored regex.

    Supported syntax (matched against a POSIX path):
    - ``**`` matches any number of path segments (including zero).
    - ``*`` matches any run of characters within a single segment.
    - ``?`` matches a single non-separator character.
    - A pattern without a ``/`` matches the basename at any depth, e.g.
      ``*.py`` behaves like ``**/*.py`` (gitignore semantics).

    Matching is case-sensitive. Results are cached per pattern string.
    """
    # A slash-less pattern matches at any depth.
    if "/" not in pattern:
        pattern = "**/" + pattern
    tokens: list[str] = _GLOB_TOKENS.findall(pattern)
    body = "".join(_GLOB_TO_REGEX.get(t, re.escape(t)) for t in tokens)
    return re.compile(f"(?s:{body})\\Z")


def path_matches_glob(file_path: str, pattern: str) -> bool:
    """Return True if ``file_path`` matches the gitignore-style glob ``pattern``.

    ``file_path`` is expected to be a POSIX path (typically workspace-relative).
    """
    if not pattern:
        return False
    return _compile_path_glob(pattern).fullmatch(file_path) is not None


class TrackInfo(BaseModel):
    """Lightweight representation of a track's essential information.

    This class provides a standardized, serializable format for track metadata
    that can be used across different components of the system.
    """

    name: str
    type: Literal["repo", "knowledge", "agenttracks"]
    content: str
    triggers: list[str] = Field(default_factory=list)
    source: str | None = None
    description: str | None = None
    is_agenttracks_format: bool = False
    disable_model_invocation: bool = False


class TrackResources(BaseModel):
    """Resource directories for a track (AgentTracks standard).

    Per the AgentTracks specification, tracks can include:
    - scripts/: Executable scripts the agent can run
    - references/: Reference documentation and examples
    - assets/: Static assets (images, data files, etc.)
    """

    track_root: str = Field(description="Root directory of the track (absolute path)")
    scripts: list[str] = Field(
        default_factory=list,
        description="List of script files in scripts/ directory (relative paths)",
    )
    references: list[str] = Field(
        default_factory=list,
        description="List of reference files in references/ directory (relative paths)",
    )
    assets: list[str] = Field(
        default_factory=list,
        description="List of asset files in assets/ directory (relative paths)",
    )

    def has_resources(self) -> bool:
        """Check if any resources are available."""
        return bool(self.scripts or self.references or self.assets)

    def get_scripts_dir(self) -> Path | None:
        """Get the scripts directory path if it exists."""
        scripts_dir = Path(self.track_root) / "scripts"
        return scripts_dir if scripts_dir.is_dir() else None

    def get_references_dir(self) -> Path | None:
        """Get the references directory path if it exists."""
        refs_dir = Path(self.track_root) / "references"
        return refs_dir if refs_dir.is_dir() else None

    def get_assets_dir(self) -> Path | None:
        """Get the assets directory path if it exists."""
        assets_dir = Path(self.track_root) / "assets"
        return assets_dir if assets_dir.is_dir() else None


# Union type for all trigger types
TriggerType = Annotated[
    KeywordTrigger | TaskTrigger | PathTrigger,
    Field(discriminator="type"),
]


def _keyword_matches(keyword: str, message_lower: str) -> bool:
    """Return True if ``keyword`` appears as a whole token in ``message_lower``.

    Uses alphanumeric boundaries (not ``\\b``) so ``git`` does not fire on
    ``github`` while slash-prefixed keywords like ``/linear`` still match.
    ``message_lower`` is expected to be lowercased by the caller.
    """
    keyword_lower = keyword.lower()
    if not keyword_lower:
        return False
    pattern = rf"(?<![a-z0-9]){re.escape(keyword_lower)}(?![a-z0-9])"
    return re.search(pattern, message_lower) is not None


class Track(BaseModel):
    """A track provides specialized knowledge or functionality.

    Track behavior depends on format (is_agenttracks_format) and trigger:

    AgentTracks format (TRACK.md files):
    - Always listed in <available_tracks> with name, description, location
    - Agent reads full content on demand (progressive disclosure)
    - If has triggers: content is ALSO auto-injected when triggered

    Legacy Handprint format:
    - With triggers: Listed in <available_tracks>, content injected on trigger
    - Without triggers (None): Full content in <REPO_CONTEXT>, always active

    This model supports both Handprint-specific fields and AgentTracks standard
    fields (https://agenttracks.io/specification) for cross-platform compatibility.
    """

    name: str
    content: str
    trigger: TriggerType | None = Field(
        default=None,
        description=(
            "Trigger determines when track content is auto-injected. "
            "None = no auto-injection (for AgentTracks: agent reads on demand; "
            "for legacy: full content always in system prompt). "
            "KeywordTrigger = auto-inject when keywords appear in user messages. "
            "TaskTrigger = auto-inject for specific tasks, may require user input."
        ),
    )
    source: str | None = Field(
        default=None,
        description=(
            "The source path or identifier of the track. "
            "When it is None, it is treated as a programmatically defined track."
        ),
    )
    mcp_tools: dict[str, MCPServer] | None = Field(
        default=None,
        description=("MCP servers for the track (repo tracks only)."),
    )
    inputs: list[InputMetadata] = Field(
        default_factory=list,
        description="Input metadata for the track (task tracks only)",
    )
    is_agenttracks_format: bool = Field(
        default=False,
        description=(
            "Whether this track was loaded from a TRACK.md file following the "
            "AgentTracks standard. AgentTracks-format tracks use progressive "
            "disclosure: always listed in <available_tracks> with name, "
            "description, and location. If the track also has triggers, content "
            "is auto-injected when triggered AND agent can read file anytime."
        ),
    )

    # AgentTracks specification: description must be 1-1024 characters.
    MAX_DESCRIPTION_LENGTH: ClassVar[int] = 1024

    # AgentTracks standard fields (https://agenttracks.io/specification)
    version: str = Field(
        default="1.0.0",
        description="Track version (AgentTracks standard field).",
    )
    description: str | None = Field(
        default=None,
        description=(
            "A brief description of what the track does and when to use it. "
            "Descriptions exceeding MAX_DESCRIPTION_LENGTH are truncated "
            "with a notice pointing to the track's source path."
        ),
    )
    license: str | None = Field(
        default=None,
        description=(
            "The license under which the track is distributed. "
            "AgentTracks standard field (e.g., 'Apache-2.0', 'MIT')."
        ),
    )
    compatibility: str | None = Field(
        default=None,
        description=(
            "Environment requirements or compatibility notes for the track. "
            "AgentTracks standard field (e.g., 'Requires git and docker')."
        ),
    )
    metadata: dict[str, str] | None = Field(
        default=None,
        description=(
            "Arbitrary key-value metadata for the track. "
            "AgentTracks standard field for extensibility."
        ),
    )
    allowed_tools: list[str] | None = Field(
        default=None,
        description=(
            "List of pre-approved tools for this track. "
            "AgentTracks standard field (parsed from space-delimited string)."
        ),
    )
    disable_model_invocation: bool = Field(
        default=False,
        description=(
            "Whether this track can only be activated by trigger matching and "
            "should not be advertised to the model for direct invocation."
        ),
    )
    resources: TrackResources | None = Field(
        default=None,
        description=(
            "Resource directories for the track (scripts/, references/, assets/). "
            "AgentTracks standard field. Only populated for TRACK.md directory format."
        ),
    )

    _DESCRIPTION_TRUNCATE_NOTICE = (
        "<response clipped><NOTE>Due to the max output limit, only part of "
        "the full description is shown. You can view the complete track "
        "content at {source}.</NOTE>"
    )

    @field_validator("allowed_tools", mode="before")
    @classmethod
    def _parse_allowed_tools(cls, v: str | list | None) -> list[str] | None:
        """Parse allowed_tools from space-delimited string or list."""
        if v is None:
            return None
        if isinstance(v, str):
            return v.split()
        if isinstance(v, list):
            return [str(t) for t in v]
        raise TrackValidationError("allowed-tools must be a string or list")

    @field_validator("metadata", mode="before")
    @classmethod
    def _convert_metadata_values(cls, v: dict | None) -> dict[str, str] | None:
        """Convert metadata values to strings."""
        if v is None:
            return None
        if isinstance(v, dict):
            return {str(k): str(val) for k, val in v.items()}
        raise TrackValidationError("metadata must be a dictionary")

    @field_validator("mcp_tools", mode="before")
    @classmethod
    def _validate_mcp_tools(
        cls, v: object, info: ValidationInfo
    ) -> dict[str, MCPServer] | None:
        """Validate track MCP tools as native MCP server models."""
        if v is None:
            return None
        if not isinstance(v, Mapping):
            raise TrackValidationError("mcp_tools must be a dictionary or None")
        try:
            return coerce_mcp_config(v, context=info.context)
        except Exception as e:
            raise TrackValidationError(f"Invalid MCP config dictionary: {e}") from e

    @field_serializer("mcp_tools")
    def _serialize_mcp_tools(
        self, value: dict[str, MCPServer] | None, info: SerializationInfo
    ) -> dict[str, dict[str, Any]] | None:
        if value is None:
            return None
        if not value:
            return {}
        return dump_mcp_config(value, context=info.context or {})

    PATH_TO_THIRD_PARTY_TRACK_NAME: ClassVar[dict[str, str]] = {
        ".cursorrules": "cursorrules",
        "agents.md": "agents",
        "agent.md": "agents",
        "haijun.md": "haijun",
        "gemini.md": "gemini",
    }

    @classmethod
    def load(
        cls,
        path: str | Path,
        track_base_dir: Path | None = None,
        strict: bool = True,
        skip_mcp: bool = False,
    ) -> "Track":
        """Load a track from a markdown file with frontmatter.

        The agent's name is derived from its path relative to track_base_dir,
        or from the directory name for AgentTracks-style TRACK.md files.

        Supports both Handprint-specific frontmatter fields and AgentTracks
        standard fields (https://agenttracks.io/specification).

        Args:
            path: Path to the track file.
            track_base_dir: Base directory for tracks (used to derive relative names).
            strict: If True, enforce strict AgentTracks name validation.
                If False, allow relaxed naming (e.g., for plugin compatibility).
            skip_mcp: If True, skip loading MCP configuration from .mcp.json.
                Used when loading root plugin tracks where MCP config is already
                loaded at the plugin level to avoid double-loading.
        """
        path = Path(path) if isinstance(path, str) else path

        with open(path, encoding="utf-8") as f:
            file_content = f.read()

        if path.name.lower() == "track.md":
            return cls._load_agenttracks_track(
                path, file_content, strict=strict, skip_mcp=skip_mcp
            )
        else:
            return cls._load_legacy_handprint_track(path, file_content, track_base_dir)

    @classmethod
    def _load_agenttracks_track(
        cls, path: Path, file_content: str, strict: bool = True, skip_mcp: bool = False
    ) -> "Track":
        """Load a track from an AgentTracks-format TRACK.md file.

        Args:
            path: Path to the TRACK.md file.
            file_content: Content of the file.
            strict: If True, enforce strict AgentTracks name validation.
            skip_mcp: If True, skip loading MCP configuration from .mcp.json.
        """
        # For TRACK.md files, use parent directory name as the track name
        directory_name = path.parent.name
        track_root = path.parent

        file_io = io.StringIO(file_content)
        loaded = frontmatter.load(file_io)
        content = loaded.content
        metadata_dict = loaded.metadata or {}

        # Use name from frontmatter if provided, otherwise use directory name
        agent_name = str(metadata_dict.get("name", directory_name))

        # Validate track name (only in strict mode)
        if strict:
            name_errors = validate_track_name(agent_name, directory_name)
            if name_errors:
                raise TrackValidationError(
                    f"Invalid track name '{agent_name}': {'; '.join(name_errors)}"
                )

        # Load MCP configuration from .mcp.json (agent_tracks ONLY use .mcp.json)
        mcp_tools: dict[str, MCPServer] | None = None
        if not skip_mcp:
            mcp_json_path = find_mcp_config(track_root)
            if mcp_json_path:
                mcp_config = load_mcp_config(mcp_json_path, track_root)
                mcp_tools = coerce_mcp_config(mcp_config.get("mcpServers", {}))

        # Discover resource directories
        resources: TrackResources | None = None
        discovered_resources = discover_track_resources(track_root)
        if discovered_resources.has_resources():
            resources = discovered_resources

        return cls._create_track_from_metadata(
            agent_name,
            content,
            path,
            metadata_dict,
            mcp_tools,
            resources=resources,
            is_agenttracks_format=True,
        )

    @classmethod
    def _load_legacy_handprint_track(
        cls, path: Path, file_content: str, track_base_dir: Path | None
    ) -> "Track":
        """Load a track from a legacy Handprint-format file.

        Args:
            path: Path to the track file.
            file_content: Content of the file.
            track_base_dir: Base directory for tracks (used to derive relative names).
        """
        # Handle third-party agent instruction files
        third_party_agent = cls._handle_third_party(path, file_content)
        if third_party_agent is not None:
            return third_party_agent

        # Calculate derived name from path
        if track_base_dir is not None:
            track_name = cls.PATH_TO_THIRD_PARTY_TRACK_NAME.get(
                path.name.lower()
            ) or to_posix_path(path.relative_to(track_base_dir).with_suffix(""))
        else:
            track_name = path.stem

        file_io = io.StringIO(file_content)
        loaded = frontmatter.load(file_io)
        content = loaded.content
        metadata_dict = loaded.metadata or {}

        # Use name from frontmatter if provided, otherwise use derived name
        agent_name = str(metadata_dict.get("name", track_name))

        # Legacy tracks ONLY use mcp_tools from frontmatter (not .mcp.json)
        mcp_tools = metadata_dict.get("mcp_tools")
        if mcp_tools is not None and not isinstance(mcp_tools, dict):
            raise TrackValidationError("mcp_tools must be a dictionary or None")
        mcp_tools = coerce_mcp_config(mcp_tools) if mcp_tools is not None else None

        return cls._create_track_from_metadata(
            agent_name, content, path, metadata_dict, mcp_tools
        )

    @staticmethod
    def _parse_paths(v: object) -> list[str] | None:
        """Parse ``paths`` frontmatter (comma-separated string or list) into a
        non-empty list of globs, or None. Mirrors Haijun Code / AgentTracks."""
        if v is None:
            return None
        if isinstance(v, str):
            v = v.split(",")
        elif not isinstance(v, list):
            raise TrackValidationError("paths must be a string or list")
        return [s for p in v if (s := str(p).strip())] or None

    @classmethod
    def _create_track_from_metadata(
        cls,
        agent_name: str,
        content: str,
        path: Path,
        metadata_dict: dict[str, object],
        mcp_tools: dict[str, MCPServer] | None = None,
        resources: TrackResources | None = None,
        is_agenttracks_format: bool = False,
    ) -> "Track":
        """Create a Track object from parsed metadata.

        Args:
            agent_name: The name of the track.
            content: The markdown content (without frontmatter).
            path: Path to the track file.
            metadata_dict: Parsed frontmatter metadata.
            mcp_tools: MCP tools configuration (from .mcp.json or frontmatter).
            resources: Discovered resource directories.
            is_agenttracks_format: Whether this track follows the AgentTracks standard.
        """
        # Extract AgentTracks standard fields (Pydantic validators handle
        # transformation). Handle "allowed-tools" to "allowed_tools" key mapping.
        allowed_tools_value = metadata_dict.get(
            "allowed-tools", metadata_dict.get("allowed_tools")
        )
        disable_model_invocation_value = metadata_dict.get(
            "disable-model-invocation",
            metadata_dict.get("disable_model_invocation"),
        )
        agenttracks_fields = {
            "description": metadata_dict.get("description"),
            "license": metadata_dict.get("license"),
            "compatibility": metadata_dict.get("compatibility"),
            "metadata": metadata_dict.get("metadata"),
            "allowed_tools": allowed_tools_value,
            "disable_model_invocation": disable_model_invocation_value,
        }
        # Remove None values to avoid passing unnecessary kwargs
        agenttracks_fields = {
            k: v for k, v in agenttracks_fields.items() if v is not None
        }

        # Get trigger keywords from metadata
        keywords = metadata_dict.get("triggers", [])
        if not isinstance(keywords, list):
            raise TrackValidationError("Triggers must be a list of strings")

        # Parse path globs ("rules"): a comma-separated string or a YAML list.
        paths = cls._parse_paths(metadata_dict.get("paths"))

        # Infer the trigger type:
        # 1. If paths exist -> PathTrigger (deterministic file-touch injection)
        # 2. If inputs exist -> TaskTrigger
        # 3. If keywords exist -> KeywordTrigger
        # 4. Else (no keywords) -> None (always active)
        if paths:
            # A track is either path-triggered OR model-invocable, not both:
            # `paths:` wins and any `triggers:`/`inputs:` are ignored. Warn so the
            # dropped fields are discoverable instead of silently disappearing.
            ignored = []
            if keywords:
                ignored.append(f"'triggers': {keywords}")
            if "inputs" in metadata_dict:
                ignored.append("'inputs'")
            if ignored:
                logger.warning(
                    "Track '%s' declares 'paths:' together with %s; 'paths:' "
                    "takes precedence (path-triggered rule) and %s will be "
                    "ignored. A track can be either path-triggered OR "
                    "model-invocable, not both.",
                    agent_name,
                    " and ".join(ignored),
                    " and ".join(ignored),
                )
            return Track(
                name=agent_name,
                content=content,
                source=to_posix_path(path),
                trigger=PathTrigger(paths=paths),
                mcp_tools=mcp_tools,
                resources=resources,
                is_agenttracks_format=is_agenttracks_format,
                **agenttracks_fields,
            )
        elif "inputs" in metadata_dict:
            # Add a trigger for the agent name if not already present
            trigger_keyword = f"/{agent_name}"
            if trigger_keyword not in keywords:
                keywords.append(trigger_keyword)
            inputs_raw = metadata_dict.get("inputs", [])
            if not isinstance(inputs_raw, list):
                raise TrackValidationError("inputs must be a list")
            inputs: list[InputMetadata] = [
                InputMetadata.model_validate(i) for i in inputs_raw
            ]
            return Track(
                name=agent_name,
                content=content,
                source=to_posix_path(path),
                trigger=TaskTrigger(triggers=keywords),
                inputs=inputs,
                mcp_tools=mcp_tools,
                resources=resources,
                is_agenttracks_format=is_agenttracks_format,
                **agenttracks_fields,
            )

        elif metadata_dict.get("triggers", None):
            return Track(
                name=agent_name,
                content=content,
                source=to_posix_path(path),
                trigger=KeywordTrigger(keywords=keywords),
                mcp_tools=mcp_tools,
                resources=resources,
                is_agenttracks_format=is_agenttracks_format,
                **agenttracks_fields,
            )
        else:
            # No triggers, default to None (always active)
            return Track(
                name=agent_name,
                content=content,
                source=to_posix_path(path),
                trigger=None,
                mcp_tools=mcp_tools,
                resources=resources,
                is_agenttracks_format=is_agenttracks_format,
                **agenttracks_fields,
            )

    @classmethod
    def _handle_third_party(cls, path: Path, file_content: str) -> Union["Track", None]:
        """Handle third-party track files (e.g., .cursorrules, AGENTS.md).

        Creates a Track with None trigger (always active) if the file type
        is recognized.
        """
        track_name = cls.PATH_TO_THIRD_PARTY_TRACK_NAME.get(path.name.lower())

        if track_name is not None:
            return Track(
                name=track_name,
                content=file_content,
                source=to_posix_path(path),
                trigger=None,
            )

        return None

    @classmethod
    def _handle_nested_third_party(
        cls, path: Path, file_content: str, rel_dir: PurePosixPath
    ) -> Union["Track", None]:
        """Build a ``PathTrigger`` rule scoped to ``rel_dir`` from a nested
        third-party file, so its guidance is injected only when a file under that
        directory is touched. ``rel_dir`` is workspace-relative (the matcher's
        base)."""
        track_name = cls.PATH_TO_THIRD_PARTY_TRACK_NAME.get(path.name.lower())
        if track_name is None:
            return None
        # Encode the directory in the name so multiple nested files (all mapping
        # to e.g. "agents") stay distinct for dedup and activation tracking.
        return Track(
            name=f"{track_name}:{rel_dir.as_posix()}",
            content=file_content,
            source=to_posix_path(path),
            trigger=PathTrigger(paths=[f"{rel_dir.as_posix()}/**"]),
        )

    @model_validator(mode="after")
    def _truncate_long_description(self):
        """Truncate description to MAX_DESCRIPTION_LENGTH via maybe_truncate.

        Uses a model_validator (not field_validator) so the truncation notice
        can reference self.source, telling the agent where to find the full
        track content.
        """
        if (
            self.description is not None
            and len(self.description) > self.MAX_DESCRIPTION_LENGTH
        ):
            logger.warning(
                "Track '%s' description truncated from %d to %d characters",
                self.name,
                len(self.description),
                self.MAX_DESCRIPTION_LENGTH,
            )
            notice = DEFAULT_TRUNCATE_NOTICE
            if self.source:
                notice = self._DESCRIPTION_TRUNCATE_NOTICE.format(source=self.source)
            self.description = maybe_truncate(
                self.description,
                truncate_after=self.MAX_DESCRIPTION_LENGTH,
                truncate_notice=notice,
            )
        return self

    @model_validator(mode="after")
    def _append_missing_variables_prompt(self):
        """Append a prompt to ask for missing variables after model construction."""
        # Only apply to task tracks
        if not isinstance(self.trigger, TaskTrigger):
            return self

        # If no variables and no inputs, nothing to do
        if not self.requires_user_input() and not self.inputs:
            return self

        prompt = (
            "\n\nIf the user didn't provide any of these variables, ask the user to "
            "provide them first before the agent can proceed with the task."
        )

        # Avoid duplicating the prompt if content already includes it
        if self.content and prompt not in self.content:
            self.content += prompt

        return self

    @model_validator(mode="after")
    def _path_rules_are_trigger_only(self):
        """Force ``disable_model_invocation`` for path rules: they inject only on
        file-touch, so every consumer of that flag (catalog, invoke_track,
        tool-attach) keeps them unadvertised and non-invocable."""
        if isinstance(self.trigger, PathTrigger):
            self.disable_model_invocation = True
        return self

    def match_trigger(self, message: str) -> str | None:
        """Match a trigger in the message.

        Returns the first trigger that matches the message, or None if no match.
        Only applies to KeywordTrigger and TaskTrigger types.

        Matching is whole-token and case-insensitive: a keyword only fires when
        it appears bounded by non-alphanumeric characters, so ``git`` does not
        match ``github`` and ``issue`` does not match ``tissue``. See
        :func:`_keyword_matches` for details.
        """
        if isinstance(self.trigger, KeywordTrigger):
            keywords = self.trigger.keywords
        elif isinstance(self.trigger, TaskTrigger):
            keywords = self.trigger.triggers
        else:
            return None

        message_lower = message.lower()
        for keyword in keywords:
            if _keyword_matches(keyword, message_lower):
                return keyword
        return None

    def match_path_trigger(self, file_path: str) -> str | None:
        """Return the first PathTrigger glob matching ``file_path`` (a POSIX,
        typically workspace-relative, path), or None. Inert for non-PathTrigger
        tracks."""
        if isinstance(self.trigger, PathTrigger):
            for pattern in self.trigger.paths:
                if path_matches_glob(file_path, pattern):
                    return pattern
        return None

    def extract_variables(self, content: str) -> list[str]:
        """Extract variables from the content.

        Variables are in the format ${variable_name}.
        """
        pattern = r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}"
        matches = re.findall(pattern, content)
        return matches

    def requires_user_input(self) -> bool:
        """Check if this track requires user input.

        Returns True if the content contains variables in the format ${variable_name}.
        """
        # Check if the content contains any variables
        variables = self.extract_variables(self.content)
        logger.debug(f"This track requires user input: {variables}")
        return len(variables) > 0

    def get_track_type(self) -> Literal["repo", "knowledge", "agenttracks"]:
        """Determine the type of this track.

        Returns:
            "agenttracks" for AgentTracks format, "repo" for always-active tracks,
            "knowledge" for trigger-based tracks.
        """
        if self.is_agenttracks_format:
            return "agenttracks"
        elif self.trigger is None:
            return "repo"
        else:
            return "knowledge"

    def get_triggers(self) -> list[str]:
        """Extract trigger keywords from this track.

        Returns:
            List of trigger strings, or empty list if no triggers.
        """
        if isinstance(self.trigger, KeywordTrigger):
            return self.trigger.keywords
        elif isinstance(self.trigger, TaskTrigger):
            return self.trigger.triggers
        return []

    def to_track_info(self) -> TrackInfo:
        """Convert this track to a TrackInfo.

        Returns:
            TrackInfo containing the track's essential information.
        """
        return TrackInfo(
            name=self.name,
            type=self.get_track_type(),
            content=self.content,
            triggers=self.get_triggers(),
            source=self.source,
            description=self.description,
            is_agenttracks_format=self.is_agenttracks_format,
            disable_model_invocation=self.disable_model_invocation,
        )

    def render_content(
        self,
        working_dir: Path | None = None,
    ) -> str:
        """Render track content, executing inline !`command` blocks.

        Inline !`command` patterns in the content are executed and
        replaced with their stdout output. Code blocks (fenced and
        inline) are preserved. Unclosed fenced blocks are treated as
        extending to EOF. Use \\!`cmd` to produce literal !`cmd` text.

        Args:
            working_dir: Directory to run commands in.

        Returns:
            Processed content with command outputs substituted.
        """
        return render_content_with_commands(self.content, working_dir)


def load_tracks_from_dir(
    track_dir: str | Path,
    strict: bool = True,
    recursive: bool = True,
    root: Path | None = None,
    exclude_dirs: set[Path] | None = None,
) -> tuple[dict[str, Track], dict[str, Track], dict[str, Track]]:
    """Load all tracks from the given directory.

    Supports both formats:
    - Handprint format: tracks/*.md files
    - AgentTracks format: tracks/track-name/TRACK.md directories

    Note, legacy repo instructions will not be loaded here.

    A track that fails to load is logged and skipped; it never aborts the others.

    Args:
        track_dir: Path to the tracks directory (e.g. .handprint/tracks)
        strict: If True, enforce strict AgentTracks name validation.
        recursive: If False, only load regular .md files that are immediate
            children of track_dir.
        root: If given, track paths that resolve outside it (e.g. through a
            symlink) are skipped. Plugins pass their root here.
        exclude_dirs: Directories whose regular .md files are not loaded as
            tracks (e.g. managed installed packages inside a user tracks dir).

    Returns:
        Tuple of (repo_tracks, knowledge_tracks, agent_tracks) dictionaries.
        - repo_tracks: Tracks with trigger=None (permanent context)
        - knowledge_tracks: Tracks with KeywordTrigger or TaskTrigger (progressive)
        - agent_tracks: AgentTracks standard TRACK.md files (separate category)
    """
    if isinstance(track_dir, str):
        track_dir = Path(track_dir)

    repo_tracks: dict[str, Track] = {}
    knowledge_tracks: dict[str, Track] = {}
    agent_tracks: dict[str, Track] = {}
    logger.debug(f"Loading agents from {track_dir}")

    # Discover track files in the tracks directory
    # Note: Third-party files (AGENTS.md, etc.) are loaded separately by
    # load_project_tracks() to ensure they're loaded even when this directory
    # doesn't exist.
    track_md_files = find_track_md_directories(track_dir, root)
    track_md_dirs = {track_md.parent for track_md in track_md_files}
    # Rebase exclusions onto track_dir so they still match when track_dir is
    # reached through a symlink (e.g. ~/.agents/tracks -> ~/.handprint/tracks).
    real_track_dir = track_dir.resolve()
    rebased_exclude_dirs = {
        track_dir / real.relative_to(real_track_dir)
        for d in exclude_dirs or ()
        if (real := d.resolve()).is_relative_to(real_track_dir)
    }
    regular_md_files = find_regular_md_files(
        track_dir, track_md_dirs | rebased_exclude_dirs, recursive, root
    )

    # Load TRACK.md files (auto-detected and validated in Track.load)
    # Wrap each load in try/except to ensure one bad track doesn't break all loading
    for track_md_path in track_md_files:
        try:
            load_and_categorize(
                track_md_path,
                track_dir,
                repo_tracks,
                knowledge_tracks,
                agent_tracks,
                strict=strict,
                root=root,
            )
        except Exception as e:
            logger.warning(f"Failed to load track from {track_md_path}: {e}")

    # Load regular .md files
    for path in regular_md_files:
        try:
            load_and_categorize(
                path,
                track_dir,
                repo_tracks,
                knowledge_tracks,
                agent_tracks,
                strict=strict,
                root=root,
            )
        except Exception as e:
            logger.warning(f"Failed to load track from {path}: {e}")

    total = len(repo_tracks) + len(knowledge_tracks) + len(agent_tracks)
    logger.debug(
        f"Loaded {total} tracks: "
        f"repo={list(repo_tracks.keys())}, "
        f"knowledge={list(knowledge_tracks.keys())}, "
        f"agent={list(agent_tracks.keys())}"
    )
    return repo_tracks, knowledge_tracks, agent_tracks


# Default user tracks directories (in order of priority)
USER_TRACKS_DIRS = [
    Path.home() / ".agents" / "tracks",
    get_user_persistence_dir() / "tracks",
    get_user_persistence_dir() / "microagents",  # Legacy support
]


def load_user_tracks() -> list[Track]:
    """Load tracks from user's home directory.

    Searches for tracks in ~/.agents/tracks/, ~/.handprint/tracks/, and
    ~/.handprint/microagents/ (legacy). Tracks from all directories are merged,
    with earlier entries in USER_TRACKS_DIRS taking precedence for duplicate
    names.

    Also loads enabled installed tracks from ~/.handprint/tracks/installed/
    (managed via install_track/uninstall_track). Installed tracks have lower
    precedence than user tracks from the directories above.

    Returns:
        List of Track objects loaded from user directories.
        Returns empty list if no tracks found or loading fails.
    """
    from handprint.sdk.tracks.installed import get_installed_tracks_dir

    all_tracks: list[Track] = []
    seen_names: set[str] = set()

    _load_and_merge_from_dirs(
        USER_TRACKS_DIRS,
        seen_names,
        all_tracks,
        "user tracks",
        exclude_dirs={get_installed_tracks_dir()},
    )

    # Load enabled installed tracks (lower precedence than user tracks)
    try:
        from handprint.sdk.tracks.installed import load_installed_tracks

        for track in load_installed_tracks():
            if track.name not in seen_names:
                seen_names.add(track.name)
                all_tracks.append(track)
    except Exception as e:
        logger.warning(f"Failed to load installed tracks: {e}")

    logger.debug(
        f"Loaded {len(all_tracks)} user tracks: {[s.name for s in all_tracks]}"
    )
    return all_tracks


def _find_git_repo_root(path: Path) -> Path | None:
    """Find the nearest ancestor directory that looks like a Git repository root.

    We intentionally don't shell out to `git`, so this works even when git isn't
    installed. A directory is considered a git root if it contains a `.git`
    entry (directory *or* file, to support worktrees/submodules).
    """

    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _merge_loaded_tracks(
    *,
    source_dir: Path,
    loaded_tracks: list[dict[str, Track]],
    seen_names: set[str],
    all_tracks: list[Track],
) -> None:
    for tracks_dict in loaded_tracks:
        for name, track in tracks_dict.items():
            if name not in seen_names:
                all_tracks.append(track)
                seen_names.add(name)
            else:
                logger.warning(f"Skipping duplicate track '{name}' from {source_dir}")


def _load_and_merge_from_dirs(
    dirs: list[Path],
    seen_names: set[str],
    all_tracks: list[Track],
    source_label: str,
    exclude_dirs: set[Path] | None = None,
) -> None:
    """Load tracks from multiple directories, merging with deduplication.

    For each directory that exists, loads all tracks via load_tracks_from_dir()
    and merges them into all_tracks, skipping duplicates based on seen_names.
    Earlier directories take precedence for duplicate names.

    Args:
        dirs: List of directories to search for tracks.
        seen_names: Set of already-seen track names (mutated in place).
        all_tracks: Accumulator list of tracks (mutated in place).
        source_label: Human-readable label for log messages (e.g. "user tracks").
        exclude_dirs: Passed through to load_tracks_from_dir().
    """
    for tracks_dir in dirs:
        if not tracks_dir.exists():
            logger.debug(f"{source_label} directory does not exist: {tracks_dir}")
            continue

        try:
            logger.debug(f"Loading {source_label} from {tracks_dir}")
            repo_tracks, knowledge_tracks, agent_tracks = load_tracks_from_dir(
                tracks_dir, exclude_dirs=exclude_dirs
            )
            _merge_loaded_tracks(
                source_dir=tracks_dir,
                loaded_tracks=[repo_tracks, knowledge_tracks, agent_tracks],
                seen_names=seen_names,
                all_tracks=all_tracks,
            )
        except Exception as e:
            logger.warning(f"Failed to load {source_label} from {tracks_dir}: {str(e)}")


def load_project_tracks(work_dir: str | Path) -> list[Track]:
    """Load tracks from project-specific directories.

    Searches for tracks in {work_dir}/.agents/tracks/, {work_dir}/.handprint/tracks/,
    and {work_dir}/.handprint/microagents/ (legacy).

    If the working directory is inside a Git repository, this function also loads
    tracks from the Git repo root, so running from a subdirectory still picks up
    repo-level guidance (e.g., AGENTS.md).

    Tracks are merged in priority order, with the *working directory* taking
    precedence over the Git repo root when duplicates exist.

    Use .agents/tracks for new tracks. .handprint/tracks is the legacy Handprint
    location, and .handprint/microagents is deprecated.

    Example: If "my-track" exists in both .agents/tracks/ and .handprint/tracks/,
    the version from .agents/tracks/ is used.

    Also loads third-party track files (AGENTS.md, .cursorrules, etc.) from the
    working directory and (if different) the git repo root.

    Args:
        work_dir: Path to the project/working directory.

    Returns:
        List of Track objects loaded from project directories.
        Returns empty list if no tracks found or loading fails.
    """
    if isinstance(work_dir, str):
        work_dir = Path(work_dir)

    all_tracks = []
    seen_names: set[str] = set()

    git_root = _find_git_repo_root(work_dir)

    # Working dir takes precedence (more local rules override repo root rules)
    search_roots: list[Path] = [work_dir]
    if git_root is not None and git_root != work_dir:
        search_roots.append(git_root)

    # First, load third-party track files (AGENTS.md, .cursorrules, etc.) from each
    # search root. This ensures they are loaded even if .handprint/tracks doesn't
    # exist.
    for root in search_roots:
        third_party_files = find_third_party_files(
            root, Track.PATH_TO_THIRD_PARTY_TRACK_NAME
        )
        for path in third_party_files:
            try:
                track = Track.load(path)
                if track.name not in seen_names:
                    all_tracks.append(track)
                    seen_names.add(track.name)
                    logger.debug(f"Loaded third-party track: {track.name} from {path}")
            except (TrackError, OSError, yaml.YAMLError) as e:
                logger.warning(f"Failed to load third-party track from {path}: {e}")

    # Load nested third-party files (e.g. server/AGENTS.md) as directory-scoped
    # path rules, keyed off work_dir (the matcher's base).
    for path, rel_dir in find_nested_third_party_files(
        work_dir, Track.PATH_TO_THIRD_PARTY_TRACK_NAME
    ):
        try:
            content = path.read_text(encoding="utf-8")
            rule = Track._handle_nested_third_party(path, content, rel_dir)
            if rule is not None and rule.name not in seen_names:
                all_tracks.append(rule)
                seen_names.add(rule.name)
                logger.debug(f"Loaded nested path rule: {rule.name} from {path}")
        except (TrackError, OSError, UnicodeDecodeError, yaml.YAMLError) as e:
            logger.warning(f"Failed to load nested third-party file {path}: {e}")

    # Load project-specific tracks from .agents/tracks, .handprint/tracks,
    # and legacy microagents (priority order; first wins for duplicates)
    for root in search_roots:
        project_tracks_dirs = [
            root / ".agents" / "tracks",
            root / ".handprint" / "tracks",
            root / ".handprint" / "microagents",  # Legacy support
        ]

        _load_and_merge_from_dirs(
            project_tracks_dirs, seen_names, all_tracks, "project tracks"
        )

    logger.debug(
        f"Loaded {len(all_tracks)} project tracks: {[s.name for s in all_tracks]}"
    )
    return all_tracks


# Public tracks repository configuration
PUBLIC_TRACKS_REPO = "https://github.com/Handprint/extensions"
# Allow overriding the ref via EXTENSIONS_REF environment variable.
# Accepts a branch name, tag (e.g. "v1.0.0"), or full 40-char commit SHA.
PUBLIC_TRACKS_REF = os.environ.get("EXTENSIONS_REF", "main")
DEFAULT_MARKETPLACE_PATH = "marketplaces/default.json"

# Process-level cache for load_public_tracks. Conversation creation re-validates
# AgentContext several times and each validation re-runs load_public_tracks
# (git fetch + parse ~40 md files ≈ 1s). The cache short-circuits repeated calls
# within the TTL while still picking up new tracks within a minute.
#
# Cache value: (timestamp, tracks)
# For mutable refs (branches), timestamp is time.monotonic() at write time and
# the entry expires after _PUBLIC_TRACKS_CACHE_TTL_SECONDS.
# For immutable refs (tags, commit SHAs), timestamp is float("inf") so the
# TTL check is never satisfied and the entry lives for the process lifetime.
_PUBLIC_TRACKS_CACHE: dict[
    tuple[str, str, str | None], tuple[float, list["Track"]]
] = {}
_PUBLIC_TRACKS_CACHE_TTL_SECONDS = 60.0
_PUBLIC_TRACKS_CACHE_LOCK = threading.Lock()


def _invalidate_public_tracks_cache() -> None:
    """Clear the in-memory public-tracks cache.

    Called by ``sync_public_tracks`` so a forced refresh re-parses immediately
    instead of waiting for the TTL.
    """
    with _PUBLIC_TRACKS_CACHE_LOCK:
        _PUBLIC_TRACKS_CACHE.clear()


def load_marketplace_track_names(
    repo_path: Path, marketplace_path: str
) -> set[str] | None:
    """Load the list of track names from a marketplace manifest file.

    Uses the existing Marketplace model from handprint.sdk.plugin to parse
    the marketplace JSON file and extract plugin names.

    Args:
        repo_path: Path to the local repository.
        marketplace_path: Relative path to the marketplace JSON file within the repo.

    Returns:
        Set of track names to load, or None if marketplace file not found or invalid.
    """
    from handprint.sdk.marketplace import Marketplace

    marketplace_file = repo_path / marketplace_path
    if not marketplace_file.exists():
        logger.debug(f"Marketplace file not found: {marketplace_file}")
        return None

    try:
        with open(marketplace_file, encoding="utf-8") as f:
            data = json.load(f)

        # Use Marketplace model for validation and parsing
        marketplace = Marketplace.model_validate(
            {**data, "path": to_posix_path(repo_path)}
        )

        track_names = {plugin.name for plugin in marketplace.plugins}

        logger.debug(
            f"Loaded {len(track_names)} track names from marketplace: "
            f"{marketplace_path}"
        )
        return track_names

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse marketplace JSON {marketplace_file}: {e}")
        return None
    except OSError as e:
        logger.warning(f"Failed to read marketplace file {marketplace_file}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Failed to load marketplace {marketplace_file}: {e}")
        return None


def load_public_tracks(
    repo_url: str = PUBLIC_TRACKS_REPO,
    ref: str = PUBLIC_TRACKS_REF,
    marketplace_path: str | None = DEFAULT_MARKETPLACE_PATH,
) -> list[Track]:
    """Load tracks from the public Handprint tracks repository.

    This function maintains a local git clone of the public tracks registry at
    https://github.com/Handprint/extensions. On first run, it clones the repository
    to ~/.handprint/tracks-cache/. On subsequent runs within the same process, it
    returns cached results. For branch refs it re-fetches after the cache TTL; for
    tags and commit SHAs (immutable refs) the cache never expires so no further
    network calls are made.

    By default, only tracks listed in the default marketplace
    (marketplaces/default.json) are loaded. Pass a different relative
    marketplace_path to load another marketplace, or None to load all public
    tracks without marketplace filtering.

    Note: When a track directory contains a TRACK.md file (AgentTracks format),
    any other markdown files in that directory or its subdirectories are treated
    as reference materials for that track, NOT as separate tracks.

    Args:
        repo_url: URL of the tracks repository. Defaults to the official
            Handprint tracks repository.
        ref: Branch name, tag (e.g. ``"v1.0.0"``), or full 40-character commit
            SHA to load tracks from. Defaults to ``'main'``. Tags and commit
            SHAs are treated as immutable: once loaded, the result is cached
            for the lifetime of the process without further remote polling.
        marketplace_path: Relative path to the marketplace JSON file within the
            repository. Pass None to load all public tracks without filtering.

    Returns:
        List of Track objects loaded from the public repository.
        Returns empty list if loading fails.

    Example:
        >>> from handprint.sdk.context import AgentContext
        >>> from handprint.sdk.tracks import load_public_tracks
        >>>
        >>> # Load public tracks
        >>> public_tracks = load_public_tracks()
        >>>
        >>> # Use with AgentContext
        >>> context = AgentContext(tracks=public_tracks)
    """
    cache_key = (repo_url, ref, marketplace_path)
    with _PUBLIC_TRACKS_CACHE_LOCK:
        cached = _PUBLIC_TRACKS_CACHE.get(cache_key)
        if (
            cached is not None
            and time.monotonic() - cached[0] < _PUBLIC_TRACKS_CACHE_TTL_SECONDS
        ):
            return list(cached[1])

    all_tracks: list[Track] = []
    is_pinned = False

    try:
        # Get or update the local repository
        cache_dir = get_tracks_cache_dir()
        repo_path = update_tracks_repository(repo_url, ref, cache_dir)

        if repo_path is None:
            logger.warning("Failed to access public tracks repository")
            return all_tracks

        # Detect whether the ref is immutable (tag or commit SHA in detached HEAD).
        # Pinned repos are cached indefinitely — no re-fetching needed.
        is_pinned = is_tracks_repo_pinned(repo_path)

        # Load tracks from the local repository
        tracks_dir = repo_path / "tracks"
        if not tracks_dir.exists():
            logger.warning(f"Tracks directory not found in repository: {tracks_dir}")
            return all_tracks

        # Determine which track files to load
        if marketplace_path is None:
            marketplace_track_names = None
        else:
            marketplace_track_names = load_marketplace_track_names(
                repo_path, marketplace_path
            )
            if (
                marketplace_track_names is None
                and marketplace_path != DEFAULT_MARKETPLACE_PATH
            ):
                logger.warning(
                    "Configured marketplace path could not be loaded: %s",
                    marketplace_path,
                )
                return all_tracks

        if marketplace_track_names is not None:
            all_track_files: list[Path] = []
            for track_name in marketplace_track_names:
                track_md = tracks_dir / track_name / "TRACK.md"
                if track_md.exists():
                    all_track_files.append(track_md)
                    continue

                legacy_md = tracks_dir / f"{track_name}.md"
                if legacy_md.exists():
                    all_track_files.append(legacy_md)
                    continue

                logger.debug(
                    "Track '%s' from marketplace '%s' not found in tracks dir",
                    track_name,
                    marketplace_path,
                )
        else:
            track_md_files = find_track_md_directories(tracks_dir)
            track_md_dirs = {track_md.parent for track_md in track_md_files}
            regular_md_files = find_regular_md_files(tracks_dir, track_md_dirs)
            all_track_files = list(track_md_files) + list(regular_md_files)

        logger.info(
            f"Found {len(all_track_files)} track files in public tracks repository"
        )

        # Load each track file
        for track_file in all_track_files:
            try:
                track = Track.load(
                    path=track_file,
                    track_base_dir=repo_path,
                )
                if track is None:
                    continue
                all_tracks.append(track)
                logger.debug(f"Loaded public track: {track.name}")
            except Exception as e:
                logger.warning(f"Failed to load track from {track_file.name}: {str(e)}")
                continue

    except Exception as e:
        logger.warning(f"Failed to load public tracks from {repo_url}: {str(e)}")

    logger.info("Loaded %d public tracks", len(all_tracks))

    # Only cache non-empty results so transient errors don't poison the cache
    # for the full TTL window.
    if all_tracks:
        timestamp = float("inf") if is_pinned else time.monotonic()
        with _PUBLIC_TRACKS_CACHE_LOCK:
            _PUBLIC_TRACKS_CACHE[cache_key] = (timestamp, list(all_tracks))

    return all_tracks


def load_available_tracks(
    work_dir: str | Path | None = None,
    *,
    include_user: bool = False,
    include_project: bool = False,
    include_public: bool = False,
    marketplace_path: str | None = DEFAULT_MARKETPLACE_PATH,
) -> dict[str, Track]:
    """Load and merge tracks from SDK-level sources with consistent precedence.

    Precedence (later overrides earlier via dict updates):
        public (lowest) → user → project (highest)

    This is the single entry-point for building a merged track catalog from
    the three SDK-shipped sources. Server-only sources (sandbox, org) are
    layered on top by the caller.

    Args:
        work_dir: Project/working directory for project tracks. When None,
            project tracks are skipped regardless of *include_project*.
        include_user: Load user-level tracks (~/.agents/tracks, etc.).
        include_project: Load project-level tracks (requires *work_dir*).
        include_public: Load public tracks from the Handprint extensions repo.
        marketplace_path: Relative marketplace JSON path to use for public tracks.
            Pass None to load all public tracks without marketplace filtering.

    Returns:
        Dict mapping track name → Track, with higher-precedence sources
        overriding lower ones.
    """
    available: dict[str, Track] = {}

    if include_public:
        try:
            for s in load_public_tracks(marketplace_path=marketplace_path):
                available[s.name] = s
        except Exception as e:
            logger.warning(f"Failed to load public tracks: {e}")

    if include_user:
        try:
            for s in load_user_tracks():
                available[s.name] = s
        except Exception as e:
            logger.warning(f"Failed to load user tracks: {e}")

    if include_project and work_dir:
        try:
            for s in load_project_tracks(work_dir):
                available[s.name] = s
        except Exception as e:
            logger.warning(f"Failed to load project tracks: {e}")

    return available


def merge_tracks_by_name(
    primary: Iterable[Track], secondary: Iterable[Track]
) -> list[Track]:
    """Merge two track collections by name.

    ``primary`` tracks are authoritative: they take precedence on name conflicts
    and keep their order. Each ``secondary`` track is appended only when its name
    is not already provided by ``primary``.
    """
    merged = list(primary)
    seen = {track.name for track in merged}
    for track in secondary:
        if track.name not in seen:
            seen.add(track.name)
            merged.append(track)
    return merged


def to_prompt(tracks: list[Track], max_description_length: int = 1024) -> str:
    """Generate XML prompt block for available tracks.

    Creates an `<available_tracks>` XML block suitable for inclusion
    in system prompts, following the AgentTracks format from tracks-ref.

    Args:
        tracks: List of tracks to include in the prompt
        max_description_length: Maximum length for descriptions (default 1024)

    Returns:
        XML string in AgentTracks format with name and description. The
        `<location>` field is intentionally omitted so the agent cannot
        bypass the `invoke_track` tool by reading the file directly.

    Example:
        >>> tracks = [Track(name="pdf-tools", content="...",
        ...                 description="Extract text from PDF files.",
        ...                 source="/path/to/track")]
        >>> print(to_prompt(tracks))
        <available_tracks>
          <track>
            <name>pdf-tools</name>
            <description>Extract text from PDF files.</description>
          </track>
        </available_tracks>
    """
    if not tracks:
        return "<available_tracks>\n  no available tracks\n</available_tracks>"

    lines = ["<available_tracks>"]
    for track in tracks:
        # Use description if available, otherwise use first line of content
        description = track.description
        content_truncated = 0
        if not description:
            # Extract first non-empty, non-header line from content as fallback
            # Track position to calculate truncated content after the description
            chars_before_desc = 0
            for line in track.content.split("\n"):
                stripped = line.strip()
                # Skip markdown headers and empty lines
                if not stripped or stripped.startswith("#"):
                    chars_before_desc += len(line) + 1  # +1 for newline
                    continue
                description = stripped
                # Calculate remaining content after this line as truncated
                desc_end_pos = chars_before_desc + len(line)
                content_truncated = max(0, len(track.content) - desc_end_pos)
                break
        description = description or ""

        # Calculate total truncated characters
        total_truncated = content_truncated

        # Truncate description if needed and add truncation indicator
        if len(description) > max_description_length:
            total_truncated += len(description) - max_description_length
            description = description[:max_description_length]

        if total_truncated > 0:
            truncation_msg = (
                f"... [{total_truncated} characters truncated. "
                f'Call invoke_track(name="{track.name}") to load the full track]'
            )
            description = description + truncation_msg

        # Escape XML special characters using standard library
        description = xml_escape(description.strip())
        name = xml_escape(track.name.strip())

        # Build track element. Note: <location> is intentionally omitted so
        # the agent cannot bypass `invoke_track` by reading the file directly;
        # `invoke_track` is the only supported invocation path.
        lines.append("  <track>")
        lines.append(f"    <name>{name}</name>")
        lines.append(f"    <description>{description}</description>")
        lines.append("  </track>")

    lines.append("</available_tracks>")
    return "\n".join(lines)
