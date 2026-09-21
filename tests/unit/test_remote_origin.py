from __future__ import annotations

from datetime import UTC, datetime

import pytest

from jarvis.remote import client_contract_metadata, normalize_server_origin


def test_server_origin_normalization_is_exact_and_https_only() -> None:
    assert normalize_server_origin("HTTPS://Jarvis.Tail.Example:443/") == (
        "https://jarvis.tail.example"
    )
    assert normalize_server_origin("https://[::1]:8443") == "https://[::1]:8443"
    assert (
        normalize_server_origin(
            "http://127.0.0.1:8765",
            allow_insecure_loopback=True,
        )
        == "http://127.0.0.1:8765"
    )


@pytest.mark.parametrize(
    "origin",
    (
        "http://jarvis.tail.example",
        "https://user@jarvis.tail.example",
        "https://jarvis.tail.example/api",
        "https://jarvis.tail.example?query=1",
        "https://jarvis.tail.example.",
        "https://bad_host.example",
        "https://jarvis.tail.example:0",
        " https://jarvis.tail.example",
    ),
)
def test_server_origin_rejects_ambiguous_or_unsafe_values(origin: str) -> None:
    with pytest.raises(ValueError):
        normalize_server_origin(origin)


def test_client_contract_metadata_is_stable_and_requires_aware_time() -> None:
    now = datetime(2026, 9, 21, 12, tzinfo=UTC)
    metadata = client_contract_metadata(server_time=now)
    assert metadata["protocol_version"] == "1"
    assert metadata["server_time"] == now
    assert metadata["capabilities"] == tuple(sorted(metadata["capabilities"]))
    assert metadata["compatibility"] == {
        "pwa_v1": True,
        "enrollment_v1": True,
        "enrollment_v2_authority_binding": True,
        "signed_request_v1": True,
    }
    with pytest.raises(ValueError):
        client_contract_metadata(server_time=now.replace(tzinfo=None))
