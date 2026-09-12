"""Proposal-only and restricted autonomous maintenance policy boundary."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from jarvis.core.models import CoreModel, Identifier

Revision = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
EvidenceDigest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
MaintenanceBranch = Annotated[
    str,
    StringConstraints(pattern=r"^jarvis-maintenance/[a-z0-9][a-z0-9._-]*$", max_length=200),
]


class MaintenanceMode(StrEnum):
    SUGGESTION = "suggestion"
    RESTRICTED_AUTONOMOUS = "restricted_autonomous"


class MaintenanceCategory(StrEnum):
    DOCUMENTATION = "documentation"
    TESTS = "tests"
    FORMATTING = "formatting"
    STATIC_ANALYSIS = "static_analysis"


class MaintenanceEvidenceKind(StrEnum):
    SANITIZED_LOG_SIGNAL = "sanitized_log_signal"
    USER_FEEDBACK = "user_feedback"


class MaintenanceCheck(StrEnum):
    FORMAT = "format"
    LINT = "lint"
    TYPE = "type"
    UNIT = "unit"
    SECURITY = "security"
    REGRESSION = "regression"
    DEPENDENCY_AUDIT = "dependency_audit"
    SECRET_SCAN = "secret_scan"


class MaintenanceAssessmentCode(StrEnum):
    PROPOSAL_ONLY = "proposal_only"
    ELIGIBLE_FOR_ISOLATED_WORK = "eligible_for_isolated_work"
    CATEGORY_NOT_PREAPPROVED = "category_not_preapproved"
    PROTECTED_PATH = "protected_path"
    CATEGORY_PATH_MISMATCH = "category_path_mismatch"


REQUIRED_MAINTENANCE_CHECKS = frozenset(MaintenanceCheck)
PROTECTED_PATHS = (
    ".codex",
    ".github/workflows",
    "AGENTS.md",
    "docs/CODEX_PHASE_PLAYBOOK.md",
    "docs/SECURITY_MODEL.md",
    "docs/security.md",
    "pyproject.toml",
    "scripts/quality.ps1",
    "scripts/setup.ps1",
    "scripts/setup-voice.ps1",
    "tests/security",
    "uv.lock",
    "src/jarvis/broker",
    "src/jarvis/computer/identity.py",
    "src/jarvis/config.py",
    "src/jarvis/core",
    "src/jarvis/permissions",
    "src/jarvis/remote",
    "src/jarvis/security",
)


class MaintenanceEvidence(CoreModel):
    evidence_id: Identifier
    kind: MaintenanceEvidenceKind
    digest: EvidenceDigest
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _normalize_time(value)


class MaintenancePolicy(CoreModel):
    mode: MaintenanceMode = MaintenanceMode.SUGGESTION
    preapproved_categories: Annotated[tuple[MaintenanceCategory, ...], Field(max_length=4)] = ()
    production_requires_user_approval: Literal[True] = True
    safety_rule_changes_allowed: Literal[False] = False
    permission_changes_allowed: Literal[False] = False
    identity_changes_allowed: Literal[False] = False
    software_install_allowed: Literal[False] = False
    spending_allowed: Literal[False] = False
    external_contact_allowed: Literal[False] = False

    @field_validator("preapproved_categories")
    @classmethod
    def unique_categories(
        cls, value: tuple[MaintenanceCategory, ...]
    ) -> tuple[MaintenanceCategory, ...]:
        if len(value) != len(set(value)):
            raise ValueError("maintenance categories must be unique")
        return tuple(sorted(value, key=str))

    @model_validator(mode="after")
    def require_restricted_allowlist(self) -> Self:
        if self.mode is MaintenanceMode.RESTRICTED_AUTONOMOUS and not self.preapproved_categories:
            raise ValueError("restricted autonomous maintenance requires an explicit allowlist")
        return self


class MaintenanceProposal(CoreModel):
    proposal_id: Identifier
    category: MaintenanceCategory
    title: Annotated[str, Field(min_length=1, max_length=200)]
    evidence: Annotated[tuple[MaintenanceEvidence, ...], Field(min_length=1, max_length=50)]
    base_revision: Revision
    isolated_branch: MaintenanceBranch
    sandbox_id: Identifier
    created_at: datetime
    changed_paths: Annotated[tuple[str, ...], Field(min_length=1, max_length=200)]
    required_checks: Annotated[tuple[MaintenanceCheck, ...], Field(min_length=8, max_length=8)] = (
        tuple(MaintenanceCheck)
    )
    production_authorized: Literal[False] = False
    installs_software: Literal[False] = False
    spends_money: Literal[False] = False
    contacts_people: Literal[False] = False

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("maintenance title cannot be blank")
        return normalized

    @field_validator("created_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _normalize_time(value)

    @field_validator("changed_paths")
    @classmethod
    def normalize_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for item in value:
            path = item.strip().replace("\\", "/")
            pure = PurePosixPath(path)
            if (
                not path
                or pure.is_absolute()
                or ":" in path
                or ".." in pure.parts
                or ".git" in pure.parts
            ):
                raise ValueError("maintenance paths must be relative repository paths")
            normalized.append(str(pure))
        if len(normalized) != len(set(normalized)):
            raise ValueError("maintenance paths must be unique")
        return tuple(sorted(normalized))

    @field_validator("required_checks")
    @classmethod
    def require_complete_checks(
        cls, value: tuple[MaintenanceCheck, ...]
    ) -> tuple[MaintenanceCheck, ...]:
        if set(value) != REQUIRED_MAINTENANCE_CHECKS:
            raise ValueError("maintenance requires every security and regression check")
        return tuple(sorted(value, key=str))

    @model_validator(mode="after")
    def validate_evidence_times(self) -> Self:
        if any(item.observed_at > self.created_at for item in self.evidence):
            raise ValueError("maintenance evidence cannot postdate its proposal")
        return self


class MaintenanceAssessment(CoreModel):
    proposal_id: Identifier
    code: MaintenanceAssessmentCode
    eligible_for_isolated_implementation: bool
    production_requires_user_approval: Literal[True] = True
    production_authorized: Literal[False] = False


class MaintenanceCheckReceipt(CoreModel):
    check: MaintenanceCheck
    passed: Literal[True] = True
    receipt_digest: EvidenceDigest


class MaintenanceCandidate(CoreModel):
    proposal_id: Identifier
    base_revision: Revision
    candidate_revision: Revision
    isolated_branch: MaintenanceBranch
    check_receipts: Annotated[
        tuple[MaintenanceCheckReceipt, ...], Field(min_length=8, max_length=8)
    ]
    audit_event_ids: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=100)]
    rollback_revision: Revision
    verified_at: datetime
    ready_for_user_review: Literal[True] = True
    production_authorized: Literal[False] = False

    @field_validator("verified_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _normalize_time(value)

    @model_validator(mode="after")
    def validate_candidate(self) -> Self:
        checks = [receipt.check for receipt in self.check_receipts]
        if set(checks) != REQUIRED_MAINTENANCE_CHECKS or len(checks) != len(set(checks)):
            raise ValueError("maintenance candidate requires one receipt for every check")
        if self.candidate_revision == self.base_revision:
            raise ValueError("maintenance candidate must create a new revision")
        if self.rollback_revision != self.base_revision:
            raise ValueError("maintenance rollback must target the reviewed base revision")
        if len(self.audit_event_ids) != len(set(self.audit_event_ids)):
            raise ValueError("maintenance audit event IDs must be unique")
        return self


def assess_maintenance(
    policy: MaintenancePolicy, proposal: MaintenanceProposal
) -> MaintenanceAssessment:
    protected = any(_is_protected(path) for path in proposal.changed_paths)
    if protected:
        code = MaintenanceAssessmentCode.PROTECTED_PATH
        eligible = False
    elif not all(
        _path_matches_category(path, proposal.category) for path in proposal.changed_paths
    ):
        code = MaintenanceAssessmentCode.CATEGORY_PATH_MISMATCH
        eligible = False
    elif policy.mode is MaintenanceMode.SUGGESTION:
        code = MaintenanceAssessmentCode.PROPOSAL_ONLY
        eligible = False
    elif proposal.category not in policy.preapproved_categories:
        code = MaintenanceAssessmentCode.CATEGORY_NOT_PREAPPROVED
        eligible = False
    else:
        code = MaintenanceAssessmentCode.ELIGIBLE_FOR_ISOLATED_WORK
        eligible = True
    return MaintenanceAssessment(
        proposal_id=proposal.proposal_id,
        code=code,
        eligible_for_isolated_implementation=eligible,
    )


def _is_protected(path: str) -> bool:
    lowered = path.casefold()
    return any(
        lowered == protected.casefold()
        or lowered.startswith(protected.casefold().rstrip("/") + "/")
        for protected in PROTECTED_PATHS
    )


def _path_matches_category(path: str, category: MaintenanceCategory) -> bool:
    if category is MaintenanceCategory.DOCUMENTATION:
        return path == "README.md" or (path.startswith("docs/") and path.endswith(".md"))
    if category is MaintenanceCategory.TESTS:
        return path.startswith("tests/") and path.endswith(".py")
    return path.endswith(".py") and path.startswith(("src/", "tests/", "scripts/"))


def _normalize_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("maintenance timestamps must include a timezone")
    return value.astimezone(UTC)
