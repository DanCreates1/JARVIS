import { MobileApiError } from "@/core/api/signedApiClient";

export type ConnectionPhase =
  | "unenrolled"
  | "unverified"
  | "connecting"
  | "connected"
  | "disconnected"
  | "offline"
  | "reconnecting"
  | "expired-session"
  | "permission-denied"
  | "recoverable-error"
  | "unrecoverable-error";

type Presentation = Readonly<{
  label: string;
  detail: string;
  tone: "ready" | "offline" | "error" | "neutral";
}>;

const presentations: Record<ConnectionPhase, Presentation> = {
  unenrolled: {
    label: "Not connected",
    detail: "Pair this device in Settings to reach JARVIS Core.",
    tone: "neutral",
  },
  unverified: {
    label: "Connection not checked",
    detail: "Device enrolled. Check Core status to verify signed access.",
    tone: "neutral",
  },
  connecting: {
    label: "Connecting",
    detail: "Checking signed access to JARVIS Core.",
    tone: "neutral",
  },
  connected: {
    label: "Connected at last check",
    detail: "Signed Core status request passed. Check again after a network change.",
    tone: "ready",
  },
  disconnected: {
    label: "Disconnected",
    detail: "Session ended. Device enrollment remains; check status to reconnect.",
    tone: "neutral",
  },
  offline: {
    label: "Core offline",
    detail: "Check Tailscale and Core, then try again. No work is queued.",
    tone: "offline",
  },
  reconnecting: {
    label: "Reconnecting",
    detail: "Trying signed Core status again. No work is queued.",
    tone: "neutral",
  },
  "expired-session": {
    label: "Session expired",
    detail: "Creating a new signed session before checking Core.",
    tone: "offline",
  },
  "permission-denied": {
    label: "Access denied",
    detail: "Core rejected this device or its scope. Check enrollment on Core.",
    tone: "error",
  },
  "recoverable-error": {
    label: "Connection error",
    detail: "Core could not complete this request. Retry when available.",
    tone: "offline",
  },
  "unrecoverable-error": {
    label: "Device setup error",
    detail: "Stored identity or Core response is invalid. Erase credentials and re-enroll.",
    tone: "error",
  },
};

export function connectionPresentation(phase: ConnectionPhase): Presentation {
  return presentations[phase];
}

export function classifyConnectionError(error: unknown): ConnectionPhase {
  if (error instanceof MobileApiError) {
    if (error.code.startsWith("invalid_")) return "unrecoverable-error";
    if (error.status === 401 || error.status === 403) return "permission-denied";
    return "recoverable-error";
  }
  if (error instanceof TypeError) return "offline";
  return "recoverable-error";
}
