from __future__ import annotations

import hashlib
from dataclasses import replace

import httpx
import pytest
import respx

from jarvis.gestures.model_store import (
    HAND_MODEL,
    MODEL_MAX_BYTES,
    PALM_MODEL,
    VisionModelError,
    install_vision_models,
    model_paths,
    verify_model,
)


def _fixture_model(model, payload: bytes):  # type: ignore[no-untyped-def]
    return replace(model, sha256=hashlib.sha256(payload).hexdigest())


@respx.mock
def test_install_models_is_bounded_atomic_verified_and_idempotent(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    palm = _fixture_model(PALM_MODEL, b"palm-model")
    hand = _fixture_model(HAND_MODEL, b"hand-model")
    monkeypatch.setattr("jarvis.gestures.model_store.VISION_MODELS", (palm, hand))
    monkeypatch.setattr("jarvis.gestures.model_store.PALM_MODEL", palm)
    monkeypatch.setattr("jarvis.gestures.model_store.HAND_MODEL", hand)
    palm_route = respx.get(palm.url).mock(return_value=httpx.Response(200, content=b"palm-model"))
    hand_route = respx.get(hand.url).mock(return_value=httpx.Response(200, content=b"hand-model"))

    paths = install_vision_models(tmp_path)
    assert [path.read_bytes() for path in paths] == [b"palm-model", b"hand-model"]
    assert verify_model(paths[0], palm)
    assert verify_model(paths[1], hand)
    assert not list(tmp_path.glob("*.tmp"))

    install_vision_models(tmp_path)
    assert palm_route.call_count == 1
    assert hand_route.call_count == 1


@respx.mock
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503),
        httpx.Response(200, content=b"wrong"),
        httpx.Response(200, headers={"content-length": str(MODEL_MAX_BYTES + 1)}),
    ],
)
def test_install_model_failures_leave_no_partial_file(
    tmp_path, monkeypatch, response: httpx.Response
) -> None:  # type: ignore[no-untyped-def]
    palm = _fixture_model(PALM_MODEL, b"expected")
    monkeypatch.setattr("jarvis.gestures.model_store.VISION_MODELS", (palm,))
    monkeypatch.setattr("jarvis.gestures.model_store.PALM_MODEL", palm)
    monkeypatch.setattr("jarvis.gestures.model_store.HAND_MODEL", palm)
    respx.get(palm.url).mock(return_value=response)

    with pytest.raises(VisionModelError):
        install_vision_models(tmp_path)

    assert not list(tmp_path.iterdir())


def test_verify_model_rejects_missing_symlink_and_wrong_digest(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / PALM_MODEL.filename
    assert not verify_model(path, PALM_MODEL)
    path.write_bytes(b"wrong")
    assert not verify_model(path, PALM_MODEL)
    assert model_paths(tmp_path) == (
        tmp_path / PALM_MODEL.filename,
        tmp_path / HAND_MODEL.filename,
    )
