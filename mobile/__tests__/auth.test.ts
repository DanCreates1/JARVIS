import { ed25519 } from "@noble/curves/ed25519.js";

import { SignedApiClient, type SessionCredential } from "@/core/api/signedApiClient";
import type { FetchLike, ResponseLike } from "@/core/api/types";
import { MobileAuthClient } from "@/core/auth/authClient";
import { authReducer } from "@/core/auth/authState";
import {
  CorruptIdentityError,
  IdentityVault,
  identitySummary,
  type MobileIdentity,
  type SecureKeyValueStore,
} from "@/core/auth/identityVault";
import { normalizeServerOrigin } from "@/core/auth/origin";
import type { RandomSource } from "@/core/auth/platform";
import { parseEnrollmentTicket } from "@/core/auth/ticket";
import {
  buildEnrollmentProof,
  canonicalRequest,
  decodeBase64Url,
  encodeBase64Url,
} from "@/core/crypto/canonicalRequest";

const now = new Date("2026-09-21T12:00:00.000Z");
const origin = "https://jarvis.tail1234.ts.net";
const seed = Uint8Array.from({ length: 32 }, (_, index) => index + 1);

class MemoryStore implements SecureKeyValueStore {
  readonly values = new Map<string, string>();

  async get(key: string): Promise<string | null> {
    return this.values.get(key) ?? null;
  }

  async set(key: string, value: string): Promise<void> {
    this.values.set(key, value);
  }

  async delete(key: string): Promise<void> {
    this.values.delete(key);
  }
}

class DeterministicRandom implements RandomSource {
  calls = 0;

  async bytes(length: number): Promise<Uint8Array> {
    this.calls += 1;
    if (length === 32) return seed.slice();
    return Uint8Array.from({ length }, (_, index) => (index + this.calls) % 256);
  }
}

function ticket(overrides: Record<string, unknown> = {}): string {
  return JSON.stringify({
    id: "enrollment:test",
    challenge: encodeBase64Url(Uint8Array.from({ length: 32 }, () => 7)),
    host_id: "host:test",
    display_name: "iPhone",
    device_type: "phone",
    approved_scopes: ["client.status.read"],
    risk_ceiling: 1,
    expires_at: "2026-09-21T12:10:00Z",
    protocol_version: "2",
    server_origin: origin,
    ...overrides,
  });
}

function response(
  status: number,
  body: unknown,
  headers: Record<string, string> = {},
): ResponseLike {
  const normalized = new Map(
    Object.entries(headers).map(([key, value]) => [key.toLowerCase(), value]),
  );
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (name) => normalized.get(name.toLowerCase()) ?? null },
    json: async () => body,
  };
}

class FakeCore {
  readonly random = new DeterministicRandom();
  readonly requests: Array<{
    url: string;
    method: string;
    headers: Readonly<Record<string, string>>;
    body?: string;
  }> = [];
  sessionCount = 0;
  revoked = 0;
  enrollmentOrigin = origin;

  readonly fetch: FetchLike = async (input, init) => {
    this.requests.push({ url: input, ...init });
    const url = new URL(input);
    if (url.pathname === "/api/v1/enrollments/complete") {
      const body = JSON.parse(init.body ?? "{}") as Record<string, string>;
      const proof = buildEnrollmentProof({
        enrollmentId: body.enrollment_id,
        challenge: body.challenge,
        publicKey: body.public_key,
        protocolVersion: "2",
        serverOrigin: body.server_origin,
      });
      expect(
        ed25519.verify(
          decodeBase64Url(body.proof_signature),
          proof,
          decodeBase64Url(body.public_key),
        ),
      ).toBe(true);
      return response(200, {
        id: "device:test",
        key_version: 1,
        enrollment_protocol_version: "2",
        server_origin: this.enrollmentOrigin,
        enrolled_at: now.toISOString(),
      });
    }

    const publicKey = ed25519.getPublicKey(seed);
    const body = init.body ?? "";
    const signed = canonicalRequest({
      method: init.method,
      authority: url.host,
      path: url.pathname,
      query: url.search.slice(1),
      body: new TextEncoder().encode(body),
      deviceId: init.headers["X-Jarvis-Device"],
      keyVersion: Number(init.headers["X-Jarvis-Key-Version"]),
      audience: "jarvis-api",
      timestamp: init.headers["X-Jarvis-Date"],
      nonce: init.headers["X-Jarvis-Nonce"],
      sessionToken: init.headers.Authorization?.replace("Bearer ", "") ?? null,
    });
    expect(
      ed25519.verify(decodeBase64Url(init.headers["X-Jarvis-Signature"]), signed, publicKey),
    ).toBe(true);
    if (url.pathname === "/api/v1/sessions") {
      this.sessionCount += 1;
      const requested = JSON.parse(body) as { requested_scopes: string[] };
      return response(200, {
        session_id: `session:${this.sessionCount}`,
        token: `token-${this.sessionCount}`,
        device_id: "device:test",
        key_version: 1,
        audience: "jarvis-api",
        scopes: requested.requested_scopes,
        expires_at: "2026-09-21T12:05:00Z",
      });
    }
    if (url.pathname === "/api/v1/client/status") {
      return response(200, { ready: true });
    }
    if (url.pathname === "/api/v1/sessions/current") {
      this.revoked += 1;
      return response(204, {});
    }
    return response(404, {});
  };
}

function identity(): MobileIdentity {
  return {
    schemaVersion: 1,
    serverOrigin: origin,
    privateSeed: encodeBase64Url(seed),
    publicKey: encodeBase64Url(ed25519.getPublicKey(seed)),
    deviceId: "device:test",
    keyVersion: 1,
    enrollmentProtocolVersion: "2",
    enrolledAt: now.toISOString(),
  };
}

describe("mobile authentication", () => {
  it("normalizes reviewed origins and permits HTTP loopback only when explicitly enabled", () => {
    expect(normalizeServerOrigin("https://JARVIS.Example:443")).toBe("https://jarvis.example");
    expect(normalizeServerOrigin("http://localhost:8000", { allowInsecureLoopback: true })).toBe(
      "http://localhost:8000",
    );
    for (const value of [
      " http://localhost:8000",
      "http://localhost:8000",
      "http://192.168.1.2:8000",
      "https://user@example.com",
      "https://example.com/path",
      "https://bad_host.example",
      "https://example.com:99999",
      "https://example.com.",
    ]) {
      expect(() => normalizeServerOrigin(value)).toThrow();
    }
  });

  it("parses strict v2 phone tickets and rejects malformed input", () => {
    expect(parseEnrollmentTicket(ticket()).serverOrigin).toBe(origin);
    for (const payload of [
      "not json",
      "[]",
      ticket({ extra: true }),
      ticket({ device_type: "browser" }),
      ticket({ challenge: "short" }),
      ticket({ approved_scopes: [] }),
      ticket({ approved_scopes: ["identity.read"] }),
      ticket({ approved_scopes: ["client.status.read", "client.status.read"] }),
      ticket({ risk_ceiling: 3 }),
      ticket({ expires_at: "invalid" }),
      ticket({ protocol_version: "1" }),
    ]) {
      expect(() => parseEnrollmentTicket(payload)).toThrow();
    }
  });

  it("round-trips a validated identity and fails closed on corrupt secure storage", async () => {
    const store = new MemoryStore();
    const vault = new IdentityVault(store);
    expect(await vault.load()).toBeNull();
    await vault.save(identity());
    expect(await new IdentityVault(store).load()).toEqual(identity());

    const key = [...store.values.keys()][0];
    store.values.set(key, JSON.stringify({ ...identity(), publicKey: "bad" }));
    await expect(vault.load()).rejects.toBeInstanceOf(CorruptIdentityError);
    store.values.set(
      key,
      JSON.stringify({ ...identity(), serverOrigin: "https://JARVIS.tail1234.ts.net" }),
    );
    await expect(vault.load()).rejects.toBeInstanceOf(CorruptIdentityError);
    await expect(
      vault.save({ ...identity(), serverOrigin: "http://evil.example" }),
    ).rejects.toBeInstanceOf(CorruptIdentityError);
    await vault.erase();
    expect(await vault.load()).toBeNull();
  });

  it("pairs, verifies signed requests, keeps sessions in memory, refreshes, and revokes", async () => {
    const store = new MemoryStore();
    const vault = new IdentityVault(store);
    const core = new FakeCore();
    const api = new SignedApiClient(core.fetch, core.random, () => now);
    const auth = new MobileAuthClient(vault, api, core.random, () => now);

    const paired = await auth.pair(ticket());
    expect(paired.identity).toEqual(identitySummary(identity()));
    expect(JSON.stringify(paired)).not.toContain(identity().privateSeed);
    expect(core.sessionCount).toBe(1);
    expect(JSON.parse(core.requests[1]?.body ?? "{}").requested_scopes).toEqual([
      "client.status.read",
    ]);
    await expect(auth.pair(ticket())).rejects.toThrow("already enrolled");
    expect(JSON.stringify([...store.values.values()])).not.toContain("token-1");
    expect(await auth.getStatus()).toEqual({ ready: true });
    expect(core.sessionCount).toBe(1);

    const restarted = new MobileAuthClient(vault, api, core.random, () => now);
    expect(await restarted.restoreIdentity()).toEqual(identitySummary(identity()));
    expect((await restarted.ensureSession(["client.status.read"])).token).toBe("token-2");
    expect(core.sessionCount).toBe(2);
    await restarted.logout();
    expect(core.revoked).toBe(1);
    expect(await restarted.restoreIdentity()).toEqual(identitySummary(identity()));
    await restarted.eraseCredentials();
    expect(await restarted.restoreIdentity()).toBeNull();
  });

  it("refreshes an expiring session and validates requested scopes", async () => {
    const store = new MemoryStore();
    const vault = new IdentityVault(store);
    await vault.save(identity());
    const core = new FakeCore();
    const auth = new MobileAuthClient(
      vault,
      new SignedApiClient(core.fetch, core.random, () => now),
      core.random,
      () => now,
    );
    await auth.ensureSession(["client.status.read"]);
    expect(core.sessionCount).toBe(1);
    const late = new MobileAuthClient(
      vault,
      new SignedApiClient(core.fetch, core.random, () => new Date("2026-09-21T12:04:45Z")),
      core.random,
      () => new Date("2026-09-21T12:04:45Z"),
    );
    await late.ensureSession(["client.status.read"]);
    expect(core.sessionCount).toBe(2);
    await expect(auth.ensureSession([])).rejects.toThrow("non-empty and unique");
    await expect(auth.ensureSession(["client.status.read", "client.status.read"])).rejects.toThrow(
      "non-empty and unique",
    );
  });

  it("rejects expired tickets and wrong-host enrollment responses", async () => {
    const core = new FakeCore();
    const vault = new IdentityVault(new MemoryStore());
    const auth = new MobileAuthClient(
      vault,
      new SignedApiClient(core.fetch, core.random, () => now),
      core.random,
      () => now,
    );
    await expect(auth.pair(ticket({ expires_at: "2026-09-21T11:50:00Z" }))).rejects.toThrow(
      "expired",
    );
    core.enrollmentOrigin = "https://wrong.example";
    await expect(auth.pair(ticket())).rejects.toThrow("JARVIS API request failed");
  });

  it("erases prior identity before changing Core origin", async () => {
    const store = new MemoryStore();
    const vault = new IdentityVault(store);
    await vault.save(identity());
    const core = new FakeCore();
    const auth = new MobileAuthClient(
      vault,
      new SignedApiClient(core.fetch, core.random, () => now),
      core.random,
      () => now,
    );
    await expect(auth.pair(ticket({ server_origin: "https://other.example" }))).rejects.toThrow(
      "JARVIS API request failed",
    );
    expect(await vault.load()).toBeNull();
  });

  it("erases local identity even when remote revocation fails", async () => {
    const store = new MemoryStore();
    const vault = new IdentityVault(store);
    const core = new FakeCore();
    const api = new SignedApiClient(core.fetch, core.random, () => now);
    const auth = new MobileAuthClient(vault, api, core.random, () => now);
    await auth.pair(ticket());
    const failingFetch: FetchLike = async (input, init) => {
      if (new URL(input).pathname === "/api/v1/sessions/current") return response(500, {});
      return core.fetch(input, init);
    };
    const failingApi = new SignedApiClient(failingFetch, core.random, () => now);
    const restarted = new MobileAuthClient(vault, failingApi, core.random, () => now);
    await restarted.ensureSession(["client.status.read"]);
    await expect(restarted.eraseCredentials()).rejects.toThrow("JARVIS API request failed");
    expect(await vault.load()).toBeNull();
  });

  it("uses bounded server Date correction for one authentication retry", async () => {
    let calls = 0;
    const timestamps: string[] = [];
    const fetcher: FetchLike = async (_input, init) => {
      calls += 1;
      timestamps.push(init.headers["X-Jarvis-Date"]);
      if (calls === 1) return response(401, {}, { Date: "Mon, 21 Sep 2026 12:02:00 GMT" });
      return response(200, { ready: true });
    };
    const api = new SignedApiClient(fetcher, new DeterministicRandom(), () => now);
    const session: SessionCredential = {
      sessionId: "session:test",
      token: "token",
      deviceId: "device:test",
      keyVersion: 1,
      audience: "jarvis-api",
      scopes: ["client.status.read"],
      expiresAt: "2026-09-21T12:05:00Z",
    };
    await expect(api.getStatus(identity(), session)).resolves.toEqual({ ready: true });
    expect(calls).toBe(2);
    expect(timestamps).toEqual(["2026-09-21T12:00:00.000000Z", "2026-09-21T12:02:00.000000Z"]);
  });

  it("transitions through typed auth states", () => {
    expect(authReducer({ status: "loading" }, { type: "RESTORED", identity: null })).toEqual({
      status: "unenrolled",
    });
    expect(authReducer({ status: "unenrolled" }, { type: "PAIR_STARTED" })).toEqual({
      status: "pairing",
    });
    expect(
      authReducer({ status: "pairing" }, { type: "PAIR_SUCCEEDED", identity: identity() }),
    ).toMatchObject({ status: "enrolled", online: true });
    expect(
      authReducer(
        { status: "enrolled", identity: identity(), online: true },
        { type: "CONNECTIVITY_CHANGED", online: false },
      ),
    ).toMatchObject({ status: "enrolled", online: false });
    expect(authReducer({ status: "loading" }, { type: "FAILED", message: "no" })).toEqual({
      status: "error",
      message: "no",
    });
    expect(authReducer({ status: "error", message: "no" }, { type: "ERASED" })).toEqual({
      status: "unenrolled",
    });
  });
});
