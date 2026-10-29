"""Opt-in real PWA/Core/local-model acceptance with disposable synthetic files only."""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import io
import ipaddress
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from jarvis.bootstrap import build_runtime
from jarvis.config import Settings
from jarvis.core import ModelRole
from jarvis.remote import DeviceType, RemoteScope
from jarvis.web import create_app

ROOT = Path(__file__).resolve().parents[1]


async def serve(directory: Path, port: int) -> None:
    settings = Settings(
        _env_file=None,
        data_dir=directory / "core",
        runtime_profile="private-files",
        ollama_model="qwen3:1.7b",
        trusted_browser_origins=(f"https://127.0.0.1:{port}",),
    )

    async def factory(config: Settings):
        runtime = await build_runtime(config)
        assert set(runtime.provider.providers) == {ModelRole.LOCAL}
        assert runtime.attachments is not None and runtime.attachments.vision is None
        assert runtime.research is None and set(runtime.service.tools) == {"get_current_time"}
        assert runtime.remote_identity is not None
        original_stream = runtime.provider.providers[ModelRole.LOCAL].stream_chat

        async def observed_stream(**kwargs):
            with (directory / "provider-calls.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"tool_count": len(kwargs.get("tools", ()))}) + "\n")
            async for frame in original_stream(**kwargs):
                yield frame

        runtime.provider.providers[ModelRole.LOCAL].stream_chat = observed_stream
        tickets = directory / "tickets.json"
        if not tickets.exists():
            result = []
            for name in ("Synthetic files owner", "Synthetic foreign owner"):
                ticket = await runtime.remote_identity.create_enrollment(
                    host_id=runtime.memory_host_id,
                    display_name=name,
                    device_type=DeviceType.BROWSER,
                    approved_scopes=tuple(
                        RemoteScope(scope)
                        for scope in (
                            "browser.session",
                            "identity.read",
                            "events.read",
                            "session.revoke",
                            "client.chat",
                            "client.tasks.read",
                            "client.status.read",
                        )
                    ),
                )
                result.append(ticket.model_dump(mode="json"))
            tickets.write_text(json.dumps(result), encoding="utf-8")
        return runtime

    await uvicorn.Server(
        uvicorn.Config(
            create_app(settings, runtime_factory=factory),
            host="127.0.0.1",
            port=port,
            ssl_keyfile=str(directory / "fixture.key"),
            ssl_certfile=str(directory / "fixture.pem"),
            log_level="warning",
            access_log=False,
        )
    ).serve()


def fixtures(directory: Path) -> None:
    (directory / "cedar.txt").write_text("cedar inventory has 17 lanterns", encoding="utf-8")
    writer = PdfWriter()
    page = writer.add_blank_page(width=400, height=100)
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 10 10 Td (harbor shipment has 23 crates) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {
                    NameObject("/F1"): DictionaryObject(
                        {
                            NameObject("/Type"): NameObject("/Font"),
                            NameObject("/Subtype"): NameObject("/Type1"),
                            NameObject("/BaseFont"): NameObject("/Helvetica"),
                        }
                    )
                }
            ),
        }
    )
    output = io.BytesIO()
    writer.write(output)
    (directory / "harbor.pdf").write_bytes(output.getvalue())
    Image.new("RGB", (16, 16), "red").save(directory / "red.png")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--serve", type=Path)
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    # Never inherit a real store, credential, model endpoint or production integration flag.
    for key in list(os.environ):
        if key.upper().startswith("JARVIS_") or key.upper() == "NVIDIA_API_KEY":
            del os.environ[key]
    if args.serve:
        asyncio.run(serve(args.serve, args.port))
        return
    if not args.live:
        parser.error("local inference requires --live; no download or cloud fallback")
    with httpx.Client(trust_env=False, timeout=5) as client:
        models = client.get("http://127.0.0.1:11434/api/tags").json()["models"]
        assert any(model["name"] == "qwen3:1.7b" for model in models), "installed model required"
    parent = (ROOT / "runtime" / "phase9").resolve()
    assert parent.is_relative_to(ROOT)
    parent.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="acceptance-", dir=parent))
    fixtures(directory)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic files fixture")])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
        .not_valid_after(datetime.now(UTC) + timedelta(hours=5))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    (directory / "fixture.key").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    (directory / "fixture.pem").write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    spki = base64.b64encode(
        hashlib.sha256(
            key.public_key().public_bytes(
                serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
            )
        ).digest()
    ).decode()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    config = {"directory": str(directory), "python": sys.executable, "port": port, "spki": spki}
    (directory / "config.json").write_text(json.dumps(config), encoding="utf-8")
    print(f"Synthetic evidence: {directory}", flush=True)
    result = subprocess.run(
        ["node", "scripts/files-browser-check.cjs", str(directory / "config.json")],
        cwd=ROOT,
        check=False,
    )
    if result.returncode:
        raise SystemExit(result.returncode)
    with sqlite3.connect(directory / "core" / "jarvis.db") as database:
        assert database.execute("SELECT COUNT(*) FROM memory_items").fetchone()[0] == 0
        assert (
            database.execute(
                "SELECT COUNT(*) FROM pwa_chat_requests WHERE status='running'"
            ).fetchone()[0]
            == 0
        )
        assert (
            database.execute(
                "SELECT COUNT(*) FROM conversations WHERE attachment_private=1"
            ).fetchone()[0]
            >= 1
        )
    print(
        json.dumps(
            {
                "automatic_memory_candidates": 0,
                "running_requests": 0,
                "sticky_private": True,
            }
        )
    )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
