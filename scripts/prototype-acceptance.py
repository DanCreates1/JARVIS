"""Opt-in disposable HTTPS/Core/Ollama acceptance; never loads owner configuration."""

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

import httpx
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


async def serve(directory: Path, port: int, model: str) -> None:
    settings = Settings(
        _env_file=None,
        data_dir=directory / "core",
        runtime_profile="prototype-text",
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model=model,
        trusted_browser_origins=(f"https://127.0.0.1:{port}",),
    )

    async def factory(config: Settings):
        runtime = await build_runtime(config)
        assert set(runtime.provider.providers) == {ModelRole.LOCAL}
        assert runtime.research is None and runtime.attachments is None
        assert runtime.remote_identity is not None
        local = runtime.provider.providers[ModelRole.LOCAL]
        original_stream = local.stream_chat

        async def observed_stream(**kwargs):
            with (directory / "provider-calls.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "model": model,
                            "reasoning_level": kwargs.get("reasoning_level"),
                            "tool_names": [tool.name for tool in kwargs.get("tools", ())],
                        }
                    )
                    + "\n"
                )
            async for frame in original_stream(**kwargs):
                if frame.content_delta:
                    with (directory / "provider-deltas.jsonl").open(
                        "a", encoding="utf-8"
                    ) as handle:
                        handle.write(json.dumps({"characters": len(frame.content_delta)}) + "\n")
                yield frame

        local.stream_chat = observed_stream
        tickets = directory / "tickets.json"
        if not tickets.exists():
            result = []
            for name in ("Synthetic owner", "Synthetic foreign owner"):
                ticket = await runtime.remote_identity.create_enrollment(
                    host_id=runtime.memory_host_id or "host:prototype",
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

    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings, runtime_factory=factory),
            host="127.0.0.1",
            port=port,
            ssl_keyfile=str(directory / "fixture.key"),
            ssl_certfile=str(directory / "fixture.pem"),
            log_level="warning",
            access_log=False,
        )
    )
    await server.serve()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--model", default="qwen3:1.7b")
    parser.add_argument("--serve", type=Path)
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    # No inherited .env or JARVIS_* can redirect synthetic storage/provider/authority.
    for key in list(os.environ):
        if key.upper().startswith("JARVIS_") or key.upper() == "NVIDIA_API_KEY":
            del os.environ[key]
    if args.serve:
        asyncio.run(serve(args.serve, args.port, args.model))
        return
    if not args.live:
        parser.error("real local inference requires --live; no download or cloud fallback")
    with httpx.Client(trust_env=False, timeout=5) as client:
        tags = client.get("http://127.0.0.1:11434/api/tags").json()
        version = client.get("http://127.0.0.1:11434/api/version").json()
        resident = client.get("http://127.0.0.1:11434/api/ps").json()
    model = next((item for item in tags["models"] if item["name"] == args.model), None)
    if model is None:
        parser.error("selected model must already be installed")
    parent = ROOT / "runtime" / "proto21"
    parent.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="acceptance-", dir=parent))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic prototype fixture")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
        .not_valid_after(datetime.now(UTC) + timedelta(hours=8))
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
    (directory / "fixture.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
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
    cases = []
    for line in (ROOT / "docs/PROTOTYPE_CORPUS.md").read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.split("|")]
        if len(cells) == 5 and cells[1] in {
            "E1",
            "E2",
            "R1",
            "R2",
            "C1",
            "C2",
            "F1",
            "F2",
            "A1",
            "U1",
        }:
            cases.append({"id": cells[1], "prompt": cells[2], "rubric": cells[3]})
    assert len(cases) == 10
    config = {
        "directory": str(directory),
        "python": sys.executable,
        "port": port,
        "spki": spki,
        "model": model,
        "ollama": version,
        "resident_before": resident,
        "cases": cases,
    }
    (directory / "config.json").write_text(json.dumps(config), encoding="utf-8")
    print(f"Synthetic results: {directory}", flush=True)
    result = subprocess.run(
        ["node", "scripts/prototype-browser-check.cjs", str(directory / "config.json")],
        cwd=ROOT,
        check=False,
    )
    results_path = directory / "browser-results.json"
    if results_path.exists():
        results = json.loads(results_path.read_text(encoding="utf-8"))
        with sqlite3.connect(directory / "core" / "jarvis.db") as database:
            results["durable_status_counts"] = dict(
                database.execute(
                    "SELECT status, COUNT(*) FROM pwa_chat_requests GROUP BY status"
                ).fetchall()
            )
            if request_id := results.get("duplicate_request_id"):
                rows = database.execute(
                    "SELECT start_sequence, end_sequence FROM pwa_chat_requests WHERE request_id=?",
                    (request_id,),
                ).fetchall()
                assert len(rows) == 1 and rows[0][1] - rows[0][0] == 2
                results["retry_durable_receipts"] = len(rows)
                results["retry_durable_messages"] = rows[0][1] - rows[0][0]
            assert (
                not results.get("passed") or results["durable_status_counts"].get("running", 0) == 0
            )
        results_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
