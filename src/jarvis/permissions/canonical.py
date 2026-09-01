"""Deterministic JSON normalization and fingerprints for privileged actions."""

from __future__ import annotations

import json
import math
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from typing import TypeAlias

from pydantic import BaseModel

CanonicalScalar: TypeAlias = str | int | float | bool | None
CanonicalValue: TypeAlias = CanonicalScalar | list["CanonicalValue"] | dict[str, "CanonicalValue"]


def normalize_unicode(value: str) -> str:
    """Return Unicode NFC so visually equivalent action data hashes identically."""
    return unicodedata.normalize("NFC", value)


def canonicalize(value: object) -> CanonicalValue:
    """Convert supported values to a normalized, finite JSON tree.

    Approval fingerprints must never depend on insertion order, Unicode composition,
    locale, model serialization quirks, or non-standard JSON floats.
    """
    if isinstance(value, BaseModel):
        return canonicalize(value.model_dump(mode="json"))
    if isinstance(value, Enum):
        return canonicalize(value.value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("canonical datetimes must be timezone-aware")
        return value.astimezone(UTC).isoformat(timespec="microseconds")
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical JSON does not permit non-finite numbers")
        return 0.0 if value == 0 else value
    if isinstance(value, str):
        return normalize_unicode(value)
    if isinstance(value, Mapping):
        normalized: dict[str, CanonicalValue] = {}
        for raw_key, raw_value in value.items():
            if not isinstance(raw_key, str):
                raise TypeError("canonical JSON object keys must be strings")
            key = normalize_unicode(raw_key)
            if key in normalized:
                raise ValueError("Unicode normalization produced a duplicate object key")
            normalized[key] = canonicalize(raw_value)
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | memoryview):
        return [canonicalize(item) for item in value]
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_json(value: object) -> str:
    """Serialize a value using the single representation used for authorization."""
    return json.dumps(
        canonicalize(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_json_bytes(value: object) -> bytes:
    return canonical_json(value).encode("utf-8")


def sha256_fingerprint(value: object) -> str:
    """Return a versioned SHA-256 fingerprint of canonical JSON."""
    return "sha256:" + sha256(canonical_json_bytes(value)).hexdigest()
