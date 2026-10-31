"""Exact local previews enriched from the hash-bound private host policy."""

from __future__ import annotations

from jarvis.permissions import ApprovalRequest, canonical_json, render_approval_summary
from jarvis.permissions.trusted_cli import terminal_literal

from .config import ComputerAccessPolicy


def render_local_action_preview(request: ApprovalRequest, policy: ComputerAccessPolicy) -> str:
    """Show exact targets without copying private executable argv into durable authority."""
    action = request.action
    if action.policy_version != policy.authority_version:
        raise ValueError("approval preview requires the exact current host policy")
    details: dict[str, object] = {}
    if action.action_id == "launch_application":
        identifier = action.normalized_arguments.get("application_id")
        if not isinstance(identifier, str) or identifier not in policy.applications:
            raise ValueError("approval application is not enrolled")
        application = policy.applications[identifier]
        details = {
            "executable": str(application.executable),
            "fixed_argv": list(application.arguments),
            "sha256": application.sha256,
        }
    elif action.action_id == "move_controlled_file":
        identity = action.precondition.get("source_identity")
        if not isinstance(identity, dict):
            raise ValueError("approval file identity is unavailable")
        details = {
            "controlled_root": str(policy.controlled_root),
            "file_bytes": identity.get("size"),
            "sha256": identity.get("sha256"),
        }
    summary = render_approval_summary(request)
    return summary + "\nExact targets: " + terminal_literal(canonical_json(details))
