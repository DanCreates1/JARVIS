"""Deterministic Phase 4 extraction. Output is always an uncommitted candidate."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence

from jarvis.core.models import SensitivityClass
from jarvis.memory.models import MemoryCategory, MemoryExtraction

_MAX_EXTRACTIONS = 8
_MAX_INPUT_CHARS = 10_000
_SPACE = re.compile(r"\s+")
_SAFE_KEY = re.compile(r"[^a-z0-9]+")

_RULES: Sequence[tuple[re.Pattern[str], MemoryCategory, str, str]] = (
    (
        re.compile(r"\bmy name is\s+(?P<value>[^.!?]{1,200})", re.IGNORECASE),
        MemoryCategory.PROFILE,
        "profile.name",
        "explicit_profile_fact",
    ),
    (
        re.compile(
            r"\bi prefer\s+(?P<value>[^.!?]{1,500}?)"
            r"(?:\s+(?:for|when)\s+(?P<context>[^.!?]{1,200}))?(?:[.!?]|$)",
            re.IGNORECASE,
        ),
        MemoryCategory.PROFILE,
        "preference",
        "explicit_preference",
    ),
    (
        re.compile(r"\b(?:remind me to|i need to)\s+(?P<value>[^.!?]{1,1000})", re.IGNORECASE),
        MemoryCategory.TASK,
        "task",
        "explicit_task",
    ),
    (
        re.compile(r"\bremember that\s+(?P<value>[^.!?]{1,2000})", re.IGNORECASE),
        MemoryCategory.SEMANTIC,
        "semantic",
        "explicit_semantic_note",
    ),
)


def extract_memory_candidates(text: str) -> tuple[MemoryExtraction, ...]:
    """Extract bounded explicit statements without assigning truth or authority."""
    normalized = _SPACE.sub(" ", text.strip())
    if not normalized or len(normalized) > _MAX_INPUT_CHARS:
        return ()

    results: list[MemoryExtraction] = []
    seen: set[tuple[MemoryCategory, str, str]] = set()
    for pattern, category, key_prefix, reason_code in _RULES:
        for match in pattern.finditer(normalized):
            value = _SPACE.sub(" ", match.group("value").strip(" ,;:-"))
            if not value:
                continue
            context = match.groupdict().get("context")
            if key_prefix == "preference":
                key = f"preference.{_slug(context or 'general')}"
                content = f"Prefers {value}"
            elif key_prefix in {"task", "semantic"}:
                digest = hashlib.sha256(value.casefold().encode("utf-8")).hexdigest()[:16]
                key = f"{key_prefix}.{digest}"
                content = value
            else:
                key = key_prefix
                content = value
            dedupe_key = (category, key, content.casefold())
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            results.append(
                MemoryExtraction(
                    category=category,
                    key=key,
                    content=content,
                    confidence=0.95 if category is MemoryCategory.PROFILE else 0.85,
                    sensitivity=SensitivityClass.PRIVATE,
                    structured={"extractor": "deterministic-explicit-v1"},
                    reason_code=reason_code,
                )
            )
            if len(results) >= _MAX_EXTRACTIONS:
                return tuple(results)
    return tuple(results)


def _slug(value: str) -> str:
    slug = _SAFE_KEY.sub(".", value.casefold()).strip(".")
    return slug[:100] or "general"
