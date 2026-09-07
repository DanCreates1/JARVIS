import asyncio
from collections.abc import AsyncIterator, Sequence

import httpx
import pytest

from jarvis.research import (
    FetchLimits,
    FetchRequest,
    HttpDocumentFetcher,
    ResearchErrorCode,
    ResearchFetchError,
)


async def public_resolver(_hostname: str, _port: int) -> Sequence[str]:
    return ("93.184.216.34",)


async def fetch_with_handler(
    handler: httpx.AsyncBaseTransport | httpx.MockTransport,
    request: FetchRequest,
) -> object:
    async with (
        httpx.AsyncClient(transport=handler, follow_redirects=False) as client,
        HttpDocumentFetcher(client=client, resolver=public_resolver) as fetcher,
    ):
        return await fetcher.fetch(request)


async def test_fetch_pins_validated_ip_and_preserves_tls_host() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "example.com"
        assert request.extensions["sni_hostname"] == "example.com"
        assert "authorization" not in request.headers
        assert "cookie" not in request.headers
        return httpx.Response(
            200,
            headers={
                "Content-Type": "text/plain; charset=utf-8",
                "ETag": '"fixture-v1"',
                "Last-Modified": "Sat, 05 Sep 2026 12:00:00 GMT",
            },
            content=b"Public source text",
        )

    document = await fetch_with_handler(
        httpx.MockTransport(handler), FetchRequest(url="https://example.com/source")
    )
    assert document.final_url == "https://example.com/source"
    assert document.media_type == "text/plain"
    assert document.encoding == "utf-8"
    assert document.body == b"Public source text"
    assert document.etag == '"fixture-v1"'
    assert document.last_modified == "Sat, 05 Sep 2026 12:00:00 GMT"


async def test_relative_redirect_is_manually_revalidated() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/start":
            return httpx.Response(302, headers={"Location": "/final"})
        return httpx.Response(200, headers={"Content-Type": "text/plain"}, content=b"done")

    document = await fetch_with_handler(
        httpx.MockTransport(handler), FetchRequest(url="https://example.com/start")
    )
    assert paths == ["/start", "/final"]
    assert document.final_url == "https://example.com/final"
    assert document.redirect_chain == ("https://example.com/final",)


@pytest.mark.parametrize(
    ("location", "code"),
    [
        ("https://localhost/private", ResearchErrorCode.PRIVATE_NETWORK_DENIED),
        ("https://other.example/source", ResearchErrorCode.DOMAIN_DENIED),
    ],
)
async def test_redirect_cannot_escape_network_or_domain_policy(
    location: str, code: ResearchErrorCode
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": location})

    with pytest.raises(ResearchFetchError) as caught:
        await fetch_with_handler(
            httpx.MockTransport(handler), FetchRequest(url="https://example.com/start")
        )
    assert caught.value.code is code


async def test_redirect_limit_is_enforced() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "/again"})

    request = FetchRequest(url="https://example.com/start", limits=FetchLimits(max_redirects=1))
    with pytest.raises(ResearchFetchError) as caught:
        await fetch_with_handler(httpx.MockTransport(handler), request)
    assert caught.value.code is ResearchErrorCode.REDIRECT_LIMIT


async def test_content_length_prevents_oversized_download() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/plain", "Content-Length": "2048"},
            content=b"small transport fixture",
        )

    request = FetchRequest(url="https://example.com", limits=FetchLimits(max_bytes=1024))
    with pytest.raises(ResearchFetchError) as caught:
        await fetch_with_handler(httpx.MockTransport(handler), request)
    assert caught.value.code is ResearchErrorCode.RESPONSE_TOO_LARGE


class ChunkStream(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b"a" * 800
        yield b"b" * 800


async def test_streaming_byte_limit_stops_unknown_length_body() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": "text/plain"}, stream=ChunkStream())

    request = FetchRequest(url="https://example.com", limits=FetchLimits(max_bytes=1024))
    with pytest.raises(ResearchFetchError) as caught:
        await fetch_with_handler(httpx.MockTransport(handler), request)
    assert caught.value.code is ResearchErrorCode.RESPONSE_TOO_LARGE


@pytest.mark.parametrize(
    ("status_code", "code"),
    [
        (401, ResearchErrorCode.AUTHENTICATION_REQUIRED),
        (403, ResearchErrorCode.AUTHENTICATION_REQUIRED),
        (402, ResearchErrorCode.PAYWALL),
        (429, ResearchErrorCode.UNAVAILABLE),
        (503, ResearchErrorCode.UNAVAILABLE),
        (404, ResearchErrorCode.PROTOCOL_ERROR),
        (206, ResearchErrorCode.PROTOCOL_ERROR),
    ],
)
async def test_http_failures_are_structured(status_code: int, code: ResearchErrorCode) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code)

    with pytest.raises(ResearchFetchError) as caught:
        await fetch_with_handler(
            httpx.MockTransport(handler), FetchRequest(url="https://example.com")
        )
    assert caught.value.code is code


async def test_unsupported_or_missing_content_type_fails_closed() -> None:
    for headers in ({"Content-Type": "application/zip"}, {}):
        transport = httpx.MockTransport(
            lambda _request, headers=headers: httpx.Response(
                200, headers=headers, content=b"not accepted"
            )
        )
        with pytest.raises(ResearchFetchError) as caught:
            await fetch_with_handler(transport, FetchRequest(url="https://example.com"))
        assert caught.value.code is ResearchErrorCode.UNSUPPORTED_CONTENT


async def test_unsupported_character_encoding_fails_closed() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            headers={"Content-Type": "text/plain; charset=made-up-codec"},
            content=b"not accepted",
        )
    )
    with pytest.raises(ResearchFetchError) as caught:
        await fetch_with_handler(transport, FetchRequest(url="https://example.com"))
    assert caught.value.code is ResearchErrorCode.UNSUPPORTED_CONTENT


class SlowStream(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        await asyncio.sleep(1)
        yield b"late"


async def test_total_timeout_includes_response_stream() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": "text/plain"}, stream=SlowStream())

    request = FetchRequest(url="https://example.com", limits=FetchLimits(timeout_seconds=0.01))
    with pytest.raises(ResearchFetchError) as caught:
        await fetch_with_handler(httpx.MockTransport(handler), request)
    assert caught.value.code is ResearchErrorCode.TIMEOUT


async def test_cancellation_propagates_without_conversion() -> None:
    started = asyncio.Event()

    async def handler(_request: httpx.Request) -> httpx.Response:
        started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client,
        HttpDocumentFetcher(client=client, resolver=public_resolver) as fetcher,
    ):
        task = asyncio.create_task(fetcher.fetch(FetchRequest(url="https://example.com")))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_closed_fetcher_rejects_use() -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: httpx.Response(200)))
    fetcher = HttpDocumentFetcher(client=client)
    await fetcher.close()
    with pytest.raises(RuntimeError, match="closed"):
        await fetcher.fetch(FetchRequest(url="https://example.com"))
    await client.aclose()
