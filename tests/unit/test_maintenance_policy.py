from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from jarvis.maintenance import (
    MaintenanceAssessmentCode,
    MaintenanceCandidate,
    MaintenanceCategory,
    MaintenanceCheck,
    MaintenanceCheckReceipt,
    MaintenanceEvidence,
    MaintenanceEvidenceKind,
    MaintenanceMode,
    MaintenancePolicy,
    MaintenanceProposal,
    assess_maintenance,
)

BASE = "1" * 40
CANDIDATE = "2" * 40
DIGEST = "a" * 64
NOW = datetime(2026, 9, 12, 8, 0, tzinfo=UTC)


def proposal(
    category: MaintenanceCategory = MaintenanceCategory.DOCUMENTATION,
    path: str = "docs/example.md",
) -> MaintenanceProposal:
    return MaintenanceProposal(
        proposal_id="maintenance:1",
        category=category,
        title="Clarify operator documentation",
        evidence=(
            MaintenanceEvidence(
                evidence_id="evidence:1",
                kind=MaintenanceEvidenceKind.USER_FEEDBACK,
                digest=DIGEST,
                observed_at=NOW,
            ),
        ),
        base_revision=BASE,
        isolated_branch="jarvis-maintenance/maintenance-1",
        sandbox_id="sandbox:1",
        created_at=NOW,
        changed_paths=(path,),
    )


def test_suggestion_mode_never_implements_or_authorizes_production() -> None:
    result = assess_maintenance(MaintenancePolicy(), proposal())
    assert result.code is MaintenanceAssessmentCode.PROPOSAL_ONLY
    assert result.eligible_for_isolated_implementation is False
    assert result.production_requires_user_approval is True
    assert result.production_authorized is False


def test_restricted_mode_allows_only_preapproved_low_risk_isolated_work() -> None:
    policy = MaintenancePolicy(
        mode=MaintenanceMode.RESTRICTED_AUTONOMOUS,
        preapproved_categories=(MaintenanceCategory.DOCUMENTATION,),
    )
    allowed = assess_maintenance(policy, proposal())
    denied = assess_maintenance(
        policy,
        proposal(MaintenanceCategory.TESTS, "tests/unit/test_example.py"),
    )
    assert allowed.code is MaintenanceAssessmentCode.ELIGIBLE_FOR_ISOLATED_WORK
    assert allowed.eligible_for_isolated_implementation is True
    assert allowed.production_authorized is False
    assert denied.code is MaintenanceAssessmentCode.CATEGORY_NOT_PREAPPROVED


@pytest.mark.parametrize(
    "path",
    (
        "AGENTS.md",
        "docs/security.md",
        "docs/SECURITY_MODEL.md",
        "tests/security/test_phase3_adversarial.py",
        "src/jarvis/permissions/policy.py",
        "src/jarvis/remote/identity.py",
        "pyproject.toml",
        "uv.lock",
    ),
)
def test_safety_identity_permissions_and_install_surfaces_are_protected(path: str) -> None:
    policy = MaintenancePolicy(
        mode=MaintenanceMode.RESTRICTED_AUTONOMOUS,
        preapproved_categories=tuple(MaintenanceCategory),
    )
    result = assess_maintenance(policy, proposal(MaintenanceCategory.FORMATTING, path))
    assert result.code is MaintenanceAssessmentCode.PROTECTED_PATH
    assert result.eligible_for_isolated_implementation is False


def test_category_path_mismatch_and_path_escape_fail_closed() -> None:
    policy = MaintenancePolicy(
        mode=MaintenanceMode.RESTRICTED_AUTONOMOUS,
        preapproved_categories=(MaintenanceCategory.DOCUMENTATION,),
    )
    mismatch = assess_maintenance(
        policy, proposal(MaintenanceCategory.DOCUMENTATION, "src/jarvis/example.py")
    )
    assert mismatch.code is MaintenanceAssessmentCode.CATEGORY_PATH_MISMATCH
    with pytest.raises(ValidationError, match="relative repository paths"):
        proposal(path="../outside.md")


def test_forbidden_autonomous_effects_are_structurally_false() -> None:
    with pytest.raises(ValidationError):
        MaintenancePolicy(spending_allowed=True)
    with pytest.raises(ValidationError):
        MaintenanceProposal.model_validate(
            {**proposal().model_dump(mode="python"), "contacts_people": True}
        )


def test_candidate_requires_full_checks_audit_history_and_exact_rollback() -> None:
    receipts = tuple(
        MaintenanceCheckReceipt(check=check, receipt_digest=DIGEST) for check in MaintenanceCheck
    )
    candidate = MaintenanceCandidate(
        proposal_id="maintenance:1",
        base_revision=BASE,
        candidate_revision=CANDIDATE,
        isolated_branch="jarvis-maintenance/maintenance-1",
        check_receipts=receipts,
        audit_event_ids=("audit:proposed", "audit:verified"),
        rollback_revision=BASE,
        verified_at=NOW,
    )
    assert candidate.ready_for_user_review is True
    assert candidate.production_authorized is False
    with pytest.raises(ValidationError, match="every check"):
        MaintenanceCandidate.model_validate(
            {
                **candidate.model_dump(mode="python"),
                "check_receipts": (*receipts[:-1], receipts[0]),
            }
        )
    with pytest.raises(ValidationError, match="rollback"):
        MaintenanceCandidate.model_validate(
            {**candidate.model_dump(mode="python"), "rollback_revision": CANDIDATE}
        )
