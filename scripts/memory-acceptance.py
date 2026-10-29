"""Opt-in real PWA/Core/local-model acceptance with disposable synthetic memory only."""

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
from jarvis.memory import MemoryCategory, ProvenanceSource, untrusted_provenance
from jarvis.web import create_app

ROOT = Path(__file__).resolve().parents[1]


async def serve(directory: Path, port: int) -> None:
    settings = Settings(
        _env_file=None,
        data_dir=directory / "core",
        runtime_profile="private-memory",
        ollama_model="qwen3:1.7b",
    )

    async def factory(config: Settings):
        runtime = await build_runtime(config)
        assert set(runtime.provider.providers) == {ModelRole.LOCAL}
        assert runtime.research is None and runtime.attachments is None
        assert set(runtime.service.tools) == {"get_current_time"}
        memory, host = runtime.memory_store, runtime.memory_host_id
        marker = directory / "seeded"
        if not marker.exists():
            await memory.propose(
                host_id=host,
                category=MemoryCategory.PROFILE,
                content="amber orchard has 91 lanterns",
                confidence=1,
                provenance=untrusted_provenance(
                    source_type=ProvenanceSource.IMPORT,
                    source_id="synthetic-import",
                    import_uri="fixture:orchard",
                    source_label="untrusted synthetic orchard import",
                ),
            )
            marker.write_text("synthetic", encoding="utf-8")
        original = runtime.provider.providers[ModelRole.LOCAL].stream_chat

        async def observed(**kwargs):
            content = "\n".join(m.content for m in kwargs["messages"] if m.role.value == "system")
            with (directory / "provider-calls.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "tool_count": len(kwargs.get("tools", ())),
                            "approved_context": "amber orchard has 29 lanterns" in content,
                            "stale_context": "amber orchard has 91 lanterns" in content,
                        }
                    )
                    + "\n"
                )
            async for frame in original(**kwargs):
                yield frame

        runtime.provider.providers[ModelRole.LOCAL].stream_chat = observed
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
    parent = (ROOT / "runtime" / "phase10").resolve()
    assert parent.is_relative_to(ROOT)
    parent.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="acceptance-", dir=parent))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic memory fixture")])
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
        ["node", "scripts/memory-browser-check.cjs", str(directory / "config.json")],
        cwd=ROOT,
        check=False,
    )
    if result.returncode:
        raise SystemExit(result.returncode)
    with sqlite3.connect(directory / "core" / "jarvis.db") as database:
        assert database.execute("SELECT COUNT(*) FROM memory_items").fetchone()[0] == 0
        assert database.execute("SELECT COUNT(*) FROM memory_fts").fetchone()[0] == 0
        assert database.execute("SELECT COUNT(*) FROM memory_provenance").fetchone()[0] == 0
    print(json.dumps({"canonical_fts_provenance_rows": 0, "cloud_calls": 0, "cost_usd": 0}))
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
