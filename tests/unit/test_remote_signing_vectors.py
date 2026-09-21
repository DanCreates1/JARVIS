from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from jarvis.remote import SignedRequest, build_enrollment_proof, canonical_request
from jarvis.remote.signing import decode_base64url, encode_base64url

_FIXTURE = Path(__file__).parents[1] / "fixtures" / "remote_signing_vectors.json"


def test_python_matches_cross_language_remote_signing_vectors() -> None:
    vectors = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    private_key = Ed25519PrivateKey.from_private_bytes(bytes(vectors["private_key_seed"]))
    public_key = encode_base64url(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )
    assert public_key == vectors["public_key"]

    request = vectors["request"]
    signed_request = SignedRequest(
        method=request["method"],
        authority=request["authority"],
        path=request["path"],
        query=request["query"],
        body=decode_base64url(request["body_base64url"]),
        device_id=request["device_id"],
        key_version=request["key_version"],
        audience=request["audience"],
        timestamp=datetime.fromisoformat(request["timestamp"].replace("Z", "+00:00")),
        nonce=request["nonce"],
        session_token=request["session_token"],
    )
    canonical = canonical_request(signed_request)
    assert encode_base64url(canonical) == request["canonical_base64url"]
    assert encode_base64url(private_key.sign(canonical)) == request["signature_base64url"]

    for name in ("enrollment_v1", "enrollment_v2"):
        vector = vectors[name]
        proof = build_enrollment_proof(
            enrollment_id=vector["enrollment_id"],
            challenge=vector["challenge"],
            public_key=public_key,
            protocol_version=vector["protocol_version"],
            server_origin=vector.get("server_origin"),
        )
        assert encode_base64url(proof) == vector["proof_base64url"]
        assert encode_base64url(private_key.sign(proof)) == vector["signature_base64url"]
