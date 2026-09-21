import type { DeviceIdentitySummary } from "./identityVault";

export type AuthState =
  | Readonly<{ status: "loading" }>
  | Readonly<{ status: "unenrolled" }>
  | Readonly<{ status: "pairing" }>
  | Readonly<{ status: "enrolled"; identity: DeviceIdentitySummary; online: boolean }>
  | Readonly<{ status: "error"; message: string }>;

export type AuthEvent =
  | Readonly<{ type: "RESTORED"; identity: DeviceIdentitySummary | null }>
  | Readonly<{ type: "PAIR_STARTED" }>
  | Readonly<{ type: "PAIR_SUCCEEDED"; identity: DeviceIdentitySummary }>
  | Readonly<{ type: "CONNECTIVITY_CHANGED"; online: boolean }>
  | Readonly<{ type: "ERASED" }>
  | Readonly<{ type: "FAILED"; message: string }>;

export function authReducer(state: AuthState, event: AuthEvent): AuthState {
  switch (event.type) {
    case "RESTORED":
      return event.identity === null
        ? { status: "unenrolled" }
        : { status: "enrolled", identity: event.identity, online: false };
    case "PAIR_STARTED":
      return { status: "pairing" };
    case "PAIR_SUCCEEDED":
      return { status: "enrolled", identity: event.identity, online: true };
    case "CONNECTIVITY_CHANGED":
      return state.status === "enrolled" ? { ...state, online: event.online } : state;
    case "ERASED":
      return { status: "unenrolled" };
    case "FAILED":
      return { status: "error", message: event.message };
  }
}
