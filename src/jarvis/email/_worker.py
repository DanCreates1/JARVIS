"""Stdlib-only isolated MIME-to-text worker; treats every header/body as untrusted."""

from __future__ import annotations

import base64
import hashlib
import json
import sys
from email import policy
from email.message import Message
from email.parser import BytesParser
from typing import Any


def clean(value: str) -> str:
    return "".join(c for c in value if (ord(c) >= 32 and ord(c) != 127) or c in "\n\t")


def parse(raw: bytes) -> dict[str, Any]:
    if not raw or len(raw) > 131_072:
        raise ValueError("message_size")
    message = BytesParser(policy=policy.default).parsebytes(raw)
    headers = {}
    for key in ("From", "To", "Subject", "Date"):
        if len(message.get_all(key, [])) > 1:
            raise ValueError("duplicate_header")
        headers[key.lower()] = clean(str(message.get(key, ""))).replace("\n", " ")[:512]
    stack: list[tuple[Message, int]] = [(message, 0)]
    count = 0
    texts: list[str] = []
    while stack:
        part, depth = stack.pop()
        count += 1
        if count > 32 or depth > 8 or part.defects:
            raise ValueError("mime_rejected")
        if part.get_content_disposition() == "attachment" or part.get_filename():
            continue
        if part.get_content_maintype() == "message":
            continue
        payload = part.get_payload()
        if part.is_multipart():
            if not isinstance(payload, list):
                raise ValueError("mime_rejected")
            stack.extend((child, depth + 1) for child in reversed(payload))
        elif part.get_content_type() == "text/plain":
            charset = (part.get_content_charset() or "us-ascii").lower()
            if charset not in {"utf-8", "us-ascii", "iso-8859-1", "windows-1252"}:
                raise ValueError("charset_rejected")
            decoded = part.get_payload(decode=True)
            if not isinstance(decoded, bytes):
                raise ValueError("mime_rejected")
            texts.append(clean(decoded.decode(charset, errors="strict")))
            if part.defects:
                raise ValueError("mime_rejected")
    text = "\n".join(texts).strip()
    if not text:
        raise ValueError("plain_text_unavailable")
    return {
        "sender": headers["from"],
        "recipients": headers["to"],
        "subject": headers["subject"],
        "date": headers["date"],
        "text": text[:32_000],
        "truncated": len(text) > 32_000,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def main() -> None:
    try:
        payload = json.loads(sys.stdin.buffer.read(180_001))
        raw = base64.b64decode(payload["body"], validate=True)
        result = parse(raw)
    except Exception:
        print(json.dumps({"error": "message_rejected"}))
        raise SystemExit(1) from None
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
