"""Trusted-local memory review. Mounted behind peer/origin/body admission in web.py."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from jarvis.memory.models import MemoryCategory, MemoryItem, MemoryQuery, MemoryState
from jarvis.memory.sqlite_memory import MemoryNotFoundError, MemoryStateError, SQLiteMemoryStore

if TYPE_CHECKING:
    from jarvis.bootstrap import RuntimeComponents

_ASSETS = Path(__file__).resolve().parents[1] / "pwa"


class VersionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


class InspectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=200)


class RetentionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: MemoryCategory
    days: int = Field(ge=1, le=36_500)


def _summary(item: MemoryItem) -> dict[str, object]:
    return {
        "id": item.id,
        "state": item.state.value,
        "category": item.category.value,
        "content": item.content[:600],
        "truncated": len(item.content) > 600,
        "version": item.version,
        "expires_at": item.expires_at.isoformat() if item.expires_at else None,
        "conflict_count": len(item.conflict_ids),
    }


def install_memory_workspace(
    app: FastAPI, *, runtime: Callable[[Request], RuntimeComponents]
) -> None:
    def store(request: Request) -> tuple[SQLiteMemoryStore, str]:
        components = runtime(request)
        if components.memory_store is None or components.memory_host_id is None:
            raise HTTPException(503, "Memory unavailable")
        return components.memory_store, components.memory_host_id

    @app.get("/memory", include_in_schema=False)
    async def page() -> FileResponse:
        return FileResponse(_ASSETS / "memory.html", media_type="text/html")

    @app.get("/memory/app.js", include_in_schema=False)
    async def script() -> FileResponse:
        return FileResponse(_ASSETS / "memory.js", media_type="text/javascript")

    @app.get("/api/memory/workspace/items")
    async def items(
        request: Request,
        state: MemoryState | None = None,
        category: MemoryCategory | None = None,
        offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
    ) -> dict[str, object]:
        memory, host = store(request)
        rows = await memory.list(
            host_id=host,
            states=(state,) if state else (),
            categories=(category,) if category else (),
            limit=21,
            offset=offset,
        )
        return {"items": [_summary(item) for item in rows[:20]], "has_more": len(rows) > 20}

    @app.get("/api/memory/workspace/items/{memory_id}")
    async def detail(request: Request, memory_id: str) -> dict[str, object]:
        memory, host = store(request)
        item = await memory.get(host_id=host, memory_id=memory_id)
        if item is None:
            raise HTTPException(404, "Memory unavailable")
        return item.model_dump(mode="json")

    @app.post("/api/memory/workspace/inspect")
    async def inspect(request: Request, payload: InspectInput) -> dict[str, object]:
        memory, host = store(request)
        query = MemoryQuery(host_id=host, text=payload.query, limit=8)
        hits = await memory.search(query)
        projection = await memory.project_for_prompt(query, max_items=8, max_chars=4_000)
        return {
            "retrieval_enabled": runtime(request).settings.memory_retrieval_enabled,
            "projection": projection.content,
            "source_ids": projection.memory_ids,
            "hits": [
                {
                    **_summary(hit.item),
                    "reason": hit.reason,
                    "matched_terms": hit.matched_terms,
                    "score": hit.score,
                    "projected": hit.item.id in projection.memory_ids,
                }
                for hit in hits
            ],
        }

    @app.post("/api/memory/workspace/items/{memory_id}/reject")
    async def reject(request: Request, memory_id: str, payload: VersionInput) -> dict[str, object]:
        memory, host = store(request)
        try:
            item = await memory.reject(
                host_id=host, memory_id=memory_id, expected_version=payload.expected_version
            )
        except (MemoryNotFoundError, MemoryStateError):
            raise HTTPException(409, "Candidate missing or stale; refresh") from None
        return item.model_dump(mode="json")

    @app.get("/api/memory/workspace/retention")
    async def retention(request: Request) -> list[dict[str, object]]:
        memory, host = store(request)
        return [
            rule.model_dump(mode="json") for rule in await memory.get_retention_rules(host_id=host)
        ]

    @app.post("/api/memory/workspace/retention")
    async def set_retention(request: Request, payload: RetentionInput) -> dict[str, object]:
        memory, host = store(request)
        rule = await memory.set_retention_rule(
            host_id=host, category=payload.category, retention_days=payload.days
        )
        return rule.model_dump(mode="json")

    @app.post("/api/memory/workspace/expire")
    async def expire(request: Request) -> dict[str, object]:
        memory, host = store(request)
        return (await memory.expire_due(host_id=host)).model_dump(mode="json")
