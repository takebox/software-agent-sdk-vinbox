"""Concrete :class:`~handprint.sdk.context.prompts.section.PromptSection` units.

Sections are pure, synchronous functions of a :class:`PromptContext` -- no Jinja
environment, no filesystem loader, no ``render_template`` bootstrap -- so each one
unit-tests in isolation. The static tier (ported from ``system_prompt.j2``) lives
in :mod:`.static`; the standalone planning composition (ported from
``system_prompt_planning.j2``) in :mod:`.planning`.
"""

from handprint.sdk.context.prompts.sections.dynamic import (
    AvailableTracksSection,
    CustomSecretsSection,
    CustomSuffixSection,
    DateTimeSection,
    MemoryContextSection,
    RepoContextSection,
)
from handprint.sdk.context.prompts.sections.planning import PlanningSection
from handprint.sdk.context.prompts.sections.static import (
    CodeQualitySection,
    EfficiencySection,
    EnvironmentSetupSection,
    ExternalServicesSection,
    FileSystemSection,
    MemorySection,
    ModelSpecificSection,
    PersonaSection,
    ProblemSolvingSection,
    ProcessManagementSection,
    PullRequestsSection,
    RoleSection,
    SecurityRiskAssessmentSection,
    SecuritySection,
    SelfDocumentationSection,
    SoulSection,
    ToolGuidanceSection,
    TroubleshootingSection,
    VersionControlSection,
)


__all__ = [
    "AvailableTracksSection",
    "CodeQualitySection",
    "CustomSecretsSection",
    "CustomSuffixSection",
    "DateTimeSection",
    "EfficiencySection",
    "EnvironmentSetupSection",
    "ExternalServicesSection",
    "FileSystemSection",
    "MemoryContextSection",
    "MemorySection",
    "ModelSpecificSection",
    "PersonaSection",
    "PlanningSection",
    "ProblemSolvingSection",
    "ProcessManagementSection",
    "PullRequestsSection",
    "RepoContextSection",
    "RoleSection",
    "SecurityRiskAssessmentSection",
    "SecuritySection",
    "SelfDocumentationSection",
    "SoulSection",
    "ToolGuidanceSection",
    "TroubleshootingSection",
    "VersionControlSection",
]
