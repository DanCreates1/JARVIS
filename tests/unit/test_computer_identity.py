from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from jarvis.computer.identity import IdentityKeyStore, LocalActorFactory
from jarvis.computer.windows import WindowsIdentity
from jarvis.permissions import InteractionInterface


class FakeIdentityProbe:
    def __init__(self, key: bytes) -> None:
        self.key = key

    def probe(self, *, require_non_elevated: bool = True) -> WindowsIdentity:
        assert require_non_elevated
        suffix = self.key.hex()[:8]
        return WindowsIdentity(
            is_elevated=False,
            user_id_hash=f"user-{suffix}",
            device_id_hash=f"device-{suffix}",
        )


def test_identity_key_store_creates_once_and_rejects_corruption(tmp_path: Path) -> None:
    store = IdentityKeyStore(tmp_path)
    first = store.load_or_create()
    second = store.load_or_create()

    assert first == second
    assert len(first) == 32
    assert store.path.read_bytes() == first
    assert list(tmp_path.glob(".computer-identity-*.tmp")) == []

    store.path.write_bytes(b"short")
    with pytest.raises(ValueError, match="invalid size"):
        store.load_or_create()


def test_identity_key_store_rejects_non_file_target(tmp_path: Path) -> None:
    store = IdentityKeyStore(tmp_path)
    store.path.mkdir(parents=True)
    with pytest.raises(ValueError, match="regular"):
        store.load_or_create()


def test_local_actor_is_stable_session_bound_and_ignores_request_metadata(tmp_path: Path) -> None:
    now = datetime(2026, 8, 22, 18, 0, tzinfo=UTC)
    store = IdentityKeyStore(tmp_path)
    first_factory = LocalActorFactory(
        store,
        session_probe=lambda: 7,
        identity_probe_factory=FakeIdentityProbe,
        now=lambda: now,
    )
    actor = first_factory.create(
        interface=InteractionInterface.LOCAL_CLI,
        capabilities=("computer.file.move", "computer.file.move", "computer.app.launch"),
    )
    repeated = first_factory.create(
        interface=InteractionInterface.LOCAL_CLI,
        capabilities=("computer.app.launch", "computer.file.move"),
    )
    other_session = LocalActorFactory(
        store,
        session_probe=lambda: 8,
        identity_probe_factory=FakeIdentityProbe,
        now=lambda: now,
    ).create(
        interface=InteractionInterface.LOCAL_CLI,
        capabilities=actor.capabilities,
    )

    assert repeated == actor
    assert actor.session_id != other_session.session_id
    assert actor.host_id == other_session.host_id
    assert actor.device_id == other_session.device_id
    assert actor.capabilities == ("computer.app.launch", "computer.file.move")


def test_local_actor_rejects_invalid_session_and_clock(tmp_path: Path) -> None:
    store = IdentityKeyStore(tmp_path)
    invalid_session = LocalActorFactory(
        store,
        session_probe=lambda: -1,
        identity_probe_factory=FakeIdentityProbe,
    )
    with pytest.raises(ValueError, match="session ID"):
        invalid_session.create(interface=InteractionInterface.LOCAL_CLI, capabilities=())

    naive_clock = LocalActorFactory(
        store,
        session_probe=lambda: 1,
        identity_probe_factory=FakeIdentityProbe,
        now=lambda: datetime(2026, 8, 22, tzinfo=UTC).replace(tzinfo=None),
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        naive_clock.create(interface=InteractionInterface.LOCAL_CLI, capabilities=())
