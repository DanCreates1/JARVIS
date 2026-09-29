import ChatScreen from "../app";
import GarminScreen from "../app/garmin";
import { parseAppEnvironment } from "../src/config/appConfig";
import { renderApp } from "../src/testing/render";
import { StatusBanner } from "../src/ui/StatusBanner";

describe("MVP 1 shell", () => {
  it("renders honest Chat and Garmin empty states", () => {
    const chat = renderApp(<ChatScreen />);
    expect(chat.getByText("Chat")).toBeOnTheScreen();
    expect(chat.getByText("No conversation yet")).toBeOnTheScreen();
    chat.unmount();

    const garmin = renderApp(<GarminScreen />);
    expect(garmin.getByText("Garmin")).toBeOnTheScreen();
    expect(garmin.getByText("No Garmin data connected")).toBeOnTheScreen();
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
