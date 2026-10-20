from __future__ import annotations

import sqlite3

import pytest

from jarvis.remote.chat_store import PWAChatError, SQLitePWAChatStore
from tests.unit.test_pwa_chat import _context, _harness, _submit, _terminal


@pytest.mark.asyncio
async def test_library_metadata_pagination_concurrency_and_exact_ownership(tmp_path):
    async with _harness(tmp_path) as h:
        first = await _submit(h)
        await h.provider.started.wait()
        h.provider.release.set()
        await _terminal(h)
        cid = first["conversation_id"]
        page = await h.chat.store.conversations(_context())
        assert page["conversations"][0]["title"]
        other = SQLitePWAChatStore(h.store.database_path)
        await other.initialize()
        try:
            edit = dict(
                context=_context(),
                conversation_id=cid,
                revision=0,
                title="  renamed\n <script>  ",
                pinned=True,
                archived=True,
            )
            await other.update_metadata(**edit)
            with pytest.raises(PWAChatError, match="metadata_conflict"):
                await h.chat.store.update_metadata(**edit)
            with pytest.raises(PWAChatError, match="library_changed"):
                await h.chat.store.conversations(_context(), revision=page["revision"])
            assert not (await h.chat.store.conversations(_context()))["conversations"]
            saved = (await h.chat.store.conversations(_context(), archived=True))["conversations"][
                0
            ]
            assert saved["title"] == "renamed <script>" and saved["revision"] == 1
            for foreign in (
                _context(device="foreign"),
                _context().model_copy(update={"host_id": "foreign"}),
            ):
                assert not (await other.conversations(foreign, archived=True))["conversations"]
                with pytest.raises(PWAChatError, match="conversation_not_found"):
                    await other.update_metadata(**{**edit, "context": foreign})
            with sqlite3.connect(h.store.database_path) as db:
                db.execute("UPDATE conversations SET email_private=1 WHERE id=?", (cid,))
            assert not (await other.conversations(_context(), archived=True))["conversations"]
        finally:
            await other.close()
        # Synthetic reservations only: no provider, real history or credentials.
        for index in range(25):
            fresh, result = await h.chat.store.reserve(
                context=_context(),
                request_id=f"page:{index}",
                fingerprint=str(index),
                conversation_id=None,
            )
            assert fresh
            await h.chat.store.complete(
                context=_context(),
                request_id=f"page:{index}",
                result={**result, "status": "cancelled"},
            )
        page = await h.chat.store.conversations(_context())
        next_page = await h.chat.store.conversations(
            _context(), offset=20, revision=page["revision"]
        )
        assert len(page["conversations"]) == 20 and page["has_more"]
        assert len(next_page["conversations"]) == 5 and not next_page["has_more"]
        assert len({row["id"] for row in page["conversations"] + next_page["conversations"]}) == 25
