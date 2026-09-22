import { sha256 } from "@noble/hashes/sha2.js";

const encoder = new TextEncoder();
const authorityPattern = /^(?:[a-z0-9.-]+|\[[0-9a-f:]+\])(?::[0-9]{1,5})?$/;
const noncePattern = /^[A-Za-z0-9_-]{22,128}$/;
const base64UrlAlphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";

export type CanonicalSignedRequest = Readonly<{
  method: string;
  authority: string;
  path: string;
  query: string;
  body: Uint8Array;
  deviceId: string;
  keyVersion: number;
  audience: "jarvis-api";
  timestamp: string;
  nonce: string;
  sessionToken: string | null;
}>;

export type EnrollmentProof = Readonly<{
  enrollmentId: string;
  challenge: string;
  publicKey: string;
  protocolVersion: "1" | "2";
  serverOrigin?: string;
}>;

export type RotationProof = Readonly<{
  deviceId: string;
  currentKeyVersion: number;
  newPublicKey: string;
}>;

export function canonicalRequest(request: CanonicalSignedRequest): Uint8Array {
  const method = request.method.toUpperCase();
  const authority = request.authority.toLowerCase();
  if (!/^[A-Z]{1,16}$/.test(method)) {
    throw new Error("invalid HTTP method");
  }
  if (!authorityPattern.test(authority)) {
    throw new Error("invalid HTTP authority");
  }
  const port = authority.slice(authority.lastIndexOf(":") + 1);
  if (/^[0-9]+$/.test(port) && Number(port) > 65_535) {
    throw new Error("invalid HTTP authority port");
  }
  if (!request.path.startsWith("/") || /[#\n]/.test(request.path)) {
    throw new Error("invalid raw request path");
  }
  if (/[#\n]/.test(request.query)) {
    throw new Error("invalid raw query");
  }
  if (!request.deviceId || request.deviceId.includes("\n")) {
    throw new Error("invalid device ID");
  }
  if (!Number.isSafeInteger(request.keyVersion) || request.keyVersion < 1) {
    throw new Error("invalid key version");
  }
  if (request.audience !== "jarvis-api") {
    throw new Error("invalid audience");
  }
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$/.test(request.timestamp)) {
    throw new Error("timestamp must be canonical UTC with microseconds");
  }
  if (!noncePattern.test(request.nonce)) {
    throw new Error("invalid nonce");
  }
  const bodyDigest = encodeBase64Url(sha256(request.body));
  const tokenDigest =
    request.sessionToken === null
      ? "-"
      : encodeBase64Url(sha256(encoder.encode(request.sessionToken)));
  return encodeProof("jarvis-http-signature-v1", [
    ["@method", method],
    ["@authority", authority],
    ["@path", request.path],
    ["@query", request.query],
    ["content-digest", `sha-256=:${bodyDigest}:`],
    ["x-jarvis-date", request.timestamp],
    ["x-jarvis-nonce", request.nonce],
    ["x-jarvis-audience", request.audience],
    ["x-jarvis-device", request.deviceId],
    ["x-jarvis-key-version", String(request.keyVersion)],
    ["authorization-digest", tokenDigest],
  ]);
}

export function buildEnrollmentProof(input: EnrollmentProof): Uint8Array {
  if (input.protocolVersion === "1") {
    if (input.serverOrigin !== undefined) {
      throw new Error("enrollment v1 cannot bind a server origin");
    }
    return encodeValues("jarvis-enrollment-v1", [
      input.enrollmentId,
      input.challenge,
      input.publicKey,
      input.protocolVersion,
    ]);
  }
  if (input.serverOrigin === undefined) {
    throw new Error("enrollment v2 requires a server origin");
  }
  return encodeValues("jarvis-enrollment-v2", [
    input.enrollmentId,
    input.challenge,
    input.publicKey,
    input.protocolVersion,
    input.serverOrigin,
  ]);
}

export function buildRotationProof(input: RotationProof): Uint8Array {
  if (!input.deviceId || input.deviceId.includes("\n")) {
    throw new Error("invalid device ID");
  }
  if (!Number.isSafeInteger(input.currentKeyVersion) || input.currentKeyVersion < 1) {
    throw new Error("invalid key version");
  }
  if (!/^[A-Za-z0-9_-]{43}$/.test(input.newPublicKey)) {
    throw new Error("invalid new public key");
  }
  return encodeValues("jarvis-key-rotation-v1", [
    input.deviceId,
    String(input.currentKeyVersion),
    input.newPublicKey,
  ]);
}

export function encodeBase64Url(value: Uint8Array): string {
  let output = "";
  for (let index = 0; index < value.length; index += 3) {
    const first = value[index] ?? 0;
    const second = value[index + 1] ?? 0;
    const third = value[index + 2] ?? 0;
    const combined = (first << 16) | (second << 8) | third;
    output += base64UrlAlphabet[(combined >> 18) & 63];
    output += base64UrlAlphabet[(combined >> 12) & 63];
    if (index + 1 < value.length) output += base64UrlAlphabet[(combined >> 6) & 63];
    if (index + 2 < value.length) output += base64UrlAlphabet[combined & 63];
  }
  return output;
}

export function decodeBase64Url(value: string): Uint8Array {
  if (!value || value.includes("=") || !/^[A-Za-z0-9_-]+$/.test(value)) {
    throw new Error("invalid canonical base64url");
  }
  const output: number[] = [];
  for (let index = 0; index < value.length; index += 4) {
    const chunk = value.slice(index, index + 4);
    let combined = 0;
    for (const character of chunk) {
      combined = (combined << 6) | base64UrlAlphabet.indexOf(character);
    }
    combined <<= (4 - chunk.length) * 6;
    output.push((combined >> 16) & 255);
    if (chunk.length >= 3) output.push((combined >> 8) & 255);
    if (chunk.length === 4) output.push(combined & 255);
  }
  const decoded = Uint8Array.from(output);
  if (encodeBase64Url(decoded) !== value) {
    throw new Error("non-canonical base64url");
  }
  return decoded;
}

function encodeProof(
  profile: string,
  components: readonly (readonly [string, string])[],
): Uint8Array {
  const chunks = [encoder.encode(`${profile}\n`)];
  for (const [name, value] of components) {
    const encoded = encoder.encode(value);
    chunks.push(encoder.encode(`${name}:${encoded.length}:`), encoded, encoder.encode("\n"));
  }
  return concatenate(chunks);
}

function encodeValues(profile: string, values: readonly string[]): Uint8Array {
  const chunks = [encoder.encode(`${profile}\n`)];
  for (const value of values) {
    const encoded = encoder.encode(value);
    chunks.push(encoder.encode(`${encoded.length}:`), encoded, encoder.encode("\n"));
  }
  return concatenate(chunks);
}

function concatenate(chunks: readonly Uint8Array[]): Uint8Array {
  const length = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const output = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    output.set(chunk, offset);
    offset += chunk.length;
  }
  return output;
}
