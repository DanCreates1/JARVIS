import { ed25519 } from "@noble/curves/ed25519.js";

import {
  buildEnrollmentProof,
  canonicalRequest,
  decodeBase64Url,
  encodeBase64Url,
} from "@/core/crypto/canonicalRequest";

const vectors = require("../../tests/fixtures/remote_signing_vectors.json") as {
  private_key_seed: number[];
  public_key: string;
  request: {
    method: string;
    authority: string;
    path: string;
    query: string;
    body_base64url: string;
    device_id: string;
    key_version: number;
    audience: "jarvis-api";
    timestamp: string;
    nonce: string;
    session_token: string;
    canonical_base64url: string;
    signature_base64url: string;
  };
  enrollment_v1: {
    enrollment_id: string;
    challenge: string;
    protocol_version: "1";
    proof_base64url: string;
    signature_base64url: string;
  };
  enrollment_v2: {
    enrollment_id: string;
    challenge: string;
    protocol_version: "2";
    server_origin: string;
    proof_base64url: string;
    signature_base64url: string;
  };
};

describe("cross-language signing vectors", () => {
  const privateKey = Uint8Array.from(vectors.private_key_seed);
  const requestInput = () => ({
    method: vectors.request.method,
    authority: vectors.request.authority,
    path: vectors.request.path,
    query: vectors.request.query,
    body: decodeBase64Url(vectors.request.body_base64url),
    deviceId: vectors.request.device_id,
    keyVersion: vectors.request.key_version,
    audience: vectors.request.audience,
    timestamp: vectors.request.timestamp,
    nonce: vectors.request.nonce,
    sessionToken: vectors.request.session_token,
  });

  it("matches Python request canonicalization and Ed25519 signing", () => {
    expect(encodeBase64Url(ed25519.getPublicKey(privateKey))).toBe(vectors.public_key);
    const request = vectors.request;
    const canonical = canonicalRequest(requestInput());
    expect(encodeBase64Url(canonical)).toBe(request.canonical_base64url);
    expect(encodeBase64Url(ed25519.sign(canonical, privateKey))).toBe(request.signature_base64url);
  });

  it("matches Python enrollment v1 and authority-bound v2 proofs", () => {
    for (const vector of [vectors.enrollment_v1, vectors.enrollment_v2] as const) {
      const proof = buildEnrollmentProof({
        enrollmentId: vector.enrollment_id,
        challenge: vector.challenge,
        publicKey: vectors.public_key,
        protocolVersion: vector.protocol_version,
        ...(vector.protocol_version === "2" ? { serverOrigin: vector.server_origin } : {}),
      });
      expect(encodeBase64Url(proof)).toBe(vector.proof_base64url);
      expect(encodeBase64Url(ed25519.sign(proof, privateKey))).toBe(vector.signature_base64url);
    }
  });

  it("rejects mutation of signed authority and enrollment origin", () => {
    const request = vectors.request;
    const original = canonicalRequest(requestInput());
    const mutated = canonicalRequest({
      method: request.method,
      authority: "evil.example",
      path: request.path,
      query: request.query,
      body: decodeBase64Url(request.body_base64url),
      deviceId: request.device_id,
      keyVersion: request.key_version,
      audience: request.audience,
      timestamp: request.timestamp,
      nonce: request.nonce,
      sessionToken: request.session_token,
    });
    expect(encodeBase64Url(mutated)).not.toBe(encodeBase64Url(original));

    const v2 = vectors.enrollment_v2;
    const proof = buildEnrollmentProof({
      enrollmentId: v2.enrollment_id,
      challenge: v2.challenge,
      publicKey: vectors.public_key,
      protocolVersion: "2",
      serverOrigin: v2.server_origin,
    });
    const changed = buildEnrollmentProof({
      enrollmentId: v2.enrollment_id,
      challenge: v2.challenge,
      publicKey: vectors.public_key,
      protocolVersion: "2",
      serverOrigin: "https://evil.example",
    });
    expect(encodeBase64Url(changed)).not.toBe(encodeBase64Url(proof));
  });

  it("fails closed on every malformed canonical request component", () => {
    const invalid = [
      { method: "G ET" },
      { authority: "user@jarvis.example" },
      { authority: "jarvis.example:99999" },
      { path: "relative" },
      { query: "bad\nquery" },
      { deviceId: "" },
      { keyVersion: 0 },
      { audience: "other-api" as never },
      { timestamp: "2026-09-21T12:34:56Z" },
      { nonce: "short" },
    ];
    for (const change of invalid) {
      expect(() => canonicalRequest({ ...requestInput(), ...change })).toThrow();
    }
    expect(encodeBase64Url(canonicalRequest({ ...requestInput(), sessionToken: null }))).not.toBe(
      vectors.request.canonical_base64url,
    );
  });

  it("rejects malformed base64url and incomplete enrollment proof inputs", () => {
    for (const value of ["", "AA=", "not+url", "A"]) {
      expect(() => decodeBase64Url(value)).toThrow();
    }
    expect(() =>
      buildEnrollmentProof({
        enrollmentId: "enrollment:test",
        challenge: "A".repeat(43),
        publicKey: vectors.public_key,
        protocolVersion: "1",
        serverOrigin: "https://jarvis.example",
      }),
    ).toThrow("enrollment v1 cannot bind");
    expect(() =>
      buildEnrollmentProof({
        enrollmentId: "enrollment:test",
        challenge: "A".repeat(43),
        publicKey: vectors.public_key,
        protocolVersion: "2",
      }),
    ).toThrow("enrollment v2 requires");
  });
});
