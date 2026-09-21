import IndexScreen from "../app";
import { parseAppEnvironment } from "../src/config/appConfig";
import { renderApp } from "../src/testing/render";

describe("M1A native foundation", () => {
  it("renders an honest offline-safe launch state", () => {
    const screen = renderApp(<IndexScreen />);

    expect(screen.getByText("JARVIS")).toBeOnTheScreen();
    expect(screen.getByText("Foundation ready")).toBeOnTheScreen();
    expect(screen.getByText("Offline-safe shell. No Core connection configured.")).toBeOnTheScreen();
    expect(
      screen.getByText(
        "Authentication, remote APIs, telemetry, and device permissions are not active.",
      ),
    ).toBeOnTheScreen();
  });

  it("fails closed to development for unknown runtime metadata", () => {
    expect(parseAppEnvironment("production")).toBe("production");
    expect(parseAppEnvironment("unknown")).toBe("development");
    expect(parseAppEnvironment(undefined)).toBe("development");
  });
});
