import { ed25519 } from "@noble/curves/ed25519.js";

import { SignedApiClient, type SessionCredential } from "@/core/api/signedApiClient";
import type { Clock } from "@/core/api/types";
import { encodeBase64Url } from "@/core/crypto/canonicalRequest";

import {
  IdentityVault,
  identitySummary,
  type DeviceIdentitySummary,
  type MobileIdentity,
} from "./identityVault";
import type { RandomSource } from "./platform";
import { parseEnrollmentTicket } from "./ticket";

const refreshWindowMs = 30_000;
const sessionScopes = ["client.status.read", "session.revoke"] as const;
const rotationScopes = ["key.rotate"] as const;

export type PairingResult = Readonly<{
  identity: DeviceIdentitySummary;
}>;

export class MobileAuthClient {
  private session: SessionCredential | null = null;

  constructor(
    private readonly vault: IdentityVault,
    private readonly api: SignedApiClient,
    private readonly random: RandomSource,
    private readonly clock: Clock = () => new Date(),
    private readonly options: Readonly<{ allowInsecureLoopback?: boolean }> = {},
  ) {}

  async restoreIdentity(): Promise<DeviceIdentitySummary | null> {
    const identity = await this.vault.load();
    return identity === null ? null : identitySummary(identity);
  }

  async pair(ticketPayload: string): Promise<PairingResult> {
    const ticket = parseEnrollmentTicket(ticketPayload, this.options);
    if (new Date(ticket.expiresAt).getTime() <= this.clock().getTime()) {
      throw new Error("enrollment ticket has expired");
    }
    const existing = await this.vault.load();
    if (existing !== null && existing.serverOrigin === ticket.serverOrigin) {
      throw new Error("device is already enrolled with this Core; erase before re-enrolling");
    }
    if (existing !== null && existing.serverOrigin !== ticket.serverOrigin) {
      this.session = null;
      await this.vault.erase();
    }
    const privateSeed = await this.random.bytes(32);
    if (privateSeed.length !== 32) throw new Error("secure random source returned wrong length");
    const publicKey = encodeBase64Url(ed25519.getPublicKey(privateSeed));
    const device = await this.api.completeEnrollment(ticket, privateSeed);
    const identity: MobileIdentity = {
      schemaVersion: 1,
      serverOrigin: ticket.serverOrigin,
      privateSeed: encodeBase64Url(privateSeed),
      publicKey,
      deviceId: device.id,
      keyVersion: device.keyVersion,
      enrollmentProtocolVersion: "2",
      enrolledAt: new Date(device.enrolledAt).toISOString(),
    };
    await this.vault.save(identity);
    const session = await this.api.createSession(identity, sessionScopes);
    this.session = session;
    return { identity: identitySummary(identity) };
  }

  async ensureSession(requestedScopes: readonly string[]): Promise<SessionCredential> {
    if (requestedScopes.length === 0 || new Set(requestedScopes).size !== requestedScopes.length) {
      throw new Error("requested scopes must be non-empty and unique");
    }
    const identity = await this.resolvePendingRotation();
    return this.ensureSessionFor(identity, requestedScopes);
  }

  async rotateKey(): Promise<PairingResult> {
    const identity = await this.resolvePendingRotation();
    const session = await this.ensureSessionFor(identity, rotationScopes);
    const nextSeed = await this.random.bytes(32);
    if (nextSeed.length !== 32) throw new Error("secure random source returned wrong length");
    const nextIdentity: MobileIdentity = {
      ...identity,
      privateSeed: encodeBase64Url(nextSeed),
      publicKey: encodeBase64Url(ed25519.getPublicKey(nextSeed)),
      keyVersion: identity.keyVersion + 1,
    };
    await this.vault.stageRotation(identity, nextIdentity);
    this.session = null;
    await this.api.rotateKey(identity, session, nextSeed);
    const committed = await this.vault.commitRotation();
    return { identity: identitySummary(committed) };
  }

  private async ensureSessionFor(
    identity: MobileIdentity,
    requestedScopes: readonly string[],
  ): Promise<SessionCredential> {
    if (
      this.session !== null &&
      requestedScopes.every((scope) => this.session?.scopes.includes(scope)) &&
      new Date(this.session.expiresAt).getTime() > this.clock().getTime() + refreshWindowMs
    ) {
      return this.session;
    }
    const session = await this.api.createSession(identity, requestedScopes);
    this.session = session;
    return session;
  }

  async getStatus(): Promise<unknown> {
    const identity = await this.resolvePendingRotation();
    const session = await this.ensureSessionFor(identity, sessionScopes);
    return this.api.getStatus(identity, session);
  }

  async logout(): Promise<void> {
    const session = this.session;
    this.session = null;
    if (session === null) return;
    const identity = await this.vault.load();
    if (identity !== null) await this.api.revokeSession(identity, session);
  }

  async eraseCredentials(): Promise<void> {
    const session = this.session;
    this.session = null;
    try {
      const identity = await this.vault.load();
      if (identity !== null && session !== null) {
        await this.api.revokeSession(identity, session);
      }
    } finally {
      await this.vault.erase();
    }
  }

  private async requireIdentity(): Promise<MobileIdentity> {
    const identity = await this.vault.load();
    if (identity === null) throw new Error("device is not enrolled");
    return identity;
  }

  private async resolvePendingRotation(): Promise<MobileIdentity> {
    const current = await this.requireIdentity();
    const pending = await this.vault.loadPendingRotation();
    if (pending === null) return current;
    if (pending.keyVersion === current.keyVersion && pending.publicKey === current.publicKey) {
      await this.vault.discardPendingRotation();
      return current;
    }
    this.session = null;
    try {
      const session = await this.api.createSession(pending, sessionScopes);
      const committed = await this.vault.commitRotation();
      this.session = session;
      return committed;
    } catch {
      try {
        const session = await this.api.createSession(current, sessionScopes);
        await this.vault.discardPendingRotation();
        this.session = session;
        return current;
      } catch {
        throw new Error("pending key rotation could not be reconciled with Core");
      }
    }
  }
}
