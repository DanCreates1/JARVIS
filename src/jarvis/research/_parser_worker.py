"""Isolated stdio worker for bounded hostile-document parsing."""

from __future__ import annotations

import base64
import io
import json
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from typing import Any

MAX_INPUT_BYTES = 10 * 1_024 * 1_024
MAX_EXTRACTED_CHARACTERS = 500_000
MAX_PDF_PAGES = 100
IGNORED_ELEMENTS = frozenset(
    {"script", "style", "template", "noscript", "svg", "nav", "aside", "footer", "header"}
)


class ResearchHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ignored_depth = 0
        self.in_title = False
        self.text_parts: list[str] = []
        self.title = ""
        self.publisher = ""
        self.published_at = ""
        self.language: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        attributes = {name.lower(): value or "" for name, value in attrs}
        if normalized_tag == "html" and attributes.get("lang"):
            self.language = attributes["lang"][:35]
        if normalized_tag in IGNORED_ELEMENTS:
            self.ignored_depth += 1
        if normalized_tag == "title" and self.ignored_depth == 0:
            self.in_title = True
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
            self.in_title = False
        if normalized_tag in IGNORED_ELEMENTS and self.ignored_depth > 0:
            self.ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.ignored_depth > 0:
            return
        if self.in_title:
            self.title += f" {data}"
        else:
            self.text_parts.append(data)


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(15 * 1_024 * 1_024 + 1)
        if len(raw) > 15 * 1_024 * 1_024:
            return fail("response_too_large")
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            return fail("protocol_error")
        body = base64.b64decode(required_string(payload, "body_base64"), validate=True)
        if not body or len(body) > MAX_INPUT_BYTES:
            return fail("response_too_large")
        media_type = required_string(payload, "media_type")
        source_url = required_string(payload, "source_url")
        encoding = required_string(payload, "encoding")
        result = parse_document(source_url, media_type, encoding, body)
        sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except BaseException:
        return fail("protocol_error")


def parse_document(source_url: str, media_type: str, encoding: str, body: bytes) -> dict[str, Any]:
    if media_type == "text/plain":
        text = normalize(body.decode(encoding, errors="replace"))
        if not text:
            raise ValueError("empty text")
        return {
            "source_url": source_url,
            "title": source_url,
            "text": text[:MAX_EXTRACTED_CHARACTERS],
        }
    if media_type == "text/html":
        parser = ResearchHtmlParser()
        parser.feed(body.decode(encoding, errors="replace"))
        parser.close()
        text = normalize(" ".join(parser.text_parts))
        if not text:
            raise ValueError("empty HTML")
        return {
            "source_url": source_url,
            "title": normalize(parser.title) or source_url,
            "text": text[:MAX_EXTRACTED_CHARACTERS],
            "publisher": normalize(parser.publisher) or None,
            "published_at": parse_datetime(parser.published_at),
            "language": parser.language,
        }
    if media_type == "application/pdf":
        return parse_pdf(source_url, body)
    raise ValueError("unsupported media type")


def parse_pdf(source_url: str, body: bytes) -> dict[str, Any]:
    from pypdf import PdfReader, filters

    for name in (
        "JBIG2_MAX_OUTPUT_LENGTH",
        "LZW_MAX_OUTPUT_LENGTH",
        "RUN_LENGTH_MAX_OUTPUT_LENGTH",
        "ZLIB_MAX_OUTPUT_LENGTH",
        "MAX_DECLARED_STREAM_LENGTH",
        "MAX_ARRAY_BASED_STREAM_OUTPUT_LENGTH",
        "IMAGE_MAX_BUFFER_SIZE",
    ):
        if hasattr(filters, name):
            setattr(filters, name, 16 * 1_024 * 1_024)
    if hasattr(filters, "JBIG2DEC_BINARY"):
        filters.JBIG2DEC_BINARY = None
    reader = PdfReader(io.BytesIO(body), strict=True)
    if reader.is_encrypted:
        raise ValueError("encrypted PDF")
    if len(reader.pages) > MAX_PDF_PAGES:
        raise ValueError("too many PDF pages")
    parts: list[str] = []
    total = 0
    for page in reader.pages:
        text = page.extract_text() or ""
        remaining = MAX_EXTRACTED_CHARACTERS - total
        if remaining <= 0:
            break
        piece = text[:remaining]
        parts.append(piece)
        total += len(piece)
    extracted = normalize(" ".join(parts))
    if not extracted:
        raise ValueError("PDF contains no extractable text")
    metadata = reader.metadata
    title = normalize(str(metadata.title or "")) if metadata is not None else ""
    publisher = normalize(str(metadata.author or "")) if metadata is not None else ""
    return {
        "source_url": source_url,
        "title": title[:1_000] or source_url,
        "text": extracted,
        "publisher": publisher[:500] or None,
    }


def required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing {key}")
    return value


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def parse_datetime(value: str) -> str | None:
    if not value:
        return None
    candidate = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.isoformat()


def fail(code: str) -> int:
    sys.stdout.write(json.dumps({"code": code}, separators=(",", ":")))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
