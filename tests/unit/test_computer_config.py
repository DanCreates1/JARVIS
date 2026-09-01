from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from jarvis.computer.config import (
    AppGroupPolicy,
    ApplicationPolicy,
    BrowserTargetPolicy,
    ComputerAccessConfigStore,
    ComputerAccessPolicy,
)
from jarvis.core import PermissionLevel


def test_policy_store_is_disabled_and_non_mutating_by_default(tmp_path: Path) -> None:
    store = ComputerAccessConfigStore(tmp_path)

    policy = store.load()

    assert policy.enabled is False
    assert policy.maximum_permission_level is PermissionLevel.LEVEL_2
    assert policy.controlled_root == tmp_path / "controlled-files"
    assert not store.path.exists()


def test_policy_store_round_trips_atomically_under_data_dir(tmp_path: Path) -> None:
    executable = tmp_path / "fixture.exe"
    executable.write_bytes(b"fixture")
    policy = ComputerAccessPolicy(
        enabled=True,
        controlled_root=tmp_path / "controlled-files",
        applications={
            "fixture": ApplicationPolicy(
                executable=executable,
                sha256="a" * 64,
                arguments=("--fixed",),
            )
        },
        app_groups={"main": AppGroupPolicy(applications=("fixture",))},
        browser_targets={"docs": BrowserTargetPolicy(url="https://learn.microsoft.com/windows/")},
        browser_application="fixture",
        hands_free_app_group="main",
    )
    store = ComputerAccessConfigStore(tmp_path)

    store.save(policy)

    assert store.load() == policy
    assert store.path.is_file()
    assert list(tmp_path.glob(".computer-access-*.tmp")) == []


@pytest.mark.parametrize(
    "changes,match",
    [
        ({"controlled_root": Path("relative")}, "absolute"),
        ({"maximum_permission_level": PermissionLevel.LEVEL_3}, "Levels 3 or 4"),
        (
            {"app_groups": {"main": AppGroupPolicy(applications=("missing",))}},
            "unknown IDs",
        ),
        ({"hands_free_app_group": "missing"}, "not configured"),
        (
            {"browser_targets": {"docs": BrowserTargetPolicy(url="https://example.com/")}},
            "fixed browser application",
        ),
    ],
)
def test_policy_rejects_unsafe_scope(
    changes: dict[str, object], match: str, tmp_path: Path
) -> None:
    values: dict[str, object] = {"controlled_root": tmp_path / "controlled-files"}
    values.update(changes)
    with pytest.raises(ValidationError, match=match):
        ComputerAccessPolicy(**values)


def test_store_rejects_root_outside_owned_data_dir(tmp_path: Path) -> None:
    store = ComputerAccessConfigStore(tmp_path / "data")
    policy = ComputerAccessPolicy(controlled_root=tmp_path / "outside")

    with pytest.raises(ValueError, match="dedicated child"):
        store.save(policy)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/",
        "https://user:password@example.com/",
        "https://localhost/",
        "https://127.0.0.1/",
        "https://10.0.0.1/",
    ],
)
def test_browser_targets_reject_non_public_or_credentialed_urls(url: str) -> None:
    with pytest.raises(ValidationError):
        BrowserTargetPolicy(url=url)


def test_application_policy_requires_absolute_exe_digest_and_fixed_arguments(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValidationError, match="absolute"):
        ApplicationPolicy(executable=Path("tool.exe"), sha256="a" * 64)
    with pytest.raises(ValidationError, match=r"Windows \.exe"):
        ApplicationPolicy(executable=tmp_path / "tool.cmd", sha256="a" * 64)
    with pytest.raises(ValidationError):
        ApplicationPolicy(executable=tmp_path / "tool.exe", sha256="not-a-digest")
    with pytest.raises(ValidationError, match="without NUL"):
        ApplicationPolicy(
            executable=tmp_path / "tool.exe",
            sha256="a" * 64,
            arguments=("bad\x00argument",),
        )


def test_store_rejects_invalid_oversized_and_non_file_policy(tmp_path: Path) -> None:
    store = ComputerAccessConfigStore(tmp_path)
    store.path.write_text("not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid"):
        store.load()

    store.path.write_bytes(b"x" * 1_000_001)
    with pytest.raises(ValueError, match="size limit"):
        store.load()

    store.path.unlink()
    store.path.mkdir()
    with pytest.raises(ValueError, match="regular"):
        store.load()
