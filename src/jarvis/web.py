"""Loopback-only Phase 1 browser chat and memory-control API."""

from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from http.cookies import CookieError, SimpleCookie
from pathlib import Path as FileSystemPath
from typing import Annotated, Any, Literal, Self, cast

from fastapi import FastAPI, HTTPException, Path, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
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
from jarvis.planning import TaskNotFoundError, TaskPlanProposal, TaskStateError, TaskStatus
from jarvis.remote import (
    BrowserOriginError,
    BrowserOriginPolicy,
    EnrollmentCompletion,
    FixedWindowRateLimiter,
    KeyRotationRequest,
    ProtocolHello,
    PWAEventHub,
    PWAEventTopic,
    PWATransportError,
    RemoteAuthenticationError,
    RemoteIdentityContext,
    RemoteIdentityService,
    RemoteScope,
    RemoteSessionKind,
    RemoteStateError,
    SessionRequest,
    SignedRequest,
    TopologyNegotiationError,
    TopologyNegotiator,
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
_REMOTE_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43,128}$")
_MAX_REMOTE_BODY_BYTES = 1_048_576
_MAX_REMOTE_HEADER_BYTES = 32_768
_MAX_REMOTE_HEADERS = 100
_MAX_REMOTE_PATH_BYTES = 2_048
_MAX_REMOTE_QUERY_BYTES = 8_192
_BROWSER_SESSION_COOKIE = "__Host-jarvis-session"
_CSRF_HEADER = "x-jarvis-csrf"
_BROWSER_ORIGIN_HEADER = "x-jarvis-browser-origin"
_SAFE_BROWSER_METHODS = frozenset({"GET", "HEAD"})
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_REMOTE_HEADER_NAMES = (
    "x-jarvis-audience",
    "x-jarvis-date",
    "x-jarvis-device",
    "x-jarvis-key-version",
    "x-jarvis-nonce",
    "x-jarvis-signature",
)
_PWA_ROOT = FileSystemPath(__file__).with_name("pwa")


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


class PWASubscriptionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topics: tuple[PWAEventTopic, ...] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def require_unique_topics(self) -> Self:
        if len(self.topics) != len(set(self.topics)):
            raise ValueError("subscription topics must be unique")
        return self


class PWAChatInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
    subscription_id: str = Field(pattern=r"^subscription:[0-9a-f-]{36}$")
    message: str = Field(min_length=1, max_length=100_000)
    conversation_id: str | None = Field(default=None, max_length=200)
    model_role: ModelRole | None = None
    reasoning_level: ReasoningLevel | None = None


def create_app(
    settings: Settings | None = None,
    *,
    runtime_factory: RuntimeFactory = build_runtime,
) -> FastAPI:
    configured = settings or Settings()
    pwa_hub = PWAEventHub()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        components = await runtime_factory(configured)
        app.state.runtime = components
        try:
            yield
        finally:
            try:
                await pwa_hub.close()
            finally:
                await components.close()

    app = FastAPI(title="JARVIS API", version="1.0", lifespan=lifespan)
    app.state.pwa_hub = pwa_hub
    origin_policy = BrowserOriginPolicy(configured.trusted_browser_origins)
    rate_limiter = FixedWindowRateLimiter(max_entries=configured.remote_rate_limit_entries)

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        if request.url.path == "/app" or request.url.path.startswith("/app/"):
            _apply_pwa_security_headers(response, path=request.url.path)
        else:
            _apply_security_headers(response, api_only=request.url.path.startswith("/api/"))
        trusted_origin = getattr(request.state, "trusted_origin", None)
        if isinstance(trusted_origin, str):
            _apply_cors_headers(response, trusted_origin)
        return response

    @app.middleware("http")
    async def remote_v1_authentication(request: Request, call_next: Any) -> Any:
        public_route, required_scope = _remote_scope_for_request(request.method, request.url.path)
        if request.url.path.startswith("/api/v1/"):
            try:
                _validate_remote_request_shape(request)
                origins = _header_values(request, "origin")
                if request.method == "OPTIONS":
                    trusted_origin = origin_policy.require(origins)
                    _validate_preflight(request)
                    decision = rate_limiter.check(
                        f"preflight:{_client_key(request)}",
                        limit=configured.remote_public_requests_per_minute,
                    )
                    if not decision.allowed:
                        return _remote_rate_error(decision.retry_after_seconds)
                    response = Response(status_code=204)
                    _apply_cors_headers(response, trusted_origin, preflight=True)
                    _apply_security_headers(response, api_only=True)
                    return response
                body = await _read_bounded_remote_body(request)
                browser_token = _browser_cookie_token(request)
                if browser_token is not None and _header_values(request, "authorization"):
                    return _remote_error(400, "Ambiguous remote authentication")
                rate_kind = "public" if public_route else "authenticated"
                rate_key = f"{rate_kind}:{_client_key(request)}:{_identity_rate_key(request, browser_token)}"
                limit = (
                    configured.remote_public_requests_per_minute
                    if public_route
                    else configured.remote_authenticated_requests_per_minute
                )
                for key in (f"{rate_kind}:ip:{_client_key(request)}", rate_key):
                    decision = rate_limiter.check(key, limit=limit)
                    if not decision.allowed:
                        return _remote_rate_error(decision.retry_after_seconds)
                if request.url.path == "/api/v1/browser/sessions":
                    request.state.trusted_origin = origin_policy.require(origins)
                if public_route:
                    return await call_next(request)
                service = _remote_identity(request)
                if browser_token is not None:
                    opaque_origin = origins == ("null",)
                    if origins and not opaque_origin:
                        trusted_origin = origin_policy.require(origins)
                    elif request.method in _SAFE_BROWSER_METHODS:
                        trusted_origin = origin_policy.require(
                            _header_values(request, _BROWSER_ORIGIN_HEADER)
                        )
                    else:
                        trusted_origin = origin_policy.require(origins)
                    request.state.trusted_origin = trusted_origin
                    csrf_token = _csrf_token(request) if request.method in _UNSAFE_METHODS else None
                    context = await service.authenticate_browser_session(
                        cookie_token=browser_token,
                        csrf_token=csrf_token,
                        require_csrf=request.method in _UNSAFE_METHODS,
                        required_scope=required_scope,
                    )
                else:
                    optional_origin = origin_policy.optional(origins)
                    if optional_origin is not None:
                        request.state.trusted_origin = optional_origin
                    token = _bearer_token(request)
                    signed_request, signature = _signed_remote_request(
                        request,
                        body=body,
                        session_token=token,
                    )
                    context = await service.authenticate_request(
                        request=signed_request,
                        signature=signature,
                        required_scope=required_scope,
                    )
                request.state.remote_identity = context
            except RemoteAuthenticationError:
                return _remote_error(401, "Remote authentication failed", authenticate=True)
            except RemoteStateError:
                return _remote_error(403, "Remote scope denied")
            except BrowserOriginError:
                return _remote_error(403, "Browser origin denied")
            except RemoteBodyTooLargeError:
                return _remote_error(413, "Remote request body too large")
            except (UnicodeError, ValueError):
                return _remote_error(400, "Malformed remote authentication headers")
        return await call_next(request)

    @app.get("/app", include_in_schema=False)
    @app.get("/app/", include_in_schema=False)
    async def pwa_index() -> FileResponse:
        return FileResponse(_PWA_ROOT / "index.html", media_type="text/html")

    @app.get("/app/app.css", include_in_schema=False)
    async def pwa_css() -> FileResponse:
        return FileResponse(_PWA_ROOT / "app.css", media_type="text/css")

    @app.get("/app/app.js", include_in_schema=False)
    async def pwa_javascript() -> FileResponse:
        return FileResponse(_PWA_ROOT / "app.js", media_type="text/javascript")

    @app.get("/app/sw.js", include_in_schema=False)
    async def pwa_service_worker() -> FileResponse:
        return FileResponse(_PWA_ROOT / "sw.js", media_type="text/javascript")

    @app.get("/app/manifest.webmanifest", include_in_schema=False)
    async def pwa_manifest() -> FileResponse:
        return FileResponse(
            _PWA_ROOT / "manifest.webmanifest",
            media_type="application/manifest+json",
        )

    @app.get("/app/icon.svg", include_in_schema=False)
    async def pwa_icon() -> FileResponse:
        return FileResponse(_PWA_ROOT / "icon.svg", media_type="image/svg+xml")

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
            "task_execution_enabled": runtime.settings.task_execution_enabled,
        }

    @app.post("/api/v1/enrollments/complete", status_code=201)
    async def complete_remote_enrollment(
        payload: EnrollmentCompletion, request: Request
    ) -> dict[str, object]:
        try:
            device = await _remote_identity(request).complete_enrollment(payload)
        except RemoteAuthenticationError:
            raise HTTPException(
                status_code=401, detail="Enrollment authentication failed"
            ) from None
        return device.model_dump(mode="json")

    @app.post("/api/v1/sessions", status_code=201)
    async def create_remote_session(payload: SessionRequest, request: Request) -> dict[str, object]:
        try:
            signed_request, signature = _signed_remote_request(
                request,
                body=await request.body(),
                session_token=None,
            )
            credential = await _remote_identity(request).create_session(
                request=signed_request,
                signature=signature,
                payload=payload,
            )
        except RemoteAuthenticationError:
            raise HTTPException(status_code=401, detail="Remote authentication failed") from None
        except RemoteStateError:
            raise HTTPException(status_code=403, detail="Remote scope denied") from None
        except (UnicodeError, ValueError):
            raise HTTPException(
                status_code=400, detail="Malformed remote authentication headers"
            ) from None
        return credential.model_dump(mode="json")

    @app.post("/api/v1/browser/sessions", status_code=201)
    async def create_browser_session(
        payload: SessionRequest, request: Request, response: Response
    ) -> dict[str, object]:
        try:
            signed_request, signature = _signed_remote_request(
                request,
                body=await request.body(),
                session_token=None,
            )
            credential = await _remote_identity(request).create_browser_session(
                request=signed_request,
                signature=signature,
                payload=payload,
            )
        except RemoteAuthenticationError:
            raise HTTPException(status_code=401, detail="Remote authentication failed") from None
        except RemoteStateError:
            raise HTTPException(status_code=403, detail="Remote scope denied") from None
        except (UnicodeError, ValueError):
            raise HTTPException(
                status_code=400, detail="Malformed remote authentication headers"
            ) from None
        response.set_cookie(
            key=_BROWSER_SESSION_COOKIE,
            value=credential.cookie_token,
            secure=True,
            httponly=True,
            samesite="strict",
            path="/",
            expires=credential.expires_at,
        )
        return cast(
            dict[str, object],
            jsonable_encoder(
                {
                    "session_id": credential.session_id,
                    "csrf_token": credential.csrf_token,
                    "device_id": credential.device_id,
                    "key_version": credential.key_version,
                    "audience": credential.audience,
                    "scopes": credential.scopes,
                    "expires_at": credential.expires_at,
                },
            ),
        )

    @app.get("/api/v1/identity")
    async def get_remote_identity(request: Request) -> dict[str, object]:
        try:
            device = await _remote_identity(request).get_current_device(_remote_context(request))
        except RemoteStateError:
            raise HTTPException(status_code=403, detail="Remote scope denied") from None
        return device.model_dump(mode="json")

    @app.post("/api/v1/topology/negotiate")
    async def negotiate_topology(payload: ProtocolHello, request: Request) -> dict[str, object]:
        context = _remote_context(request)
        identity = _remote_identity(request)
        try:
            result = _topology(request).negotiate(context=context, hello=payload)
        except TopologyNegotiationError as exc:
            await identity.record_protocol_negotiation(
                context=context,
                succeeded=False,
                reason_code=exc.code,
            )
            raise HTTPException(
                status_code=409,
                detail={"code": exc.code, "message": "Topology negotiation failed"},
            ) from None
        await identity.record_protocol_negotiation(
            context=context,
            succeeded=True,
            reason_code="capabilities_negotiated",
        )
        return cast(dict[str, object], jsonable_encoder(result.model_dump(mode="json")))

    @app.get("/api/v1/events")
    async def list_remote_identity_events(
        request: Request,
        after: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> list[dict[str, object]]:
        try:
            events = await _remote_identity(request).list_device_events(
                context=_remote_context(request),
                after_sequence=after,
                limit=limit,
            )
        except RemoteStateError:
            raise HTTPException(status_code=403, detail="Remote scope denied") from None
        return [event.model_dump(mode="json") for event in events]

    @app.get("/api/v1/client/status")
    async def get_pwa_status(request: Request) -> dict[str, object]:
        context = _remote_context(request)
        runtime = _runtime(request)
        _require_remote_host(runtime, context)
        try:
            device = await _remote_identity(request).get_current_device(context)
        except RemoteStateError:
            raise HTTPException(status_code=403, detail="Remote scope denied") from None
        task_counts: dict[str, int] = {}
        if runtime.task_store is not None and runtime.memory_host_id is not None:
            for record in await runtime.task_store.list_tasks(
                host_id=runtime.memory_host_id,
                limit=500,
            ):
                task_counts[record.status.value] = task_counts.get(record.status.value, 0) + 1
        return cast(
            dict[str, object],
            jsonable_encoder(
                {
                    "online": True,
                    "device": {
                        "id": device.id,
                        "display_name": device.display_name,
                        "device_type": device.device_type,
                        "state": device.state,
                        "key_version": device.key_version,
                        "credential_expires_at": device.credential_expires_at,
                    },
                    "session": {
                        "id": context.session_id,
                        "scopes": sorted(scope.value for scope in context.scopes),
                    },
                    "task_counts": task_counts,
                    "notifications": {
                        "supported": True,
                        "private_preview": False,
                    },
                }
            ),
        )

    @app.get("/api/v1/client/tasks")
    async def list_pwa_tasks(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> list[dict[str, object]]:
        context = _remote_context(request)
        runtime = _runtime(request)
        _require_remote_host(runtime, context)
        if runtime.task_store is None or runtime.memory_host_id is None:
            return []
        records = await runtime.task_store.list_tasks(
            host_id=runtime.memory_host_id,
            limit=limit,
        )
        return [
            cast(
                dict[str, object],
                jsonable_encoder(
                    {
                        "id": record.graph.id,
                        "status": record.status,
                        "version": record.version,
                        "pause_requested": record.pause_requested,
                        "cancel_requested": record.cancel_requested,
                        "updated_at": record.updated_at,
                    }
                ),
            )
            for record in records
        ]

    @app.post("/api/v1/client/subscriptions", status_code=201)
    async def create_pwa_subscription(
        payload: PWASubscriptionInput, request: Request
    ) -> dict[str, object]:
        context = _remote_context(request)
        _require_remote_host(_runtime(request), context)
        _require_pwa_topic_scopes(context, payload.topics)
        try:
            subscription = await _pwa_hub(request).subscribe(
                context=context,
                topics=payload.topics,
            )
            if PWAEventTopic.DEVICE in payload.topics:
                await _pwa_hub(request).publish(
                    context=context,
                    subscription_id=subscription.id,
                    topic=PWAEventTopic.DEVICE,
                    event_type="device.online",
                    payload={"online": True},
                )
        except PWATransportError as exc:
            raise _pwa_transport_http_error(exc) from None
        return subscription.model_dump(mode="json")

    @app.get("/api/v1/client/events")
    async def stream_pwa_events(
        request: Request,
        subscription_id: Annotated[str, Query(pattern=r"^subscription:[0-9a-f-]{36}$")],
        after: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        wait: Annotated[float, Query(ge=0, le=25)] = 0,
    ) -> StreamingResponse:
        context = _remote_context(request)
        _require_remote_host(_runtime(request), context)
        try:
            page = await _pwa_hub(request).read(
                context=context,
                subscription_id=subscription_id,
                after_cursor=after,
                limit=limit,
                wait_seconds=wait,
            )
        except PWATransportError as exc:
            raise _pwa_transport_http_error(exc) from None

        async def pwa_events() -> AsyncIterator[str]:
            if not page.events:
                yield ": keepalive\n\n"
                return
            for event in page.events:
                yield (
                    f"id: {event.cursor}\n"
                    f"event: {event.event_type}\n"
                    f"data: {event.model_dump_json()}\n\n"
                )

        return StreamingResponse(
            pwa_events(),
            media_type="text/event-stream",
            headers={
                "X-Jarvis-Next-Cursor": str(page.next_cursor),
                "X-Jarvis-Earliest-Cursor": str(page.earliest_cursor),
                "X-Jarvis-Has-More": str(page.has_more).lower(),
                "X-Accel-Buffering": "no",
            },
        )

    @app.delete("/api/v1/client/subscriptions/{subscription_id}")
    async def delete_pwa_subscription(
        request: Request,
        subscription_id: Annotated[str, Path(pattern=r"^subscription:[0-9a-f-]{36}$")],
    ) -> dict[str, bool]:
        context = _remote_context(request)
        try:
            closed = await _pwa_hub(request).close_subscription(
                context=context,
                subscription_id=subscription_id,
            )
        except PWATransportError as exc:
            raise _pwa_transport_http_error(exc) from None
        if not closed:
            raise HTTPException(status_code=404, detail="Subscription unavailable")
        return {"closed": True}

    @app.post("/api/v1/client/chat")
    async def pwa_chat(payload: PWAChatInput, request: Request) -> Response:
        context = _remote_context(request)
        runtime = _runtime(request)
        _require_remote_host(runtime, context)
        hub = _pwa_hub(request)
        try:
            is_new, cached = await hub.begin_request(
                context=context,
                request_id=payload.request_id,
            )
            if not is_new:
                if cached is None:
                    return JSONResponse(
                        status_code=202,
                        content={"request_id": payload.request_id, "status": "running"},
                    )
                return JSONResponse(content=cached)
            await hub.publish(
                context=context,
                subscription_id=payload.subscription_id,
                topic=PWAEventTopic.CHAT,
                event_type="chat.started",
                request_id=payload.request_id,
                payload={},
            )
            result: object | None = None
            emitted_delta = False
            async for frame in runtime.service.stream(_assistant_request(payload)):
                if frame.event is not None:
                    event_payload = frame.event.model_dump(mode="json")
                    emitted_delta = emitted_delta or frame.event.type.value == "assistant_delta"
                    await hub.publish(
                        context=context,
                        subscription_id=payload.subscription_id,
                        topic=PWAEventTopic.CHAT,
                        event_type="chat.frame",
                        request_id=payload.request_id,
                        payload=event_payload,
                    )
                if frame.result is not None:
                    result = frame.result
            if result is None:
                raise RuntimeError("assistant stream ended without a result")
            rendered = cast(dict[str, object], jsonable_encoder(result))
            reply = rendered.get("reply")
            if not emitted_delta and isinstance(reply, str):
                for offset in range(0, len(reply), 16_000):
                    await hub.publish(
                        context=context,
                        subscription_id=payload.subscription_id,
                        topic=PWAEventTopic.CHAT,
                        event_type="chat.delta",
                        request_id=payload.request_id,
                        payload={"content_delta": reply[offset : offset + 16_000]},
                    )
            await hub.complete_request(
                context=context,
                request_id=payload.request_id,
                result=cast(Any, rendered),
            )
            await hub.publish(
                context=context,
                subscription_id=payload.subscription_id,
                topic=PWAEventTopic.CHAT,
                event_type="chat.completed",
                request_id=payload.request_id,
                payload=cast(
                    Any,
                    {
                        "status": rendered.get("status"),
                        "conversation_id": rendered.get("conversation_id"),
                    },
                ),
            )
            return JSONResponse(content=rendered)
        except PWATransportError as exc:
            await hub.abandon_request(context=context, request_id=payload.request_id)
            raise _pwa_transport_http_error(exc) from None
        except Exception:
            await hub.abandon_request(context=context, request_id=payload.request_id)
            with suppress(PWATransportError):
                await hub.publish(
                    context=context,
                    subscription_id=payload.subscription_id,
                    topic=PWAEventTopic.CHAT,
                    event_type="chat.failed",
                    request_id=payload.request_id,
                    payload={"error": "request_failed"},
                )
            raise HTTPException(status_code=502, detail="Assistant request failed") from None

    @app.delete("/api/v1/sessions/current")
    async def revoke_current_remote_session(
        request: Request, response: Response
    ) -> dict[str, bool]:
        revoked = await _remote_identity(request).revoke_current_session(_remote_context(request))
        if not revoked:
            raise HTTPException(status_code=409, detail="Session already changed")
        if _remote_context(request).session_kind is RemoteSessionKind.BROWSER:
            await _pwa_hub(request).clear_session(_remote_context(request).session_id)
            response.delete_cookie(
                key=_BROWSER_SESSION_COOKIE,
                path="/",
                secure=True,
                httponly=True,
                samesite="strict",
            )
            response.headers["Clear-Site-Data"] = '"cache", "cookies", "storage"'
        return {"revoked": True}

    @app.post("/api/v1/device/key")
    async def rotate_remote_device_key(
        payload: KeyRotationRequest, request: Request
    ) -> dict[str, object]:
        try:
            device = await _remote_identity(request).rotate_key(
                context=_remote_context(request),
                payload=payload,
            )
        except RemoteAuthenticationError:
            raise HTTPException(status_code=401, detail="Remote authentication failed") from None
        except RemoteStateError:
            raise HTTPException(status_code=409, detail="Remote key rotation rejected") from None
        return device.model_dump(mode="json")

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

    @app.post("/api/tasks", status_code=201)
    async def create_task(payload: TaskPlanProposal, request: Request) -> dict[str, object]:
        """Persist a validated preview only; browser API cannot run or approve effects."""
        runtime = _runtime(request)
        if runtime.tasks is None or runtime.memory_host_id is None:
            raise HTTPException(status_code=503, detail="Task planning is unavailable")
        try:
            record = await runtime.tasks.submit(
                host_id=runtime.memory_host_id,
                proposal=payload,
            )
        except (ValueError, TaskStateError):
            raise HTTPException(status_code=422, detail="Task plan was rejected") from None
        return record.model_dump(mode="json")

    @app.get("/api/tasks")
    async def list_tasks(
        request: Request,
        status: TaskStatus | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> list[dict[str, object]]:
        runtime = _runtime(request)
        if runtime.task_store is None or runtime.memory_host_id is None:
            raise HTTPException(status_code=503, detail="Task planning is unavailable")
        records = await runtime.task_store.list_tasks(
            host_id=runtime.memory_host_id,
            status=status,
            limit=limit,
        )
        return [record.model_dump(mode="json") for record in records]

    @app.get("/api/tasks/{task_id}")
    async def get_task(
        request: Request,
        task_id: Annotated[str, Path(min_length=1, max_length=200)],
    ) -> dict[str, object]:
        runtime = _runtime(request)
        if runtime.task_store is None or runtime.memory_host_id is None:
            raise HTTPException(status_code=503, detail="Task planning is unavailable")
        record = await runtime.task_store.get_task(
            host_id=runtime.memory_host_id,
            task_id=task_id,
        )
        if record is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return record.model_dump(mode="json")

    @app.get("/api/tasks/{task_id}/events")
    async def get_task_events(
        request: Request,
        task_id: Annotated[str, Path(min_length=1, max_length=200)],
        limit: Annotated[int, Query(ge=1, le=2_000)] = 500,
    ) -> list[dict[str, object]]:
        runtime = _runtime(request)
        if runtime.task_store is None or runtime.memory_host_id is None:
            raise HTTPException(status_code=503, detail="Task planning is unavailable")
        try:
            events = await runtime.task_store.list_events(
                host_id=runtime.memory_host_id,
                task_id=task_id,
                limit=limit,
            )
        except TaskNotFoundError:
            raise HTTPException(status_code=404, detail="Task not found") from None
        return [event.model_dump(mode="json") for event in events]

    @app.post("/api/tasks/{task_id}/pause")
    async def pause_task(
        request: Request,
        task_id: Annotated[str, Path(min_length=1, max_length=200)],
    ) -> dict[str, object]:
        runtime = _runtime(request)
        if runtime.tasks is None or runtime.memory_host_id is None:
            raise HTTPException(status_code=503, detail="Task planning is unavailable")
        try:
            record = await runtime.tasks.pause(
                host_id=runtime.memory_host_id,
                task_id=task_id,
            )
        except TaskNotFoundError:
            raise HTTPException(status_code=404, detail="Task not found") from None
        return record.model_dump(mode="json")

    @app.post("/api/tasks/{task_id}/cancel")
    async def cancel_task(
        request: Request,
        task_id: Annotated[str, Path(min_length=1, max_length=200)],
    ) -> dict[str, object]:
        runtime = _runtime(request)
        if runtime.tasks is None or runtime.memory_host_id is None:
            raise HTTPException(status_code=503, detail="Task planning is unavailable")
        try:
            record = await runtime.tasks.cancel(
                host_id=runtime.memory_host_id,
                task_id=task_id,
            )
        except TaskNotFoundError:
            raise HTTPException(status_code=404, detail="Task not found") from None
        return record.model_dump(mode="json")

    @app.get("/api/audit")
    async def list_audit(request: Request, limit: int = 100) -> list[dict[str, object]]:
        records = await _runtime(request).store.list_audit_records(limit=limit)
        return [record.model_dump(mode="json") for record in records]

    return app


def _runtime(request: Request) -> RuntimeComponents:
    return request.app.state.runtime  # type: ignore[no-any-return]


def _remote_identity(request: Request) -> RemoteIdentityService:
    service = _runtime(request).remote_identity
    if service is None:
        raise HTTPException(status_code=503, detail="Remote identity is unavailable")
    return service


def _remote_context(request: Request) -> RemoteIdentityContext:
    context = getattr(request.state, "remote_identity", None)
    if not isinstance(context, RemoteIdentityContext):
        raise HTTPException(status_code=401, detail="Remote authentication failed")
    return context


def _pwa_hub(request: Request) -> PWAEventHub:
    hub = getattr(request.app.state, "pwa_hub", None)
    if not isinstance(hub, PWAEventHub):
        raise HTTPException(status_code=503, detail="PWA transport is unavailable")
    return hub


def _require_remote_host(runtime: RuntimeComponents, context: RemoteIdentityContext) -> None:
    if runtime.memory_host_id is None or runtime.memory_host_id != context.host_id:
        raise HTTPException(status_code=403, detail="Remote host denied")


def _require_pwa_topic_scopes(
    context: RemoteIdentityContext,
    topics: tuple[PWAEventTopic, ...],
) -> None:
    required = {
        PWAEventTopic.CHAT: RemoteScope.CLIENT_CHAT,
        PWAEventTopic.TASKS: RemoteScope.CLIENT_TASKS_READ,
        PWAEventTopic.DEVICE: RemoteScope.CLIENT_STATUS_READ,
    }
    if any(required[topic] not in context.scopes for topic in topics):
        raise HTTPException(status_code=403, detail="Remote scope denied")


def _pwa_transport_http_error(error: PWATransportError) -> HTTPException:
    if error.code in {"subscription_limit", "transport_capacity"}:
        return HTTPException(status_code=429, detail="PWA transport capacity exceeded")
    if error.code == "cursor_expired":
        return HTTPException(status_code=409, detail="PWA event cursor expired")
    if error.code in {"event_too_large", "request_result_too_large"}:
        return HTTPException(status_code=413, detail="PWA transport payload too large")
    if error.code == "topic_not_subscribed":
        return HTTPException(status_code=403, detail="PWA topic denied")
    return HTTPException(status_code=404, detail="PWA subscription unavailable")


def _remote_scope_for_request(method: str, path: str) -> tuple[bool, RemoteScope | None]:
    if (method, path) in {
        ("POST", "/api/v1/enrollments/complete"),
        ("POST", "/api/v1/sessions"),
        ("POST", "/api/v1/browser/sessions"),
    }:
        return True, None
    if method == "DELETE" and path.startswith("/api/v1/client/subscriptions/"):
        return False, RemoteScope.EVENTS_READ
    return False, {
        "/api/v1/identity": RemoteScope.IDENTITY_READ,
        "/api/v1/events": RemoteScope.EVENTS_READ,
        "/api/v1/sessions/current": RemoteScope.SESSION_REVOKE,
        "/api/v1/device/key": RemoteScope.KEY_ROTATE,
        "/api/v1/topology/negotiate": RemoteScope.TOPOLOGY_NEGOTIATE,
        "/api/v1/client/status": RemoteScope.CLIENT_STATUS_READ,
        "/api/v1/client/tasks": RemoteScope.CLIENT_TASKS_READ,
        "/api/v1/client/subscriptions": RemoteScope.EVENTS_READ,
        "/api/v1/client/events": RemoteScope.EVENTS_READ,
        "/api/v1/client/chat": RemoteScope.CLIENT_CHAT,
    }.get(path)


def _topology(request: Request) -> TopologyNegotiator:
    topology = _runtime(request).topology
    if topology is None:
        raise HTTPException(status_code=503, detail="Topology protocol unavailable")
    return topology


def _validate_remote_request_shape(request: Request) -> None:
    raw_headers = request.scope.get("headers", ())
    raw_path = request.scope.get("raw_path", b"")
    raw_query = request.scope.get("query_string", b"")
    if not isinstance(raw_headers, (list, tuple)) or len(raw_headers) > _MAX_REMOTE_HEADERS:
        raise ValueError("remote header count exceeded")
    if not isinstance(raw_query, bytes) or len(raw_query) > _MAX_REMOTE_QUERY_BYTES:
        raise ValueError("remote query size exceeded")
    if not isinstance(raw_path, bytes) or len(raw_path) > _MAX_REMOTE_PATH_BYTES:
        raise ValueError("remote path size exceeded")
    total = 0
    for item in raw_headers:
        if (
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], bytes)
            or not isinstance(item[1], bytes)
        ):
            raise ValueError("invalid ASGI header")
        total += len(item[0]) + len(item[1])
    if total > _MAX_REMOTE_HEADER_BYTES:
        raise ValueError("remote header size exceeded")
    content_lengths = _header_values(request, "content-length")
    if len(content_lengths) > 1:
        raise ValueError("duplicate content length")
    if content_lengths:
        try:
            content_length = int(content_lengths[0])
        except ValueError as exc:
            raise ValueError("invalid content length") from exc
        if content_length < 0:
            raise ValueError("invalid content length")
        if content_length > _MAX_REMOTE_BODY_BYTES:
            raise RemoteBodyTooLargeError


class RemoteBodyTooLargeError(ValueError):
    pass


async def _read_bounded_remote_body(request: Request) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > _MAX_REMOTE_BODY_BYTES:
            raise RemoteBodyTooLargeError
        chunks.append(chunk)
    body = b"".join(chunks)
    request._body = body
    return body


def _header_values(request: Request, name: str) -> tuple[str, ...]:
    encoded = name.encode("ascii")
    raw_headers = request.scope.get("headers", ())
    if not isinstance(raw_headers, (list, tuple)):
        raise ValueError("invalid ASGI headers")
    return tuple(
        item[1].decode("ascii")
        for item in raw_headers
        if isinstance(item, tuple) and len(item) == 2 and item[0].lower() == encoded
    )


def _browser_cookie_token(request: Request) -> str | None:
    cookie_values = _header_values(request, "cookie")
    if not cookie_values:
        return None
    if len(cookie_values) != 1:
        raise ValueError("duplicate cookie headers")
    occurrences = sum(
        1
        for part in cookie_values[0].split(";")
        if part.strip().partition("=")[0] == _BROWSER_SESSION_COOKIE
    )
    if occurrences == 0:
        return None
    if occurrences != 1:
        raise ValueError("duplicate browser session cookie")
    parsed = SimpleCookie()
    try:
        parsed.load(cookie_values[0])
    except CookieError as exc:
        raise ValueError("invalid browser session cookie") from exc
    morsel = parsed.get(_BROWSER_SESSION_COOKIE)
    if morsel is None or _REMOTE_TOKEN_PATTERN.fullmatch(morsel.value) is None:
        raise ValueError("invalid browser session cookie")
    return morsel.value


def _csrf_token(request: Request) -> str | None:
    values = _header_values(request, _CSRF_HEADER)
    return values[0] if len(values) == 1 else None


def _client_key(request: Request) -> str:
    client = request.client
    return "unknown" if client is None else client.host


def _identity_rate_key(request: Request, browser_token: str | None) -> str:
    if browser_token is not None:
        return hashlib.sha256(browser_token.encode("ascii")).hexdigest()[:24]
    values = _header_values(request, "x-jarvis-device")
    return values[0][:200] if len(values) == 1 else "anonymous"


def _validate_preflight(request: Request) -> None:
    methods = _header_values(request, "access-control-request-method")
    if len(methods) != 1 or methods[0] not in {"GET", "POST", "DELETE"}:
        raise ValueError("preflight method denied")
    requested_headers = _header_values(request, "access-control-request-headers")
    if len(requested_headers) > 1:
        raise ValueError("duplicate preflight headers")
    if requested_headers:
        allowed = {
            "content-type",
            _CSRF_HEADER,
            "x-jarvis-audience",
            "x-jarvis-date",
            "x-jarvis-device",
            "x-jarvis-key-version",
            "x-jarvis-nonce",
            "x-jarvis-signature",
        }
        supplied = {
            item.strip().lower() for item in requested_headers[0].split(",") if item.strip()
        }
        if not supplied.issubset(allowed):
            raise ValueError("preflight header denied")


def _apply_cors_headers(response: Response, origin: str, *, preflight: bool = False) -> None:
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Vary"] = "Origin"
    if preflight:
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE"
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, X-Jarvis-CSRF, X-Jarvis-Audience, X-Jarvis-Date, "
            "X-Jarvis-Device, X-Jarvis-Key-Version, X-Jarvis-Nonce, X-Jarvis-Signature"
        )
        response.headers["Access-Control-Max-Age"] = "600"


def _apply_security_headers(response: Response, *, api_only: bool) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Strict-Transport-Security"] = "max-age=31536000"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        if api_only
        else _legacy_page_csp()
    )


def _apply_pwa_security_headers(response: Response, *, path: str) -> None:
    response.headers["Cache-Control"] = (
        "no-cache" if path in {"/app", "/app/", "/app/sw.js"} else "public, max-age=3600"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Strict-Transport-Security"] = "max-age=31536000"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
        "connect-src 'self'; manifest-src 'self'; worker-src 'self'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )


def _legacy_page_csp() -> str:
    hashes: list[str] = []
    for tag in ("style", "script"):
        match = re.search(rf"<{tag}>(.*?)</{tag}>", _CHAT_HTML, flags=re.DOTALL)
        if match is None:
            raise RuntimeError(f"legacy page is missing inline {tag}")
        digest = base64.b64encode(hashlib.sha256(match.group(1).encode()).digest()).decode()
        hashes.append(f"'sha256-{digest}'")
    return (
        "default-src 'none'; "
        f"style-src {hashes[0]}; script-src {hashes[1]}; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )


def _bearer_token(request: Request) -> str:
    try:
        authorization = _single_header(request, "authorization")
    except ValueError:
        raise RemoteAuthenticationError("missing_session_token") from None
    if not authorization.startswith("Bearer "):
        raise RemoteAuthenticationError("invalid_token_type")
    token = authorization.removeprefix("Bearer ")
    if _REMOTE_TOKEN_PATTERN.fullmatch(token) is None:
        raise RemoteAuthenticationError("invalid_session")
    return token


def _signed_remote_request(
    request: Request,
    *,
    body: bytes,
    session_token: str | None,
) -> tuple[SignedRequest, str]:
    if len(body) > _MAX_REMOTE_BODY_BYTES:
        raise ValueError("remote request body exceeds 1 MiB")
    headers = {name: _single_header(request, name) for name in _REMOTE_HEADER_NAMES}
    try:
        timestamp = datetime.fromisoformat(headers["x-jarvis-date"].replace("Z", "+00:00"))
        key_version = int(headers["x-jarvis-key-version"])
        raw_path = request.scope.get("raw_path", request.url.path.encode("ascii"))
        raw_query = request.scope.get("query_string", b"")
        if not isinstance(raw_path, bytes) or not isinstance(raw_query, bytes):
            raise ValueError("invalid ASGI raw request target")
        signed = SignedRequest(
            method=request.method,
            authority=_single_header(request, "host"),
            path=raw_path.decode("ascii"),
            query=raw_query.decode("ascii"),
            body=body,
            device_id=headers["x-jarvis-device"],
            key_version=key_version,
            audience=headers["x-jarvis-audience"],
            timestamp=timestamp,
            nonce=headers["x-jarvis-nonce"],
            session_token=session_token,
        )
    except (OverflowError, TypeError) as exc:
        raise ValueError("invalid remote authentication headers") from exc
    return signed, headers["x-jarvis-signature"]


def _single_header(request: Request, name: str) -> str:
    encoded_name = name.encode("ascii")
    raw_headers: object = request.scope.get("headers", ())
    if not isinstance(raw_headers, (list, tuple)):
        raise ValueError("invalid ASGI headers")
    values: list[bytes] = []
    for item in raw_headers:
        if (
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], bytes)
            or not isinstance(item[1], bytes)
        ):
            raise ValueError("invalid ASGI header")
        if item[0].lower() == encoded_name:
            values.append(item[1])
    if len(values) != 1:
        raise ValueError(f"exactly one {name} header is required")
    return values[0].decode("ascii")


def _remote_error(status_code: int, detail: str, *, authenticate: bool = False) -> JSONResponse:
    response = JSONResponse(status_code=status_code, content={"detail": detail})
    _apply_security_headers(response, api_only=True)
    if authenticate:
        response.headers["WWW-Authenticate"] = 'Bearer realm="jarvis-api"'
    return response


def _remote_rate_error(retry_after_seconds: int) -> JSONResponse:
    response = _remote_error(429, "Remote request rate exceeded")
    response.headers["Retry-After"] = str(retry_after_seconds)
    return response


def _assistant_request(payload: ChatInput | PWAChatInput) -> AssistantRequest:
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
