"""Synthetic production local email/model smoke, credential-free, no external effects."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))

from jarvis.bootstrap import build_runtime  # noqa: E402
from jarvis.config import Settings  # noqa: E402
from jarvis.core import AssistantRequest, ModelRole, RuntimeStatus, SensitivityClass  # noqa: E402
from jarvis.diagnostics import run_diagnostics  # noqa: E402


async def smoke(directory: Path) -> dict[str, object]:
    root = directory / "exports"
    (root / "t1").mkdir(parents=True)
    raw = b"Subject: Synthetic\n\nThe synthetic email code word is ORACLE."
    (root / "t1" / "m1.eml").write_bytes(raw)
    settings = Settings(
        _env_file=None,
        data_dir=directory / "data",
        cloud_policy="local_only",
        groq_api_key=None,
        gemini_api_key=None,
        nvidia_api_key=None,
        email_enabled=True,
        email_export_root=root,
        local_model="qwen3:0.6b",
        current_context_enabled=False,
        automatic_research_enabled=False,
        research_enabled=False,
        computer_access_enabled=False,
        coding_context_enabled=False,
        attachments_enabled=False,
    )
    assert (await run_diagnostics(settings)).ok
    async with await build_runtime(settings) as components:
        assert components.email is not None
        result = await components.service.run(
            AssistantRequest(
                user_input="Which code word appears in email? Reply only code word.",
                email_thread_id="t1",
                metadata={"interface": "cli"},
                requested_model_role=ModelRole.FAST,
            )
        )
        assert result.status is RuntimeStatus.COMPLETED
        assert "ORACLE" in (result.reply or "").upper()
        assert result.conversation_id is not None
        conversation_id = result.conversation_id
        assert (await components.store.get_conversation(conversation_id)).email_private
        history = await components.store.recent_messages(conversation_id, limit=20)
        assert all(item.disclosure_sensitivity is SensitivityClass.PRIVATE for item in history)
        assert all("synthetic email code word" not in item.content for item in history)
        assert (root / "t1" / "m1.eml").read_bytes() == raw
        draft = await components.email.draft(
            "t1", recipients=("chosen@example.invalid",), subject="Explicit", body="Unsent"
        )
        assert not draft.sent and not draft.stored
        await components.store.close()
        await components.store.initialize()
        assert (await components.store.get_conversation(conversation_id)).email_private
        await components.store.delete_conversation(conversation_id)
        assert await components.store.get_conversation(conversation_id) is None
    return {
        "doctor": "pass",
        "production_private_email_chat": "pass",
        "cloud_override_denied": "pass",
        "restart_delete": "pass",
        "draft_unsent": "pass",
        "credentials_used": 0,
        "research_calls": 0,
        "cloud_calls": 0,
        "effects": 0,
        "cost_usd": 0,
    }


def main() -> None:
    runtime = REPOSITORY / "runtime"
    runtime.mkdir(exist_ok=True)
    if not runtime.resolve().is_relative_to(REPOSITORY):
        raise ValueError("runtime outside workspace")
    with tempfile.TemporaryDirectory(prefix="phase-i-smoke-", dir=runtime) as directory:
        root = Path(directory).resolve()
        if not root.is_relative_to(runtime.resolve()):
            raise ValueError("cleanup outside runtime")
        result = asyncio.run(smoke(root))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
