"""Loopback-only Phase 1 browser chat and memory-control API."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Self

from fastapi import FastAPI, HTTPException, Path, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from jarvis.bootstrap import RuntimeComponents, build_runtime
from jarvis.config import Settings
from jarvis.core import AssistantRequest, ModelRole, ReasoningLevel
from jarvis.memory import (
    ConfirmationInterface,
    MemoryCategory,
    MemoryConfirmation,
    MemoryKind,
    MemoryNotFoundError,
    MemoryQuery,
    MemoryStateError,
    explicit_provenance,
)
from jarvis.research import (
    ResearchInterface,
    ResearchNotFoundError,
    ResearchPlan,
    ResearchStateError,
    ResearchStorageApproval,
    SourceState,
    UnansweredQuestionStatus,
)

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
    category: MemoryCategory | None = None
    key: str | None = Field(default=None, min_length=1, max_length=500)


class MemoryConfirmationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    expected_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class MemoryCorrectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    content: str = Field(min_length=1, max_length=100_000)
    key: str | None = Field(default=None, min_length=1, max_length=500)


class ResearchRunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=1, max_length=2_000)
    questions: tuple[str, ...] = Field(min_length=1, max_length=20)
    max_sources: int = Field(default=10, ge=1, le=50)
    max_fetches: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def require_fetch_capacity(self) -> Self:
        if self.max_sources > self.max_fetches:
            raise ValueError("max_sources cannot exceed max_fetches")
        return self


class ResearchApprovalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "deny"]
    expected_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    supersedes_report_id: str | None = Field(default=None, min_length=1, max_length=200)


class ResearchQuestionUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    status: Literal["answered", "dismissed"]
    answer_claim_id: str | None = Field(default=None, min_length=1, max_length=200)


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
        runtime = _runtime(request)
        if runtime.memory_store is not None and runtime.memory_host_id is not None:
            await runtime.memory_store.delete_by_conversation(
                host_id=runtime.memory_host_id,
                conversation_id=conversation_id,
            )
        deleted = await runtime.store.delete_conversation(conversation_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"deleted": True}

    @app.get("/api/memories")
    async def list_memories(request: Request, limit: int = 100) -> list[dict[str, object]]:
        runtime = _runtime(request)
        if runtime.memory_store is None or runtime.memory_host_id is None:
            legacy_records = await runtime.store.list_memories(limit=limit)
            return [record.model_dump(mode="json") for record in legacy_records]
        phase4_records = await runtime.memory_store.list(
            host_id=runtime.memory_host_id,
            limit=limit,
        )
        return [record.model_dump(mode="json") for record in phase4_records]

    @app.post("/api/memories", status_code=201)
    async def create_memory(payload: MemoryInput, request: Request) -> dict[str, object]:
        runtime = _runtime(request)
        if runtime.memory_store is None or runtime.memory_host_id is None:
            legacy_record = await runtime.store.create_memory(
                kind=payload.kind,
                content=payload.content,
                provenance=payload.provenance,
            )
            return legacy_record.model_dump(mode="json")
        category = (
            payload.category
            or {
                MemoryKind.NOTE: MemoryCategory.SEMANTIC,
                MemoryKind.PROFILE: MemoryCategory.PROFILE,
                MemoryKind.TASK: MemoryCategory.TASK,
            }[payload.kind]
        )
        phase4_record = await runtime.memory_store.remember(
            host_id=runtime.memory_host_id,
            category=category,
            content=payload.content,
            key=payload.key,
            provenance=explicit_provenance(
                source_id=f"local-web:{datetime.now(UTC).isoformat(timespec='microseconds')}",
                source_label=payload.provenance,
            ),
        )
        return phase4_record.model_dump(mode="json")

    @app.get("/api/memory/search")
    async def search_memory(
        request: Request,
        query: str,
        limit: int = 8,
    ) -> list[dict[str, object]]:
        runtime = _runtime(request)
        if runtime.memory_store is None or runtime.memory_host_id is None:
            raise HTTPException(status_code=503, detail="Phase 4 memory is unavailable")
        hits = await runtime.memory_store.search(
            MemoryQuery(host_id=runtime.memory_host_id, text=query, limit=limit)
        )
        return [hit.model_dump(mode="json") for hit in hits]

    @app.post("/api/memory/candidates/{memory_id}/promote")
    async def promote_memory_candidate(
        payload: MemoryConfirmationInput,
        request: Request,
        memory_id: Annotated[str, Path(min_length=1, max_length=200)],
    ) -> dict[str, object]:
        runtime = _runtime(request)
        if runtime.memory_store is None or runtime.memory_host_id is None:
            raise HTTPException(status_code=503, detail="Phase 4 memory is unavailable")
        try:
            item = await runtime.memory_store.promote(
                MemoryConfirmation(
                    host_id=runtime.memory_host_id,
                    interface=ConfirmationInterface.LOCAL_WEB,
                    candidate_id=memory_id,
                    expected_version=payload.expected_version,
                    expected_content_sha256=payload.expected_content_sha256,
                    confirmed_at=datetime.now(UTC),
                )
            )
        except (MemoryNotFoundError, MemoryStateError):
            raise HTTPException(status_code=409, detail="Candidate is missing or stale") from None
        return item.model_dump(mode="json")

    @app.post("/api/memory/{memory_id}/correct")
    async def correct_memory(
        payload: MemoryCorrectionInput,
        request: Request,
        memory_id: Annotated[str, Path(min_length=1, max_length=200)],
    ) -> dict[str, object]:
        runtime = _runtime(request)
        if runtime.memory_store is None or runtime.memory_host_id is None:
            raise HTTPException(status_code=503, detail="Phase 4 memory is unavailable")
        try:
            item = await runtime.memory_store.correct(
                host_id=runtime.memory_host_id,
                memory_id=memory_id,
                expected_version=payload.expected_version,
                content=payload.content,
                key=payload.key,
                provenance=explicit_provenance(
                    source_id=(
                        "local-web-correction:"
                        + datetime.now(UTC).isoformat(timespec="microseconds")
                    ),
                    source_label="explicit local browser correction",
                ),
            )
        except (MemoryNotFoundError, MemoryStateError):
            raise HTTPException(status_code=409, detail="Memory is missing or stale") from None
        return item.model_dump(mode="json")

    @app.delete("/api/memories/{memory_id}")
    async def delete_memory(
        request: Request,
        memory_id: Annotated[str, Path(min_length=1, max_length=200)],
    ) -> dict[str, bool]:
        runtime = _runtime(request)
        if runtime.memory_store is None or runtime.memory_host_id is None:
            deleted = await runtime.store.delete_memory(memory_id)
            if not deleted:
                raise HTTPException(status_code=404, detail="Memory not found")
            return {"deleted": True}
        try:
            await runtime.memory_store.delete(
                host_id=runtime.memory_host_id,
                memory_id=memory_id,
            )
        except MemoryNotFoundError:
            raise HTTPException(status_code=404, detail="Memory not found") from None
        return {"deleted": True}

    @app.post("/api/research/runs")
    async def run_research(payload: ResearchRunInput, request: Request) -> dict[str, object]:
        runtime = _runtime(request)
        if runtime.research is None or runtime.memory_host_id is None:
            raise HTTPException(status_code=503, detail="Research is disabled")
        try:
            pending = await runtime.research.run(
                host_id=runtime.memory_host_id,
                plan=ResearchPlan(
                    objective=payload.objective,
                    questions=payload.questions,
                    max_sources=payload.max_sources,
                    max_fetches=payload.max_fetches,
                ),
            )
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"Research failed: {type(exc).__name__}"
            ) from None
        return pending.model_dump(mode="json")

    @app.post("/api/research/runs/{pending_run_id}/approval")
    async def decide_research_storage(
        payload: ResearchApprovalInput,
        request: Request,
        pending_run_id: Annotated[str, Path(min_length=1, max_length=200)],
    ) -> dict[str, object]:
        runtime = _runtime(request)
        if runtime.research is None or runtime.memory_host_id is None:
            raise HTTPException(status_code=503, detail="Research is disabled")
        try:
            if payload.decision == "deny":
                receipt = await runtime.research.deny(
                    host_id=runtime.memory_host_id,
                    pending_run_id=pending_run_id,
                    expected_report_sha256=payload.expected_report_sha256,
                )
            else:
                receipt = await runtime.research.approve(
                    ResearchStorageApproval(
                        host_id=runtime.memory_host_id,
                        pending_run_id=pending_run_id,
                        expected_report_sha256=payload.expected_report_sha256,
                        interface=ResearchInterface.LOCAL_WEB,
                        approved_at=datetime.now(UTC),
                        supersedes_report_id=payload.supersedes_report_id,
                    )
                )
        except ResearchNotFoundError:
            raise HTTPException(status_code=404, detail="Pending research run not found") from None
        except ResearchStateError:
            raise HTTPException(status_code=409, detail="Pending research run changed") from None
        return receipt.model_dump(mode="json")

    @app.get("/api/research/reports")
    async def list_research_reports(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> list[dict[str, object]]:
        runtime = _runtime(request)
        if runtime.research_store is None or runtime.memory_host_id is None:
            raise HTTPException(status_code=503, detail="Research storage is unavailable")
        reports = await runtime.research_store.list_reports(
            host_id=runtime.memory_host_id, limit=limit
        )
        return [report.model_dump(mode="json") for report in reports]

    @app.get("/api/research/reports/{report_id}")
    async def get_research_report(
        request: Request,
        report_id: Annotated[str, Path(min_length=1, max_length=200)],
    ) -> dict[str, object]:
        runtime = _runtime(request)
        if runtime.research_store is None or runtime.memory_host_id is None:
            raise HTTPException(status_code=503, detail="Research storage is unavailable")
        report = await runtime.research_store.get_report(
            host_id=runtime.memory_host_id, report_id=report_id
        )
        if report is None:
            raise HTTPException(status_code=404, detail="Research report not found")
        return report.model_dump(mode="json")

    @app.get("/api/research/sources")
    async def list_research_sources(
        request: Request,
        state: SourceState | None = None,
        query: Annotated[str | None, Query(min_length=1, max_length=1_000)] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> list[dict[str, object]]:
        runtime = _runtime(request)
        if runtime.research_store is None or runtime.memory_host_id is None:
            raise HTTPException(status_code=503, detail="Research storage is unavailable")
        if query is None:
            sources = await runtime.research_store.list_sources(
                host_id=runtime.memory_host_id, state=state, limit=limit
            )
        else:
            sources = await runtime.research_store.search_sources(
                host_id=runtime.memory_host_id, text=query, limit=limit
            )
        return [source.model_dump(mode="json") for source in sources]

    @app.post("/api/research/sources/{source_id}/revalidate")
    async def revalidate_research_source(
        request: Request,
        source_id: Annotated[str, Path(min_length=1, max_length=200)],
    ) -> dict[str, object]:
        runtime = _runtime(request)
        if runtime.research is None or runtime.memory_host_id is None:
            raise HTTPException(status_code=503, detail="Research is disabled")
        try:
            receipt = await runtime.research.revalidate_source(
                host_id=runtime.memory_host_id, source_id=source_id
            )
        except ResearchNotFoundError:
            raise HTTPException(status_code=404, detail="Research source not found") from None
        return receipt.model_dump(mode="json")

    @app.delete("/api/research/sources/{source_id}")
    async def delete_research_source(
        request: Request,
        source_id: Annotated[str, Path(min_length=1, max_length=200)],
        confirm_source_id: Annotated[str, Query(min_length=1, max_length=200)],
    ) -> dict[str, object]:
        runtime = _runtime(request)
        if runtime.research_store is None or runtime.memory_host_id is None:
            raise HTTPException(status_code=503, detail="Research storage is unavailable")
        if confirm_source_id != source_id:
            raise HTTPException(status_code=409, detail="Deletion confirmation does not match")
        try:
            receipt = await runtime.research_store.delete_source(
                host_id=runtime.memory_host_id, source_id=source_id
            )
        except ResearchNotFoundError:
            raise HTTPException(status_code=404, detail="Research source not found") from None
        return receipt.model_dump(mode="json")

    @app.get("/api/research/questions")
    async def list_research_questions(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> list[dict[str, object]]:
        runtime = _runtime(request)
        if runtime.research_store is None or runtime.memory_host_id is None:
            raise HTTPException(status_code=503, detail="Research storage is unavailable")
        questions = await runtime.research_store.list_unanswered_questions(
            host_id=runtime.memory_host_id, limit=limit
        )
        return [question.model_dump(mode="json") for question in questions]

    @app.post("/api/research/questions/{question_id}")
    async def update_research_question(
        payload: ResearchQuestionUpdateInput,
        request: Request,
        question_id: Annotated[str, Path(min_length=1, max_length=200)],
    ) -> dict[str, object]:
        runtime = _runtime(request)
        if runtime.research_store is None or runtime.memory_host_id is None:
            raise HTTPException(status_code=503, detail="Research storage is unavailable")
        try:
            question = await runtime.research_store.update_unanswered_question(
                host_id=runtime.memory_host_id,
                question_id=question_id,
                expected_version=payload.expected_version,
                status=UnansweredQuestionStatus(payload.status),
                answer_claim_id=payload.answer_claim_id,
                interface=ResearchInterface.LOCAL_WEB,
            )
        except ResearchNotFoundError:
            raise HTTPException(status_code=404, detail="Question or claim not found") from None
        except ResearchStateError:
            raise HTTPException(status_code=409, detail="Question changed or is invalid") from None
        return question.model_dump(mode="json")

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
#research-result{white-space:pre-wrap;border:1px solid #29324a;padding:1rem;margin-top:.5rem}.hidden{display:none}
.you{color:#9ecbff}.jarvis{color:#8ef0b3}.meta{color:#98a2b8;font-size:.85rem}
</style></head><body><h1>JARVIS</h1><p class="meta">Loopback browser chat. Routing shown after each turn.</p>
<div id="log" aria-live="polite"></div><form id="chat"><input id="message" autocomplete="off" autofocus
placeholder="Ask JARVIS" maxlength="100000"><button>Send</button></form>
<h2>Research</h2><p class="meta">Results stay volatile until exact local approval.</p>
<form id="research"><input id="objective" placeholder="Public research objective" maxlength="2000">
<input id="question" placeholder="Public question" maxlength="2000"><button>Research</button></form>
<div id="research-result" class="hidden"></div><div id="research-actions" class="hidden">
<button id="research-approve" type="button">Approve storage</button>
<button id="research-deny" type="button">Discard</button></div><script>
let conversation=null;const log=document.querySelector('#log'),form=document.querySelector('#chat'),input=document.querySelector('#message');
function row(cls,text){const element=document.createElement('div');element.className=cls;element.textContent=text;log.appendChild(element);return element;}
form.addEventListener('submit',async e=>{e.preventDefault();const message=input.value.trim();if(!message)return;
row('you',`You: ${message}`);input.value='';const answer=row('jarvis','JARVIS: ');let streamed='',route=null,result=null;
try{const response=await fetch('/api/chat/stream',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({message,conversation_id:conversation})});
if(!response.ok||!response.body)throw new Error(`HTTP ${response.status}`);const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
while(true){const {value,done}=await reader.read();buffer+=decoder.decode(value||new Uint8Array(),{stream:!done});const blocks=buffer.split('\n\n');buffer=blocks.pop()||'';
for(const block of blocks){const data=block.split('\n').filter(line=>line.startsWith('data:')).map(line=>line.slice(5).trim()).join('');if(!data)continue;const frame=JSON.parse(data);
if(frame.event?.type==='assistant_delta'&&frame.event.content_delta){streamed+=frame.event.content_delta;answer.textContent=`JARVIS: ${streamed}`;}
if(frame.event?.type==='routing_decided')route=frame.event.routing;if(frame.result)result=frame.result;}if(done)break;}
if(!result)throw new Error('stream ended without result');conversation=result.conversation_id||conversation;
if(!streamed)answer.textContent=`JARVIS: ${result.reply||result.error?.message||'Failed'}`;
route=route||result.events?.find(event=>event.type==='routing_decided')?.routing;
if(route)row('meta',`Route: ${route.chosen_role} · ${route.sensitivity}`);
}catch(error){answer.textContent=`JARVIS: Streaming failed (${error.message||'unknown error'})`;}
log.scrollTop=log.scrollHeight;});
let pendingResearch=null;const researchForm=document.querySelector('#research'),researchResult=document.querySelector('#research-result'),researchActions=document.querySelector('#research-actions');
researchForm.addEventListener('submit',async e=>{e.preventDefault();const objective=document.querySelector('#objective').value.trim(),question=document.querySelector('#question').value.trim();if(!objective||!question)return;
researchResult.classList.remove('hidden');researchResult.textContent='Researching…';researchActions.classList.add('hidden');pendingResearch=null;
try{const response=await fetch('/api/research/runs',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({objective,questions:[question]})});if(!response.ok)throw new Error(`HTTP ${response.status}`);pendingResearch=await response.json();researchResult.textContent=`${pendingResearch.result.report.answer}\n\nSHA-256: ${pendingResearch.report_sha256}`;researchActions.classList.remove('hidden');}catch(error){researchResult.textContent=`Research failed (${error.message||'unknown error'})`;}});
async function decideResearch(decision){if(!pendingResearch)return;const response=await fetch(`/api/research/runs/${encodeURIComponent(pendingResearch.id)}/approval`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({decision,expected_report_sha256:pendingResearch.report_sha256})});if(!response.ok){researchResult.textContent+=`\nDecision failed (HTTP ${response.status})`;return;}const receipt=await response.json();researchResult.textContent+=receipt.stored?`\nStored report: ${receipt.report_id}`:'\nDiscarded; nothing stored.';researchActions.classList.add('hidden');pendingResearch=null;}
document.querySelector('#research-approve').addEventListener('click',()=>decideResearch('approve'));document.querySelector('#research-deny').addEventListener('click',()=>decideResearch('deny'));
</script></body></html>"""
