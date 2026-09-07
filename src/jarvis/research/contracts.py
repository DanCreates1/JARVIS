"""Adapter ports for Phase 5 research acquisition and parsing."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from jarvis.research.models import (
    FetchedDocument,
    FetchRequest,
    ParsedDocument,
    ResearchSynthesisDraft,
    ResearchSynthesisRequest,
    SearchRequest,
    SearchResult,
)


class SearchProvider(Protocol):
    async def search(self, request: SearchRequest) -> Sequence[SearchResult]: ...

    async def close(self) -> None: ...


class DocumentFetcher(Protocol):
    async def fetch(self, request: FetchRequest) -> FetchedDocument: ...

    async def close(self) -> None: ...


class DocumentParser(Protocol):
    def parse(self, document: FetchedDocument) -> ParsedDocument: ...


class ResearchSynthesizer(Protocol):
    async def synthesize(self, request: ResearchSynthesisRequest) -> ResearchSynthesisDraft: ...

    async def close(self) -> None: ...
