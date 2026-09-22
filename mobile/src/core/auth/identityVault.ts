import { ed25519 } from "@noble/curves/ed25519.js";

import { decodeBase64Url, encodeBase64Url } from "@/core/crypto/canonicalRequest";

import { normalizeServerOrigin } from "./origin";

const identityKey = "jarvis.mobile.identity.v1";
const pendingRotationKey = "jarvis.mobile.identity.rotation.v1";

export interface SecureKeyValueStore {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
  delete(key: string): Promise<void>;
}

export type MobileIdentity = Readonly<{
  schemaVersion: 1;
  serverOrigin: string;
  privateSeed: string;
  publicKey: string;
  deviceId: string;
  keyVersion: number;
  enrollmentProtocolVersion: "2";
  enrolledAt: string;
}>;

export type DeviceIdentitySummary = Readonly<{
  serverOrigin: string;
  deviceId: string;
  enrolledAt: string;
}>;

export function identitySummary(identity: MobileIdentity): DeviceIdentitySummary {
  return {
    serverOrigin: identity.serverOrigin,
    deviceId: identity.deviceId,
    enrolledAt: identity.enrolledAt,
  };
}

export class CorruptIdentityError extends Error {
  constructor() {
    super("stored mobile identity is invalid");
    this.name = "CorruptIdentityError";
  }
}

export class IdentityVault {
  constructor(
    private readonly storage: SecureKeyValueStore,
    private readonly options: Readonly<{ allowInsecureLoopback?: boolean }> = {},
  ) {}

  async load(): Promise<MobileIdentity | null> {
    const serialized = await this.storage.get(identityKey);
    return serialized === null ? null : this.parse(serialized);
  }

  async loadPendingRotation(): Promise<MobileIdentity | null> {
    const serialized = await this.storage.get(pendingRotationKey);
    return serialized === null ? null : this.parse(serialized);
  }

  async save(identity: MobileIdentity): Promise<void> {
    this.validate(identity);
    await this.storage.set(identityKey, JSON.stringify(identity));
  }

  async stageRotation(current: MobileIdentity, next: MobileIdentity): Promise<void> {
    this.validate(current);
    this.validate(next);
    const stored = await this.load();
    if (
      stored === null ||
      stored.serverOrigin !== current.serverOrigin ||
      stored.deviceId !== current.deviceId ||
      stored.keyVersion !== current.keyVersion ||
      stored.publicKey !== current.publicKey ||
      stored.privateSeed !== current.privateSeed ||
      next.serverOrigin !== current.serverOrigin ||
      next.deviceId !== current.deviceId ||
      next.enrolledAt !== current.enrolledAt ||
      next.keyVersion !== current.keyVersion + 1 ||
      next.publicKey === current.publicKey
    ) {
      throw new CorruptIdentityError();
    }
    await this.storage.set(pendingRotationKey, JSON.stringify(next));
  }

  async commitRotation(): Promise<MobileIdentity> {
    const current = await this.load();
    const pending = await this.loadPendingRotation();
    if (current === null || pending === null) throw new CorruptIdentityError();
    if (
      current.serverOrigin !== pending.serverOrigin ||
      current.deviceId !== pending.deviceId ||
      current.enrolledAt !== pending.enrolledAt ||
      (pending.keyVersion !== current.keyVersion + 1 &&
        !(pending.keyVersion === current.keyVersion && pending.publicKey === current.publicKey))
    ) {
      throw new CorruptIdentityError();
    }
    if (pending.keyVersion !== current.keyVersion) await this.save(pending);
    await this.storage.delete(pendingRotationKey);
    return pending;
  }

  async discardPendingRotation(): Promise<void> {
    await this.storage.delete(pendingRotationKey);
  }

  async erase(): Promise<void> {
    let failure: unknown;
    try {
      await this.storage.delete(identityKey);
    } catch (error) {
      failure = error;
    }
    try {
      await this.storage.delete(pendingRotationKey);
    } catch (error) {
      failure ??= error;
    }
    if (failure !== undefined) throw failure;
  }

  private parse(serialized: string): MobileIdentity {
    try {
      const value = JSON.parse(serialized) as Record<string, unknown>;
      const serverOrigin = String(value.serverOrigin);
      const identity: MobileIdentity = {
        schemaVersion: value.schemaVersion as 1,
        serverOrigin: normalizeServerOrigin(serverOrigin, this.options),
        privateSeed: String(value.privateSeed),
        publicKey: String(value.publicKey),
        deviceId: String(value.deviceId),
        keyVersion: Number(value.keyVersion),
        enrollmentProtocolVersion: value.enrollmentProtocolVersion as "2",
        enrolledAt: new Date(String(value.enrolledAt)).toISOString(),
      };
      if (identity.serverOrigin !== serverOrigin) throw new Error("identity origin changed");
      this.validate(identity);
      return identity;
    } catch {
      throw new CorruptIdentityError();
    }
  }

  private validate(identity: MobileIdentity): void {
    try {
      const seed = decodeBase64Url(identity.privateSeed);
      if (
        identity.schemaVersion !== 1 ||
        seed.length !== 32 ||
        !/^device:[A-Za-z0-9._:-]+$/.test(identity.deviceId) ||
        !Number.isInteger(identity.keyVersion) ||
        identity.keyVersion < 1 ||
        identity.enrollmentProtocolVersion !== "2" ||
        !Number.isFinite(new Date(identity.enrolledAt).getTime()) ||
        new Date(identity.enrolledAt).toISOString() !== identity.enrolledAt ||
        encodeBase64Url(ed25519.getPublicKey(seed)) !== identity.publicKey ||
        normalizeServerOrigin(identity.serverOrigin, this.options) !== identity.serverOrigin
      ) {
        throw new Error("identity invariant failed");
      }
    } catch {
      throw new CorruptIdentityError();
    }
  }
}
