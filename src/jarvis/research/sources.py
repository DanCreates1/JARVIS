"""Explicit public-source selection through the existing bounded search port."""

from __future__ import annotations

import re
from collections.abc import Sequence
from urllib.parse import urlsplit

from jarvis.research.adapters import ResearchSearchError
from jarvis.research.contracts import SearchProvider
from jarvis.research.models import ResearchErrorCode, SearchRequest, SearchResult
from jarvis.research.security import PublicResearchUrlPolicy, ResearchUrlDenied

_URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


class ExplicitSourceSearchProvider:
    """Use deliberate query URLs, otherwise retain configured public discovery.

    This selects candidates only. The pinned fetcher still validates DNS, redirects,
    media, deadlines and byte bounds at every network hop. No source-body URLs are followed.
    Place PrivacyRoutedSearchProvider outside this adapter.
    """

    def __init__(self, delegate: SearchProvider) -> None:
        self._delegate = delegate
        self._policy = PublicResearchUrlPolicy()

    async def search(self, request: SearchRequest) -> Sequence[SearchResult]:
        candidates = _URL.findall(request.query)
        if not candidates:
            if re.search(r"https?://", request.query, re.IGNORECASE):
                raise ResearchSearchError(
                    ResearchErrorCode.INVALID_URL, "explicit source URL empty"
                )
            return await self._delegate.search(request)
        results: dict[str, SearchResult] = {}
        for candidate in candidates:
            # Permit ordinary prose/Markdown delimiters, never repair credentials or schemes.
            candidate = candidate.rstrip(".,;!?)")
            try:
                if urlsplit(candidate).query:
                    raise ResearchSearchError(
                        ResearchErrorCode.PRIVACY_DENIED,
                        "explicit source query parameters are not permitted",
                    )
                url, host, _ = self._policy.validate_syntax(
                    candidate, allowed_domains=request.allowed_domains
                )
            except ResearchUrlDenied as exc:
                raise ResearchSearchError(exc.code, "explicit source URL denied") from exc
            except ValueError as exc:
                raise ResearchSearchError(
                    ResearchErrorCode.INVALID_URL, "explicit source URL malformed"
                ) from exc
            results[url] = SearchResult(url=url, title=host, publisher=host)
            if len(results) > 4:
                raise ResearchSearchError(
                    ResearchErrorCode.PROTOCOL_ERROR, "at most four explicit source URLs allowed"
                )
        return tuple(results.values())[: request.limit]

    async def close(self) -> None:
        await self._delegate.close()
