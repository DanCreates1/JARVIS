from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from jarvis.core.models import Message, MessageRole
from jarvis.memory.sqlite_store import SQLiteConversationStore


async def test_persists_conversation_and_bounded_recent_messages(tmp_path: Path) -> None:
    database_path = tmp_path / "state" / "jarvis.db"
    store = SQLiteConversationStore(database_path, max_recent_messages=3)
    await store.initialize()
    await store.initialize()

    conversation = await store.create_conversation(metadata={"topic": "test", "private": True})
    first = await store.append_message(
        Message(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content="first",
        )
    )
    second = await store.append_message(
        Message(
            id="fixed-message-id",
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content="second",
        )
    )
    await store.append_message(
        Message(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content="third",
        )
    )

    assert first.id is not None
    assert second.id == "fixed-message-id"
    recent = await store.recent_messages(conversation.id, limit=2)
    assert [message.content for message in recent] == [
        "second",
        "third",
    ]
    assert await store.get_conversation(conversation.id) == conversation
    assert await store.get_conversation("missing") is None

    with pytest.raises(ValueError, match="between 1 and 3"):
        await store.recent_messages(conversation.id, limit=0)
    with pytest.raises(ValueError, match="between 1 and 3"):
        await store.recent_messages(conversation.id, limit=4)

    await store.close()
    await store.close()

    async with SQLiteConversationStore(database_path) as reopened:
        messages = await reopened.recent_messages(conversation.id, limit=10)
        assert [message.content for message in messages] == ["first", "second", "third"]
        assert await reopened.get_conversation(conversation.id) == conversation

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        migrations = connection.execute(
            "SELECT version, name, applied_at FROM schema_migrations"
        ).fetchall()
        conversation_times = connection.execute(
            "SELECT created_at, updated_at FROM conversations WHERE id = ?",
            (conversation.id,),
        ).fetchone()

    assert migrations[0][:2] == (1, "001_initial.sql")
    assert re.fullmatch(r".*\+00:00", migrations[0][2])
    assert conversation_times is not None
    assert all(re.fullmatch(r".*\+00:00", timestamp) for timestamp in conversation_times)


async def test_unknown_conversation_rolls_back_and_store_remains_usable(tmp_path: Path) -> None:
    async with SQLiteConversationStore(tmp_path / "jarvis.db") as store:
        with pytest.raises(KeyError, match="conversation does not exist"):
            await store.append_message(
                Message(
                    conversation_id="missing",
                    role=MessageRole.USER,
                    content="orphan",
                )
            )

        conversation = await store.create_conversation()
        assert await store.recent_messages(conversation.id, limit=1) == []
        stored = await store.append_message(
            Message(
                conversation_id=conversation.id,
                role=MessageRole.USER,
                content="works after rollback",
            )
        )
        assert (await store.recent_messages(conversation.id, limit=1))[0] == stored


def test_rejects_invalid_operational_bounds(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="busy_timeout_ms"):
        SQLiteConversationStore(tmp_path / "jarvis.db", busy_timeout_ms=-1)
    with pytest.raises(ValueError, match="max_recent_messages"):
        SQLiteConversationStore(tmp_path / "jarvis.db", max_recent_messages=0)
