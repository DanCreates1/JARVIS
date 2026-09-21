import IndexScreen from "../app";
import { parseAppEnvironment } from "../src/config/appConfig";
import { renderApp } from "../src/testing/render";
import { StatusBanner } from "../src/ui/StatusBanner";

describe("M1A native foundation", () => {
  it("renders an honest offline-safe launch state", () => {
    const screen = renderApp(<IndexScreen />);

    expect(screen.getByText("JARVIS")).toBeOnTheScreen();
    expect(screen.getByText("Pairing ready")).toBeOnTheScreen();
    expect(
      screen.getByText("Offline-safe until you enroll this device with JARVIS Core."),
    ).toBeOnTheScreen();
    expect(screen.getByText("Pair this device")).toBeOnTheScreen();
    expect(
      screen.getByText(
        "Secure pairing and authenticated status are available. No telemetry or background permissions are active.",
      ),
    ).toBeOnTheScreen();
  });

  it("fails closed to development for unknown runtime metadata", () => {
    expect(parseAppEnvironment("production")).toBe("production");
    expect(parseAppEnvironment("unknown")).toBe("development");
    expect(parseAppEnvironment(undefined)).toBe("development");
  });

  it("renders an explicit offline state", () => {
    const screen = renderApp(
      <StatusBanner label="Offline" detail="No queued mutations." tone="offline" />,
    );

    expect(screen.getByText("Offline")).toBeOnTheScreen();
    expect(screen.getByText("No queued mutations.")).toBeOnTheScreen();
  });
});
