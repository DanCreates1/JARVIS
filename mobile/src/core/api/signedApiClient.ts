import { ed25519 } from "@noble/curves/ed25519.js";

import type { MobileIdentity } from "@/core/auth/identityVault";
import type { RandomSource } from "@/core/auth/platform";
import type { EnrollmentTicketV2 } from "@/core/auth/ticket";
import {
  buildEnrollmentProof,
  buildRotationProof,
  canonicalRequest,
  decodeBase64Url,
  encodeBase64Url,
} from "@/core/crypto/canonicalRequest";

import type { Clock, FetchLike, ResponseLike } from "./types";

const encoder = new TextEncoder();

export type SessionCredential = Readonly<{
  sessionId: string;
  token: string;
  deviceId: string;
  keyVersion: number;
  audience: "jarvis-api";
  scopes: readonly string[];
  expiresAt: string;
}>;

export type EnrollmentDevice = Readonly<{
  id: string;
  keyVersion: number;
  enrollmentProtocolVersion: "2";
  serverOrigin: string;
  enrolledAt: string;
}>;

export type RotatedDevice = Readonly<{
  id: string;
  keyVersion: number;
  enrollmentProtocolVersion: "2";
  serverOrigin: string;
}>;

export class MobileApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
  ) {
    super(`JARVIS API request failed (${status})`);
    this.name = "MobileApiError";
  }
}

export class SignedApiClient {
  private clockOffsetMs = 0;

  constructor(
    private readonly fetcher: FetchLike,
    private readonly random: RandomSource,
    private readonly clock: Clock = () => new Date(),
  ) {}

  async completeEnrollment(
    ticket: EnrollmentTicketV2,
    privateSeed: Uint8Array,
  ): Promise<EnrollmentDevice> {
    const publicKey = encodeBase64Url(ed25519.getPublicKey(privateSeed));
    const proof = buildEnrollmentProof({
      enrollmentId: ticket.id,
      challenge: ticket.challenge,
      publicKey,
      protocolVersion: "2",
      serverOrigin: ticket.serverOrigin,
    });
    const body = JSON.stringify({
      enrollment_id: ticket.id,
      challenge: ticket.challenge,
      public_key: publicKey,
      proof_signature: encodeBase64Url(ed25519.sign(proof, privateSeed)),
      protocol_version: "2",
      server_origin: ticket.serverOrigin,
    });
    const response = await this.fetcher(`${ticket.serverOrigin}/api/v1/enrollments/complete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    this.observeServerTime(response);
    if (!response.ok) throw new MobileApiError(response.status, "enrollment_failed");
    const value = asRecord(await response.json());
    if (
      typeof value.id !== "string" ||
      !value.id.startsWith("device:") ||
      value.key_version !== 1 ||
      value.enrollment_protocol_version !== "2" ||
      value.server_origin !== ticket.serverOrigin ||
      typeof value.enrolled_at !== "string"
    ) {
      throw new MobileApiError(response.status, "invalid_enrollment_response");
    }
    return {
      id: value.id,
      keyVersion: 1,
      enrollmentProtocolVersion: "2",
      serverOrigin: value.server_origin,
      enrolledAt: value.enrolled_at,
    };
  }

  async createSession(
    identity: MobileIdentity,
    requestedScopes: readonly string[],
  ): Promise<SessionCredential> {
    const response = await this.signedRequest(
      identity,
      "POST",
      "/api/v1/sessions",
      JSON.stringify({ requested_scopes: requestedScopes, audience: "jarvis-api" }),
      null,
    );
    if (!response.ok) throw new MobileApiError(response.status, "session_failed");
    const value = asRecord(await response.json());
    const scopes = value.scopes;
    if (
      typeof value.session_id !== "string" ||
      typeof value.token !== "string" ||
      value.device_id !== identity.deviceId ||
      value.key_version !== identity.keyVersion ||
      value.audience !== "jarvis-api" ||
      !Array.isArray(scopes) ||
      !scopes.every((item) => typeof item === "string") ||
      scopes.length !== requestedScopes.length ||
      !requestedScopes.every((scope) => scopes.includes(scope)) ||
      typeof value.expires_at !== "string"
    ) {
      throw new MobileApiError(response.status, "invalid_session_response");
    }
    return {
      sessionId: value.session_id,
      token: value.token,
      deviceId: value.device_id,
      keyVersion: value.key_version,
      audience: "jarvis-api",
      scopes,
      expiresAt: new Date(value.expires_at).toISOString(),
    };
  }

  async getStatus(identity: MobileIdentity, session: SessionCredential): Promise<unknown> {
    const response = await this.signedRequest(
      identity,
      "GET",
      "/api/v1/client/status",
      undefined,
      session.token,
    );
    if (!response.ok) throw new MobileApiError(response.status, "status_failed");
    return response.json();
  }

  async revokeSession(identity: MobileIdentity, session: SessionCredential): Promise<void> {
    const response = await this.signedRequest(
      identity,
      "DELETE",
      "/api/v1/sessions/current",
      undefined,
      session.token,
    );
    if (!response.ok) throw new MobileApiError(response.status, "logout_failed");
  }

  async rotateKey(
    identity: MobileIdentity,
    session: SessionCredential,
    newPrivateSeed: Uint8Array,
  ): Promise<RotatedDevice> {
    if (newPrivateSeed.length !== 32) throw new Error("new private seed has wrong length");
    const newPublicKey = encodeBase64Url(ed25519.getPublicKey(newPrivateSeed));
    const proof = buildRotationProof({
      deviceId: identity.deviceId,
      currentKeyVersion: identity.keyVersion,
      newPublicKey,
    });
    const response = await this.signedRequest(
      identity,
      "POST",
      "/api/v1/device/key",
      JSON.stringify({
        new_public_key: newPublicKey,
        new_key_proof: encodeBase64Url(ed25519.sign(proof, newPrivateSeed)),
      }),
      session.token,
    );
    if (!response.ok) throw new MobileApiError(response.status, "key_rotation_failed");
    const value = asRecord(await response.json());
    if (
      value.id !== identity.deviceId ||
      value.key_version !== identity.keyVersion + 1 ||
      value.enrollment_protocol_version !== "2" ||
      value.server_origin !== identity.serverOrigin ||
      value.state !== "active"
    ) {
      throw new MobileApiError(response.status, "invalid_key_rotation_response");
    }
    return {
      id: identity.deviceId,
      keyVersion: identity.keyVersion + 1,
      enrollmentProtocolVersion: "2",
      serverOrigin: identity.serverOrigin,
    };
  }

  private async signedRequest(
    identity: MobileIdentity,
    method: string,
    path: string,
    body: string | undefined,
    sessionToken: string | null,
    retryForClock = true,
  ): Promise<ResponseLike> {
    const nonce = encodeBase64Url(await this.random.bytes(16));
    const timestamp = canonicalTimestamp(new Date(this.clock().getTime() + this.clockOffsetMs));
    const canonical = canonicalRequest({
      method,
      authority: new URL(identity.serverOrigin).host,
      path,
      query: "",
      body: encoder.encode(body ?? ""),
      deviceId: identity.deviceId,
      keyVersion: identity.keyVersion,
      audience: "jarvis-api",
      timestamp,
      nonce,
      sessionToken,
    });
    const headers: Record<string, string> = {
      "X-Jarvis-Audience": "jarvis-api",
      "X-Jarvis-Date": timestamp,
      "X-Jarvis-Device": identity.deviceId,
      "X-Jarvis-Key-Version": String(identity.keyVersion),
      "X-Jarvis-Nonce": nonce,
      "X-Jarvis-Signature": encodeBase64Url(
        ed25519.sign(canonical, decodeBase64Url(identity.privateSeed)),
      ),
    };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (sessionToken !== null) headers.Authorization = `Bearer ${sessionToken}`;
    const response = await this.fetcher(`${identity.serverOrigin}${path}`, {
      method,
      headers,
      ...(body === undefined ? {} : { body }),
    });
    const offsetChanged = this.observeServerTime(response);
    if (response.status === 401 && retryForClock && offsetChanged) {
      return this.signedRequest(identity, method, path, body, sessionToken, false);
    }
    return response;
  }

  private observeServerTime(response: ResponseLike): boolean {
    const header = response.headers.get("date");
    if (header === null) return false;
    const serverTime = new Date(header).getTime();
    if (!Number.isFinite(serverTime)) return false;
    const nextOffset = serverTime - this.clock().getTime();
    if (Math.abs(nextOffset) > 24 * 60 * 60 * 1000) return false;
    const changed = Math.abs(nextOffset - this.clockOffsetMs) >= 1_000;
    this.clockOffsetMs = nextOffset;
    return changed;
  }
}

function canonicalTimestamp(value: Date): string {
  return value.toISOString().replace(/\.(\d{3})Z$/, (_match, milliseconds: string) => {
    return `.${milliseconds}000Z`;
  });
}

function asRecord(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new MobileApiError(502, "invalid_json_response");
  }
  return value as Record<string, unknown>;
}
