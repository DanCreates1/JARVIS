import { ed25519 } from "@noble/curves/ed25519.js";

import { decodeBase64Url, encodeBase64Url } from "@/core/crypto/canonicalRequest";

import { normalizeServerOrigin } from "./origin";

const identityKey = "jarvis.mobile.identity.v1";

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
    if (serialized === null) return null;
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
      const seed = decodeBase64Url(identity.privateSeed);
      if (
        identity.schemaVersion !== 1 ||
        seed.length !== 32 ||
        !/^device:[A-Za-z0-9._:-]+$/.test(identity.deviceId) ||
        !Number.isInteger(identity.keyVersion) ||
        identity.keyVersion < 1 ||
        identity.enrollmentProtocolVersion !== "2" ||
        identity.serverOrigin !== serverOrigin ||
        encodeBase64Url(ed25519.getPublicKey(seed)) !== identity.publicKey
      ) {
        throw new Error("identity invariant failed");
      }
      return identity;
    } catch {
      throw new CorruptIdentityError();
    }
  }

  async save(identity: MobileIdentity): Promise<void> {
    try {
      const seed = decodeBase64Url(identity.privateSeed);
      if (
        seed.length !== 32 ||
        encodeBase64Url(ed25519.getPublicKey(seed)) !== identity.publicKey ||
        normalizeServerOrigin(identity.serverOrigin, this.options) !== identity.serverOrigin
      ) {
        throw new Error("identity invariant failed");
      }
    } catch {
      throw new CorruptIdentityError();
    }
    await this.storage.set(identityKey, JSON.stringify(identity));
  }

  async erase(): Promise<void> {
    await this.storage.delete(identityKey);
  }
}
