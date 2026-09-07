"""Non-executing extraction of bounded untrusted research documents."""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

from pydantic import ValidationError

from jarvis.research.fetch import ResearchFetchError
from jarvis.research.models import FetchedDocument, ParsedDocument, ResearchErrorCode

_MAX_EXTRACTED_CHARACTERS = 500_000
_MAX_WORKER_OUTPUT_BYTES = 1_100_000
_IGNORED_ELEMENTS = frozenset(
    {"script", "style", "template", "noscript", "svg", "nav", "aside", "footer", "header"}
)


class SandboxedDocumentParser:
    """Parse hostile documents in a short-lived isolated worker process."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 10,
        worker_path: str | Path | None = None,
    ) -> None:
        if not 0 < timeout_seconds <= 60:
            raise ValueError("parser timeout must be between 0 and 60 seconds")
        self._timeout_seconds = timeout_seconds
        self._worker_path = (
            Path(worker_path)
            if worker_path is not None
            else Path(__file__).with_name("_parser_worker.py")
        )

    def parse(self, document: FetchedDocument) -> ParsedDocument:
        if document.media_type not in {"text/html", "text/plain", "application/pdf"}:
            raise ResearchFetchError(
                ResearchErrorCode.UNSUPPORTED_CONTENT,
                f"research parser does not support {document.media_type}",
            )
        if not self._worker_path.is_file():
            raise ResearchFetchError(
                ResearchErrorCode.UNAVAILABLE,
                "research parser worker is unavailable",
            )
        request = json.dumps(
            {
                "source_url": document.final_url,
                "media_type": document.media_type,
                "encoding": document.encoding,
                "body_base64": base64.b64encode(document.body).decode("ascii"),
            },
            separators=(",", ":"),
        ).encode("utf-8")
        environment = {
            key: value
            for key in ("SystemRoot", "WINDIR", "PATH", "TEMP", "TMP")
            if (value := os.environ.get(key)) is not None
        }
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            with tempfile.TemporaryDirectory(prefix="jarvis-research-parser-") as working_dir:
                completed = subprocess.run(
                    [sys.executable, "-I", "-X", "utf8", str(self._worker_path)],
                    input=request,
                    capture_output=True,
                    cwd=working_dir,
                    env=environment,
                    check=False,
                    timeout=self._timeout_seconds,
                    creationflags=creation_flags,
                )
        except subprocess.TimeoutExpired as exc:
            raise ResearchFetchError(
                ResearchErrorCode.TIMEOUT,
                "research parser exceeded its isolated worker deadline",
            ) from exc
        except OSError as exc:
            raise ResearchFetchError(
                ResearchErrorCode.UNAVAILABLE,
                "research parser worker could not start",
            ) from exc
        if len(completed.stdout) > _MAX_WORKER_OUTPUT_BYTES:
            raise ResearchFetchError(
                ResearchErrorCode.RESPONSE_TOO_LARGE,
                "research parser worker output exceeded its limit",
            )
        try:
            payload = json.loads(completed.stdout.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ResearchFetchError(
                ResearchErrorCode.PROTOCOL_ERROR,
                "research parser worker returned malformed output",
            ) from exc
        if completed.returncode != 0 or not isinstance(payload, dict):
            code_value = payload.get("code") if isinstance(payload, dict) else None
            try:
                code = ResearchErrorCode(code_value) if isinstance(code_value, str) else None
            except ValueError:
                code = None
            raise ResearchFetchError(
                code or ResearchErrorCode.PROTOCOL_ERROR,
                "research parser rejected the untrusted document",
            )
        try:
            return ParsedDocument.model_validate(payload)
        except ValidationError as exc:
            raise ResearchFetchError(
                ResearchErrorCode.PROTOCOL_ERROR,
                "research parser worker returned an invalid document",
            ) from exc


class UntrustedDocumentParser:
    """Extract text and basic provenance metadata without executing source content."""

    def parse(self, document: FetchedDocument) -> ParsedDocument:
        if document.media_type == "text/plain":
            text = _decode(document)
            normalized = _normalize_text(text)
            if not normalized:
                raise ResearchFetchError(
                    ResearchErrorCode.PROTOCOL_ERROR,
                    "research document contains no extractable text",
                )
            return ParsedDocument(
                source_url=document.final_url,
                title=document.final_url,
                text=normalized[:_MAX_EXTRACTED_CHARACTERS],
            )
        if document.media_type == "text/html":
            parser = _ResearchHtmlParser()
            parser.feed(_decode(document))
            parser.close()
            text = _normalize_text(" ".join(parser.text_parts))
            if not text:
                raise ResearchFetchError(
                    ResearchErrorCode.PROTOCOL_ERROR,
                    "research document contains no extractable text",
                )
            return ParsedDocument(
                source_url=document.final_url,
                title=_normalize_text(parser.title) or document.final_url,
                text=text[:_MAX_EXTRACTED_CHARACTERS],
                publisher=_normalize_text(parser.publisher) or None,
                published_at=_parse_datetime(parser.published_at),
                language=parser.language,
            )
        if document.media_type == "application/pdf":
            raise ResearchFetchError(
                ResearchErrorCode.UNSUPPORTED_CONTENT,
                "PDF parsing is available only through the isolated parser",
            )
        raise ResearchFetchError(
            ResearchErrorCode.UNSUPPORTED_CONTENT,
            f"research parser does not support {document.media_type}",
        )


class _ResearchHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self._in_title = False
        self.text_parts: list[str] = []
        self.title = ""
        self.publisher = ""
        self.published_at = ""
        self.language: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        attributes: dict[str, str] = {name.lower(): value or "" for name, value in attrs}
        if normalized_tag == "html" and attributes.get("lang"):
            self.language = attributes["lang"][:35]
        if normalized_tag in _IGNORED_ELEMENTS:
            self._ignored_depth += 1
        if normalized_tag == "title" and self._ignored_depth == 0:
            self._in_title = True
        if normalized_tag == "meta":
            key = (attributes.get("property") or attributes.get("name") or "").lower()
            value = attributes.get("content", "")
            if key in {"og:site_name", "application-name", "publisher"} and not self.publisher:
                self.publisher = value[:500]
            if key in {"article:published_time", "date", "datepublished"} and not self.published_at:
                self.published_at = value[:100]

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag == "title":
            self._in_title = False
        if normalized_tag in _IGNORED_ELEMENTS and self._ignored_depth > 0:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_depth > 0:
            return
        if self._in_title:
            self.title += f" {data}"
        else:
            self.text_parts.append(data)


def _decode(document: FetchedDocument) -> str:
    try:
        return document.body.decode(document.encoding, errors="replace")
    except LookupError as exc:
        raise ResearchFetchError(
            ResearchErrorCode.UNSUPPORTED_CONTENT,
            "research document declared an unsupported character encoding",
        ) from exc


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    candidate = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed
