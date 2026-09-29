import { fireEvent, waitFor } from "@testing-library/react-native";
import type { ReactNode } from "react";
import { Alert } from "react-native";

import PairScreen, { type PairingClient } from "../app/pair";
import { MobileApiError } from "@/core/api/signedApiClient";
import type { DeviceIdentitySummary } from "@/core/auth/identityVault";
import { renderApp } from "@/testing/render";

const mockRequestPermission = jest.fn();
let mockPermissionGranted = false;

jest.mock("expo-camera", () => {
  const React = jest.requireActual("react") as typeof import("react");
  const { Text, View } = jest.requireActual("react-native") as typeof import("react-native");
  return {
    CameraView: ({ onBarcodeScanned }: { onBarcodeScanned(result: { data: string }): void }) =>
      React.createElement(
        View,
        { accessibilityLabel: "Enrollment QR scanner" },
        React.createElement(
          Text,
          { onPress: () => onBarcodeScanned({ data: "scanned-ticket" }) },
          "Simulate QR",
        ),
      ),
    useCameraPermissions: () => [{ granted: mockPermissionGranted }, mockRequestPermission],
  };
});

jest.mock("expo-router", () => ({
  Link: ({ children }: { children: ReactNode }) => children,
}));

const identity: DeviceIdentitySummary = {
  serverOrigin: "https://jarvis.example",
  deviceId: "device:test",
  enrolledAt: "2026-09-21T12:00:00.000Z",
};

function client(overrides: Partial<PairingClient> = {}): jest.Mocked<PairingClient> {
  return {
    restoreIdentity: jest.fn().mockResolvedValue(null),
    pair: jest.fn().mockResolvedValue({ identity }),
    getStatus: jest.fn().mockResolvedValue({ online: true }),
    logout: jest.fn().mockResolvedValue(undefined),
    rotateKey: jest.fn().mockResolvedValue({ identity }),
    eraseCredentials: jest.fn().mockResolvedValue(undefined),
    isSessionExpired: jest.fn().mockReturnValue(false),
    ...overrides,
  } as jest.Mocked<PairingClient>;
}

describe("pairing screen", () => {
  beforeEach(() => {
    mockPermissionGranted = false;
    mockRequestPermission.mockReset();
  });

  it("restores an existing identity and erases it", async () => {
    const auth = client({ restoreIdentity: jest.fn().mockResolvedValue(identity) });
    const screen = renderApp(<PairScreen authClient={auth} />);
    expect(screen.getByLabelText("Loading stored identity")).toBeOnTheScreen();
    await waitFor(() => expect(screen.getByText("Device enrolled")).toBeOnTheScreen());
    expect(screen.getByText("Bound to https://jarvis.example")).toBeOnTheScreen();
    fireEvent.press(screen.getByText("Erase local credentials"));
    await waitFor(() => expect(auth.eraseCredentials).toHaveBeenCalledTimes(1));
    expect(screen.queryByText("Device enrolled")).not.toBeOnTheScreen();
  });

  it("pairs from manually pasted ticket content", async () => {
    const auth = client();
    const screen = renderApp(<PairScreen authClient={auth} />);
    await waitFor(() =>
      expect(screen.getByLabelText("Enrollment ticket JSON")).toHaveProp("editable", true),
    );
    fireEvent.changeText(screen.getByLabelText("Enrollment ticket JSON"), "ticket-json");
    fireEvent.press(screen.getByText("Pair device"));
    await waitFor(() => expect(auth.pair).toHaveBeenCalledWith("ticket-json"));
    expect(screen.getByText("Device enrolled")).toBeOnTheScreen();
    expect(screen.queryByLabelText("Enrollment ticket JSON")).not.toBeOnTheScreen();
  });

  it("shows restore and pairing failures without exposing ticket content", async () => {
    const restoreFailure = client({
      restoreIdentity: jest.fn().mockRejectedValue(new Error("secret detail")),
    });
    const first = renderApp(<PairScreen authClient={restoreFailure} />);
    await waitFor(() =>
      expect(first.getByText("Stored identity is unreadable. Erase it.")).toBeOnTheScreen(),
    );
    first.unmount();

    const auth = client({ pair: jest.fn().mockRejectedValue(new Error("ticket rejected")) });
    const second = renderApp(<PairScreen authClient={auth} />);
    await waitFor(() =>
      expect(second.getByLabelText("Enrollment ticket JSON")).toHaveProp("editable", true),
    );
    fireEvent.changeText(second.getByLabelText("Enrollment ticket JSON"), "sensitive-ticket");
    fireEvent.press(second.getByText("Pair device"));
    await waitFor(() => expect(second.getByText("ticket rejected")).toBeOnTheScreen());
    expect(second.queryByText("sensitive-ticket")).not.toBeOnTheScreen();
  });

  it("handles denied camera permission and accepts a scanned QR payload", async () => {
    mockRequestPermission.mockResolvedValueOnce({ granted: false });
    const denied = renderApp(<PairScreen authClient={client()} />);
    await waitFor(() => expect(denied.getByText("Scan QR")).toBeOnTheScreen());
    fireEvent.press(denied.getByText("Scan QR"));
    await waitFor(() =>
      expect(
        denied.getByText("Camera permission denied. Paste ticket JSON instead."),
      ).toBeOnTheScreen(),
    );
    denied.unmount();

    mockPermissionGranted = true;
    const allowed = renderApp(<PairScreen authClient={client()} />);
    await waitFor(() => expect(allowed.getByText("Scan QR")).toBeOnTheScreen());
    fireEvent.press(allowed.getByText("Scan QR"));
    expect(allowed.getByLabelText("Enrollment QR scanner")).toBeOnTheScreen();
    fireEvent.press(allowed.getByText("Simulate QR"));
    expect(allowed.getByLabelText("Enrollment ticket JSON")).toHaveProp("value", "scanned-ticket");
  });

  it("closes an active scanner without changing credentials", async () => {
    mockPermissionGranted = true;
    const auth = client();
    const screen = renderApp(<PairScreen authClient={auth} />);
    await waitFor(() => expect(screen.getByText("Scan QR")).toBeOnTheScreen());
    fireEvent.press(screen.getByText("Scan QR"));
    fireEvent.press(screen.getByText("Cancel scan"));
    expect(screen.getByLabelText("Enrollment ticket JSON")).toBeOnTheScreen();
    expect(auth.pair).not.toHaveBeenCalled();
  });

  it("reports an unavailable remote revoke after local erase", async () => {
    const auth = client({
      restoreIdentity: jest.fn().mockResolvedValue(identity),
      eraseCredentials: jest.fn().mockRejectedValue(new Error("unavailable")),
    });
    const screen = renderApp(<PairScreen authClient={auth} />);
    await waitFor(() => expect(screen.getByText("Device enrolled")).toBeOnTheScreen());
    fireEvent.press(screen.getByText("Erase local credentials"));
    await waitFor(() =>
      expect(
        screen.getByText(
          "Local credentials erased. Remote revoke unavailable; revoke this device on Core.",
        ),
      ).toBeOnTheScreen(),
    );
  });

  it("exposes signed Core status and session logout controls", async () => {
    const auth = client({ restoreIdentity: jest.fn().mockResolvedValue(identity) });
    const screen = renderApp(<PairScreen authClient={auth} />);
    await waitFor(() => expect(screen.getByText("Check Core status")).toBeOnTheScreen());
    expect(screen.queryByLabelText("Enrollment ticket JSON")).not.toBeOnTheScreen();

    fireEvent.press(screen.getByText("Check Core status"));
    await waitFor(() => expect(auth.getStatus).toHaveBeenCalledTimes(1));
    expect(screen.getByText("Connected at last check")).toBeOnTheScreen();
    expect(
      screen.getByText("Signed Core status request passed. Check again after a network change."),
    ).toBeOnTheScreen();

    fireEvent.press(screen.getByText("Log out session"));
    await waitFor(() => expect(auth.logout).toHaveBeenCalledTimes(1));
    expect(screen.getByText("Session revoked. Device enrollment retained.")).toBeOnTheScreen();

    fireEvent.press(screen.getByText("Check Core status"));
    await waitFor(() => expect(auth.getStatus).toHaveBeenCalledTimes(2));

    fireEvent.press(screen.getByText("Disconnect"));
    await waitFor(() => expect(auth.logout).toHaveBeenCalledTimes(2));
    expect(screen.getByText("Disconnected. Device enrollment retained.")).toBeOnTheScreen();
    expect(screen.getByText("Disconnected")).toBeOnTheScreen();
  });

  it("requires confirmation before rotating the device key", async () => {
    const auth = client({ restoreIdentity: jest.fn().mockResolvedValue(identity) });
    const alert = jest.spyOn(Alert, "alert").mockImplementation((_title, _message, buttons) => {
      buttons?.find((button) => button.text === "Rotate key")?.onPress?.();
    });
    const screen = renderApp(<PairScreen authClient={auth} />);
    await waitFor(() => expect(screen.getByText("Rotate device key")).toBeOnTheScreen());
    fireEvent.press(screen.getByText("Rotate device key"));
    await waitFor(() => expect(auth.rotateKey).toHaveBeenCalledTimes(1));
    expect(
      screen.getByText("Device key rotated. Existing sessions were revoked."),
    ).toBeOnTheScreen();
    alert.mockRestore();
  });

  it("keeps credential erase available after status or logout failure", async () => {
    const auth = client({
      restoreIdentity: jest.fn().mockResolvedValue(identity),
      getStatus: jest.fn().mockRejectedValue(new TypeError("private API detail")),
      logout: jest.fn().mockRejectedValue(new Error("private revoke detail")),
    });
    const screen = renderApp(<PairScreen authClient={auth} />);
    await waitFor(() => expect(screen.getByText("Check Core status")).toBeOnTheScreen());

    fireEvent.press(screen.getByText("Check Core status"));
    await waitFor(() => expect(screen.getByText("Core offline")).toBeOnTheScreen());
    fireEvent.press(screen.getByText("Log out session"));
    await waitFor(() =>
      expect(
        screen.getByText("Session cleared locally. Remote revoke unavailable; revoke on Core."),
      ).toBeOnTheScreen(),
    );
    expect(screen.queryByText("private API detail")).not.toBeOnTheScreen();
    expect(screen.queryByText("private revoke detail")).not.toBeOnTheScreen();
    expect(screen.getByText("Erase local credentials")).toBeOnTheScreen();
  });

  it("distinguishes denied access from network loss without exposing API details", async () => {
    const auth = client({
      restoreIdentity: jest.fn().mockResolvedValue(identity),
      getStatus: jest.fn().mockRejectedValue(new MobileApiError(403, "status_failed")),
    });
    const screen = renderApp(<PairScreen authClient={auth} showBackLink={false} />);
    await waitFor(() => expect(screen.getByText("Check Core status")).toBeOnTheScreen());
    fireEvent.press(screen.getByText("Check Core status"));
    await waitFor(() => expect(screen.getByText("Access denied")).toBeOnTheScreen());
    expect(screen.queryByText("status_failed")).not.toBeOnTheScreen();
    expect(screen.queryByText("Back to Chat")).not.toBeOnTheScreen();
  });

  it("shows expired-session recovery while a new signed session is pending", async () => {
    let finishStatus: (() => void) | undefined;
    const pendingStatus = new Promise<void>((resolve) => {
      finishStatus = resolve;
    });
    const auth = client({
      restoreIdentity: jest.fn().mockResolvedValue(identity),
      isSessionExpired: jest.fn().mockReturnValue(true),
      getStatus: jest.fn().mockReturnValue(pendingStatus),
    });
    const screen = renderApp(<PairScreen authClient={auth} />);
    await waitFor(() => expect(screen.getByText("Check Core status")).toBeOnTheScreen());
    fireEvent.press(screen.getByText("Check Core status"));
    expect(screen.getByText("Session expired")).toBeOnTheScreen();
    finishStatus?.();
    await waitFor(() => expect(screen.getByText("Connected at last check")).toBeOnTheScreen());
  });
});
