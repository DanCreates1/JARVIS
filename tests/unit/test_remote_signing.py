from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from jarvis.remote import SignedRequest, canonical_request
from jarvis.remote.signing import decode_base64url, encode_base64url


def _request() -> SignedRequest:
    return SignedRequest(
        method="post",
        authority="LOCALHOST:8765",
        path="/api/v1/identity",
        query="cursor=1%202&kind=identity",
        body=b'{"safe":true}',
        device_id="device:test",
        key_version=1,
        audience="jarvis-api",
        timestamp=datetime(2026, 9, 9, 12, tzinfo=UTC),
        nonce="A" * 22,
        session_token="B" * 43,
    )


def test_canonical_request_is_stable_and_binds_every_security_component() -> None:
    request = _request()
    baseline = canonical_request(request)
    assert baseline == canonical_request(request)
    assert b"jarvis-http-signature-v1" in baseline
    variants = (
        replace(request, method="GET"),
        replace(request, authority="localhost:9999"),
        replace(request, path="/api/v1/events"),
        replace(request, query="cursor=2"),
        replace(request, body=b"{}"),
        replace(request, device_id="device:other"),
        replace(request, key_version=2),
        replace(request, timestamp=datetime(2026, 9, 9, 12, 0, 1, tzinfo=UTC)),
        replace(request, nonce="C" * 22),
        replace(request, session_token="D" * 43),
    )
    assert len({baseline, *(canonical_request(item) for item in variants)}) == len(variants) + 1


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("method", "G ET"),
        ("authority", "user@localhost"),
        ("authority", "localhost:99999"),
        ("path", "relative"),
        ("query", "bad\nquery"),
        ("audience", "other-api"),
        ("nonce", "short"),
        ("timestamp", datetime(2026, 9, 9, 12, tzinfo=UTC).replace(tzinfo=None)),
    ),
)
def test_canonical_request_rejects_ambiguous_components(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        canonical_request(replace(_request(), **{field: value}))


def test_base64url_codec_requires_canonical_unpadded_encoding() -> None:
    encoded = encode_base64url(bytes(range(32)))
    assert decode_base64url(encoded, expected_bytes=32) == bytes(range(32))
    for invalid in (encoded + "=", "not+url", "", "A"):
        with pytest.raises(ValueError):
            decode_base64url(invalid, expected_bytes=32)
