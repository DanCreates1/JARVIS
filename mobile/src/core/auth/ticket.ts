import { normalizeServerOrigin } from "./origin";

const identifier = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$/;
const base64Url = /^[A-Za-z0-9_-]+$/;
const scope = /^[a-z][a-z0-9_.]{0,63}$/;

export type EnrollmentTicketV2 = Readonly<{
  id: string;
  challenge: string;
  hostId: string;
  displayName: string;
  deviceType: "phone";
  approvedScopes: readonly string[];
  riskCeiling: number;
  expiresAt: string;
  protocolVersion: "2";
  serverOrigin: string;
}>;

export function parseEnrollmentTicket(
  payload: string,
  options: Readonly<{ allowInsecureLoopback?: boolean }> = {},
): EnrollmentTicketV2 {
  let value: unknown;
  try {
    value = JSON.parse(payload);
  } catch {
    throw new Error("enrollment ticket is not valid JSON");
  }
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("enrollment ticket must be an object");
  }
  const record = value as Record<string, unknown>;
  const allowedKeys = new Set([
    "id",
    "challenge",
    "host_id",
    "display_name",
    "device_type",
    "approved_scopes",
    "risk_ceiling",
    "expires_at",
    "protocol_version",
    "server_origin",
  ]);
  if (Object.keys(record).some((key) => !allowedKeys.has(key))) {
    throw new Error("enrollment ticket contains unknown fields");
  }
  const approvedScopes = record.approved_scopes;
  if (
    !identifier.test(String(record.id ?? "")) ||
    typeof record.challenge !== "string" ||
    record.challenge.length !== 43 ||
    !base64Url.test(record.challenge) ||
    !identifier.test(String(record.host_id ?? "")) ||
    typeof record.display_name !== "string" ||
    record.display_name.length < 1 ||
    record.display_name.length > 100 ||
    record.device_type !== "phone" ||
    !Array.isArray(approvedScopes) ||
    approvedScopes.length < 1 ||
    approvedScopes.length > 16 ||
    !approvedScopes.every((item) => typeof item === "string" && scope.test(item)) ||
    new Set(approvedScopes).size !== approvedScopes.length ||
    !approvedScopes.includes("client.status.read") ||
    !Number.isInteger(record.risk_ceiling) ||
    Number(record.risk_ceiling) < 0 ||
    Number(record.risk_ceiling) > 2 ||
    record.protocol_version !== "2" ||
    typeof record.server_origin !== "string" ||
    typeof record.expires_at !== "string"
  ) {
    throw new Error("enrollment ticket fields are invalid");
  }
  const expiresAt = new Date(record.expires_at);
  if (!Number.isFinite(expiresAt.getTime())) {
    throw new Error("enrollment ticket expiry is invalid");
  }
  return {
    id: String(record.id),
    challenge: record.challenge,
    hostId: String(record.host_id),
    displayName: record.display_name,
    deviceType: "phone",
    approvedScopes,
    riskCeiling: Number(record.risk_ceiling),
    expiresAt: expiresAt.toISOString(),
    protocolVersion: "2",
    serverOrigin: normalizeServerOrigin(record.server_origin, options),
  };
}
