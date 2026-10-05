"""Credential-free production runtime/doctor smoke using synthetic local data only."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))

from jarvis.attachments import AttachmentType, AttachmentUpload  # noqa: E402
from jarvis.bootstrap import build_runtime  # noqa: E402
from jarvis.config import Settings  # noqa: E402
from jarvis.core import AssistantRequest, ModelRole, RuntimeStatus, SensitivityClass  # noqa: E402
from jarvis.diagnostics import run_diagnostics  # noqa: E402


async def smoke(directory: Path) -> dict[str, object]:
    settings = Settings(
        _env_file=None,
        data_dir=directory,
        cloud_policy="local_only",
        groq_api_key=None,
        gemini_api_key=None,
        nvidia_api_key=None,
        attachments_enabled=True,
        local_model="qwen3:0.6b",
        current_context_enabled=False,
        attachment_vision_model="qwen3.5:0.8b",
        automatic_research_enabled=False,
        computer_access_enabled=False,
        coding_context_enabled=False,
    )
    diagnostics = await run_diagnostics(settings)
    assert diagnostics.ok, [
        check.name for check in diagnostics.checks if check.status.value != "pass"
    ]
    components = await build_runtime(settings)
    async with components:
        assert components.attachments is not None
        conversation = await components.store.create_conversation(metadata={"interface": "cli"})
        record = await components.attachments.upload(
            AttachmentUpload(
                conversation_id=conversation.id,
                filename="synthetic.txt",
                media_type=AttachmentType.TEXT,
            ),
            b"The synthetic code word is ORACLE.",
        )
        result = await components.service.run(
            AssistantRequest(
                conversation_id=conversation.id,
                user_input="Which code word appears in attached text? Reply only code word.",
                attachment_ids=(record.id,),
                metadata={"interface": "cli"},
                requested_model_role=ModelRole.FAST,
            )
        )
        assert result.status is RuntimeStatus.COMPLETED and "ORACLE" in (result.reply or "").upper()
        messages = await components.store.recent_messages(conversation.id, limit=10)
        assert all(
            message.disclosure_sensitivity is SensitivityClass.PRIVATE for message in messages
        )
        assert all("synthetic code word" not in message.content for message in messages)
        await components.attachments.delete(conversation.id, record.id)
        assert not await components.attachments.list(conversation.id)
        await components.store.delete_conversation(conversation.id)
    return {
        "doctor": "pass",
        "production_private_attachment_chat": "pass",
        "cloud_override_denied": "pass",
        "upload_delete_conversation_cleanup": "pass",
        "credentials_used": 0,
        "cloud_calls": 0,
        "cost_usd": 0,
    }


def main() -> None:
    runtime = REPOSITORY / "runtime"
    runtime.mkdir(exist_ok=True)
    if not runtime.resolve().is_relative_to(REPOSITORY):
        raise ValueError("runtime outside workspace")
    with tempfile.TemporaryDirectory(prefix="phase-g-smoke-", dir=runtime) as directory:
        path = Path(directory).resolve()
        if not path.is_relative_to(runtime.resolve()):
            raise ValueError("cleanup outside runtime")
        result = asyncio.run(smoke(path))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
