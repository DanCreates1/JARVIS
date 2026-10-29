"""Opt-in real PWA/Core/public-source acceptance using disposable identities and state."""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
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

import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

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
        runtime_profile="public-research",
        trusted_browser_origins=(f"https://127.0.0.1:{port}",),
        ollama_model="qwen3:1.7b",
    )

    async def factory(config: Settings):
        runtime = await build_runtime(config)
        assert set(runtime.provider.providers) == {ModelRole.LOCAL}
        assert runtime.research is not None and runtime.attachments is None
        assert set(runtime.service.tools) == {"get_current_time"}
        assert runtime.remote_identity is not None

        async def forbidden(**kwargs):
            (directory / "unexpected-model-call").write_text("failed", encoding="utf-8")
            raise AssertionError("grounded research must not invoke a model")
            yield

        runtime.provider.providers[ModelRole.LOCAL].stream_chat = forbidden
        projector = runtime.service.automatic_research
        original = projector.render

        def observed(report, decision):
            result = original(report, decision)
            with (directory / "evidence.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(report.model_dump(mode="json")) + "\n")
            return result

        projector.render = observed
        tickets = directory / "tickets.json"
        if not tickets.exists():
            ticket = await runtime.remote_identity.create_enrollment(
                host_id=runtime.memory_host_id,
                display_name="Synthetic research owner",
                device_type=DeviceType.BROWSER,
                approved_scopes=tuple(
                    RemoteScope(scope)
                    for scope in (
                        "browser.session",
                        "identity.read",
                        "events.read",
                        "session.revoke",
                        "client.chat",
                        "client.status.read",
                        "client.tasks.read",
                    )
                ),
            )
            tickets.write_text(json.dumps([ticket.model_dump(mode="json")]), encoding="utf-8")
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--serve", type=Path)
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    # Never inherit a real store, credential, model endpoint or production integration flag.
    for key in list(os.environ):
        if key.upper().startswith("JARVIS_") or key.upper() in {
            "NVIDIA_API_KEY",
            "GROQ_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
        }:
            del os.environ[key]
    if args.serve:
        asyncio.run(serve(args.serve, args.port))
        return
    if not args.live:
        parser.error("public network acceptance requires --live; no credentials or cloud model")
    parent = (ROOT / "runtime" / "phase11").resolve()
    assert parent.is_relative_to(ROOT)
    parent.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="acceptance-", dir=parent))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic research fixture")])
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
        ["node", "scripts/research-browser-check.cjs", str(directory / "config.json")],
        cwd=ROOT,
        check=False,
    )
    if result.returncode:
        raise SystemExit(result.returncode)
    with sqlite3.connect(directory / "core" / "jarvis.db") as database:
        for table in ("research_sources", "research_reports", "memory_items"):
            assert database.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert not (directory / "unexpected-model-call").exists()
    print(json.dumps({"research_source_report_memory_rows": 0, "model_calls": 0, "cost_usd": 0}))
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
