"""Strict host-owned configuration for controlled computer actions."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator

from jarvis.core import PermissionLevel

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_MAX_POLICY_BYTES = 1_000_000


class ComputerConfigModel(BaseModel):
    """Strict immutable value loaded from the trusted policy file."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ApplicationPolicy(ComputerConfigModel):
    """One enrolled executable with a host-fixed argument vector and digest."""

    executable: Path
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    arguments: Annotated[tuple[str, ...], Field(max_length=16)] = ()
    startup_timeout_seconds: float = Field(default=5.0, gt=0, le=30)

    @field_validator("executable")
    @classmethod
    def normalize_executable(cls, value: Path) -> Path:
        return value.expanduser()

    @model_validator(mode="after")
    def validate_executable(self) -> Self:
        if not self.executable.is_absolute():
            raise ValueError("application executable must be an absolute path")
        if self.executable.suffix.casefold() != ".exe":
            raise ValueError("application executable must be a Windows .exe file")
        if any(
            not argument or len(argument) > 512 or "\x00" in argument for argument in self.arguments
        ):
            raise ValueError("fixed application arguments must be 1-512 characters without NUL")
        return self


class AppGroupPolicy(ComputerConfigModel):
    """Ordered fixed application IDs launched as one bounded group."""

    applications: Annotated[tuple[str, ...], Field(min_length=1, max_length=8)]

    @field_validator("applications")
    @classmethod
    def validate_application_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("application group contains duplicate IDs")
        if any(_IDENTIFIER.fullmatch(item) is None for item in value):
            raise ValueError("application group contains an invalid ID")
        return value


class BrowserTargetPolicy(ComputerConfigModel):
    """Exact preconfigured public HTTPS destination."""

    url: AnyHttpUrl

    @field_validator("url")
    @classmethod
    def validate_public_https(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.scheme != "https" or value.username is not None or value.password is not None:
            raise ValueError("browser targets require credential-free HTTPS URLs")
        host = value.host
        if host is None:
            raise ValueError("browser target requires a host")
        try:
            address = ipaddress.ip_address(host.strip("[]"))
        except ValueError:
            if host.casefold() == "localhost" or host.casefold().endswith(".localhost"):
                raise ValueError("browser targets cannot use localhost") from None
        else:
            if not address.is_global:
                raise ValueError("browser targets cannot use private or local IP addresses")
        return value


class PrinterPolicy(ComputerConfigModel):
    """Stable host-owned alias for an exact Windows printer name."""

    system_name: str = Field(min_length=1, max_length=256)
    allow_sensitive_content: Literal[False] = False

    @field_validator("system_name")
    @classmethod
    def reject_control_characters(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or any(ord(character) < 32 for character in normalized):
            raise ValueError("printer name contains control characters")
        return normalized


class HandsFreeMappingsPolicy(ComputerConfigModel):
    """Closed opt-ins for Phase 3 hands-free proposal mappings."""

    volume_step: bool = False
    media_play_pause: bool = False
    mute_toggle: bool = False
    media_track_navigation: bool = False
    cancel_session: bool = False


class ComputerAccessPolicy(ComputerConfigModel):
    """Deny-by-default Phase 3 action policy owned by the local host."""

    schema_version: Literal[1] = 1
    enabled: bool = False
    policy_version: str = Field(default="phase3-v1", pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$")
    maximum_permission_level: PermissionLevel = PermissionLevel.LEVEL_2
    controlled_root: Path
    applications: Annotated[dict[str, ApplicationPolicy], Field(max_length=32)] = Field(
        default_factory=dict
    )
    app_groups: Annotated[dict[str, AppGroupPolicy], Field(max_length=16)] = Field(
        default_factory=dict
    )
    browser_targets: Annotated[dict[str, BrowserTargetPolicy], Field(max_length=32)] = Field(
        default_factory=dict
    )
    browser_application: str | None = None
    printers: Annotated[dict[str, PrinterPolicy], Field(max_length=32)] = Field(
        default_factory=dict
    )
    hands_free_app_group: str | None = None
    hands_free_mappings: HandsFreeMappingsPolicy = Field(default_factory=HandsFreeMappingsPolicy)
    approval_ttl_seconds: int = Field(default=120, ge=15, le=600)
    grant_ttl_seconds: int = Field(default=60, ge=5, le=300)
    max_file_bytes: int = Field(default=100 * 1024 * 1024, ge=1, le=100 * 1024 * 1024)
    max_search_results: int = Field(default=50, ge=1, le=200)
    max_clipboard_bytes: int = Field(default=8 * 1024, ge=1, le=64 * 1024)
    max_print_bytes: int = Field(default=1 * 1024 * 1024, ge=1, le=10 * 1024 * 1024)
    max_print_copies: int = Field(default=5, ge=1, le=20)

    @field_validator("controlled_root")
    @classmethod
    def normalize_controlled_root(cls, value: Path) -> Path:
        return value.expanduser()

    @field_validator("applications", "app_groups", "browser_targets", "printers")
    @classmethod
    def validate_mapping_ids(cls, value: dict[str, object]) -> dict[str, object]:
        if any(_IDENTIFIER.fullmatch(item) is None for item in value):
            raise ValueError("computer policy mapping contains an invalid ID")
        return value

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        if not self.controlled_root.is_absolute():
            raise ValueError("controlled_root must be absolute")
        if self.maximum_permission_level > PermissionLevel.LEVEL_2:
            raise ValueError("Phase 3 does not enable permission Levels 3 or 4")
        known_apps = set(self.applications)
        for group_id, group in self.app_groups.items():
            unknown = set(group.applications).difference(known_apps)
            if unknown:
                raise ValueError(
                    f"application group '{group_id}' references unknown IDs: {sorted(unknown)!r}"
                )
        if self.browser_application is not None:
            if _IDENTIFIER.fullmatch(self.browser_application) is None:
                raise ValueError("browser application ID is invalid")
            if self.browser_application not in known_apps:
                raise ValueError("browser application is not configured")
        if self.browser_targets and self.browser_application is None:
            raise ValueError("browser targets require one fixed browser application")
        if self.hands_free_app_group is not None:
            if _IDENTIFIER.fullmatch(self.hands_free_app_group) is None:
                raise ValueError("hands-free app group ID is invalid")
            if self.hands_free_app_group not in self.app_groups:
                raise ValueError("hands-free app group is not configured")
        return self


class ComputerAccessConfigStore:
    """Load/save one bounded atomic policy file under private application data."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir.expanduser().resolve(strict=False)
        self._path = self._data_dir / "computer-access.json"

    @property
    def path(self) -> Path:
        return self._path

    @property
    def controlled_root(self) -> Path:
        return self._data_dir / "controlled-files"

    def default_policy(self) -> ComputerAccessPolicy:
        return ComputerAccessPolicy(enabled=False, controlled_root=self.controlled_root)

    def load(self) -> ComputerAccessPolicy:
        if not self._path.exists():
            return self.default_policy()
        if self._path.is_symlink() or not self._path.is_file():
            raise ValueError("computer access policy must be a regular non-link file")
        if self._path.stat().st_size > _MAX_POLICY_BYTES:
            raise ValueError("computer access policy exceeds the size limit")
        try:
            raw = self._path.read_text(encoding="utf-8")
            policy = ComputerAccessPolicy.model_validate_json(raw)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("computer access policy is invalid") from exc
        self._validate_owned_root(policy.controlled_root)
        return policy

    def save(self, policy: ComputerAccessPolicy) -> None:
        policy = ComputerAccessPolicy.model_validate(policy)
        self._validate_owned_root(policy.controlled_root)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        if self._path.exists() and (self._path.is_symlink() or not self._path.is_file()):
            raise ValueError("computer access policy target is not a regular file")
        payload = policy.model_dump_json(indent=2).encode("utf-8") + b"\n"
        if len(payload) > _MAX_POLICY_BYTES:
            raise ValueError("computer access policy exceeds the size limit")
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self._data_dir,
                prefix=".computer-access-",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_name = handle.name
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            assert temporary_name is not None
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, self._path)
            temporary_name = None
        finally:
            if temporary_name is not None:
                Path(temporary_name).unlink(missing_ok=True)

    def _validate_owned_root(self, controlled_root: Path) -> None:
        root = controlled_root.expanduser().resolve(strict=False)
        if root == self._data_dir or not root.is_relative_to(self._data_dir):
            raise ValueError("controlled root must be a dedicated child of the JARVIS data dir")
        if root.exists() and (root.is_symlink() or not root.is_dir()):
            raise ValueError("controlled root must be a regular non-link directory")
