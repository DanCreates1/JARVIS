"""Loopback-only Phase 1 browser chat and memory-control API."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Path, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from jarvis.bootstrap import RuntimeComponents, build_runtime
from jarvis.config import Settings
from jarvis.core import AssistantRequest, ModelRole, ReasoningLevel
from jarvis.memory import MemoryKind

RuntimeFactory = Callable[[Settings], Awaitable[RuntimeComponents]]


class ChatInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=100_000)
    conversation_id: str | None = Field(default=None, max_length=200)
    model_role: ModelRole | None = None
    reasoning_level: ReasoningLevel | None = None


class MemoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: MemoryKind = MemoryKind.NOTE
    content: str = Field(min_length=1, max_length=100_000)
    provenance: str = Field(default="explicit browser entry", min_length=1, max_length=2_000)


def create_app(
    settings: Settings | None = None,
    *,
    runtime_factory: RuntimeFactory = build_runtime,
) -> FastAPI:
    configured = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        components = await runtime_factory(configured)
        app.state.runtime = components
        try:
            yield
        finally:
            await components.close()

    app = FastAPI(title="JARVIS Phase 1", version="1", lifespan=lifespan)

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
            "connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return _CHAT_HTML

    @app.get("/api/health")
    async def health(request: Request) -> dict[str, object]:
        runtime = _runtime(request)
        return {
            "status": "ready",
            "cloud_policy": runtime.settings.cloud_policy,
            "max_cloud_cost_usd": runtime.settings.max_cloud_cost_usd,
            "roles": [role.value for role in runtime.provider.providers],
        }

    @app.post("/api/chat")
    async def chat(payload: ChatInput, request: Request) -> dict[str, object]:
        runtime = _runtime(request)
        result = await runtime.service.run(_assistant_request(payload))
        return result.model_dump(mode="json")

    @app.post("/api/chat/stream")
    async def stream_chat(payload: ChatInput, request: Request) -> StreamingResponse:
        runtime = _runtime(request)

        async def events() -> AsyncIterator[str]:
            async for frame in runtime.service.stream(_assistant_request(payload)):
                yield f"data: {frame.model_dump_json()}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.delete("/api/conversations/{conversation_id}")
    async def delete_conversation(
        request: Request,
        conversation_id: Annotated[str, Path(min_length=1, max_length=200)],
    ) -> dict[str, bool]:
        deleted = await _runtime(request).store.delete_conversation(conversation_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"deleted": True}

    @app.get("/api/memories")
    async def list_memories(request: Request, limit: int = 100) -> list[dict[str, object]]:
        records = await _runtime(request).store.list_memories(limit=limit)
        return [record.model_dump(mode="json") for record in records]

    @app.post("/api/memories", status_code=201)
    async def create_memory(payload: MemoryInput, request: Request) -> dict[str, object]:
        record = await _runtime(request).store.create_memory(
            kind=payload.kind,
            content=payload.content,
            provenance=payload.provenance,
        )
        return record.model_dump(mode="json")

    @app.delete("/api/memories/{memory_id}")
    async def delete_memory(
        request: Request,
        memory_id: Annotated[str, Path(min_length=1, max_length=200)],
    ) -> dict[str, bool]:
        deleted = await _runtime(request).store.delete_memory(memory_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Memory not found")
        return {"deleted": True}

    @app.get("/api/audit")
    async def list_audit(request: Request, limit: int = 100) -> list[dict[str, object]]:
        records = await _runtime(request).store.list_audit_records(limit=limit)
        return [record.model_dump(mode="json") for record in records]

    return app


def _runtime(request: Request) -> RuntimeComponents:
    return request.app.state.runtime  # type: ignore[no-any-return]


def _assistant_request(payload: ChatInput) -> AssistantRequest:
    return AssistantRequest(
        user_input=payload.message,
        conversation_id=payload.conversation_id,
        metadata={"interface": "browser"},
        requested_model_role=payload.model_role,
        reasoning_level=payload.reasoning_level,
    )


_CHAT_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>JARVIS</title><style>
body{font:16px system-ui;background:#0b1020;color:#e8edf7;max-width:850px;margin:2rem auto;padding:1rem}
#log{min-height:55vh;white-space:pre-wrap;border:1px solid #29324a;padding:1rem;border-radius:10px}
form{display:flex;gap:.5rem;margin-top:1rem}input{flex:1;padding:.8rem}button{padding:.8rem 1.2rem}
.you{color:#9ecbff}.jarvis{color:#8ef0b3}.meta{color:#98a2b8;font-size:.85rem}
</style></head><body><h1>JARVIS</h1><p class="meta">Loopback browser chat. Routing shown after each turn.</p>
<div id="log" aria-live="polite"></div><form id="chat"><input id="message" autocomplete="off" autofocus
placeholder="Ask JARVIS" maxlength="100000"><button>Send</button></form><script>
let conversation=null;const log=document.querySelector('#log'),form=document.querySelector('#chat'),input=document.querySelector('#message');
form.addEventListener('submit',async e=>{e.preventDefault();const message=input.value.trim();if(!message)return;
log.innerHTML+=`<div class="you">You: ${escapeHtml(message)}</div>`;input.value='';
const response=await fetch('/api/chat',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({message,conversation_id:conversation})});
const result=await response.json();conversation=result.conversation_id||conversation;
log.innerHTML+=`<div class="jarvis">JARVIS: ${escapeHtml(result.reply||result.error?.message||'Failed')}</div>`;
const route=result.events?.find(e=>e.type==='routing_decided')?.routing;
if(route)log.innerHTML+=`<div class="meta">Route: ${route.chosen_role} · ${route.sensitivity}</div>`;log.scrollTop=log.scrollHeight;});
function escapeHtml(value){const e=document.createElement('div');e.textContent=value;return e.innerHTML;}
</script></body></html>"""
