import { afterEach, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { LiveDiagnosticProvider } from "../providers/LiveDiagnosticProvider";
import { AndroidStatus } from "../components/AndroidStatus";

afterEach(() => vi.unstubAllGlobals());

function respond(states: string[]) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200,
    json: async () => ({ count: states.length + 1, devices: [
      ...states.map((state, i) => ({ device_id: `android-test${i}`, platform: "ANDROID", connection_state: state, identity: null })),
      { device_id: "ios-test", platform: "IOS", connection_state: "CONNECTED", identity: null },
    ] }),
  }));
}

it.each([
  [["CONNECTED"], "DEVICE", 1],
  [["OFFLINE", "CONNECTED"], "DEVICE", 1],
  [["UNAUTHORIZED"], "UNAUTHORIZED", 1],
  [["CONNECTED", "CONNECTED"], "MULTIPLE_DEVICES", 2],
  [["UNAUTHORIZED", "CONNECTED"], "MULTIPLE_DEVICES", 2],
  [["UNAUTHORIZED", "UNAUTHORIZED"], "MULTIPLE_DEVICES", 2],
  [["OFFLINE"], "OFFLINE", 1],
  [[], "NO_DEVICE", 0],
  [["UNKNOWN"], "UNKNOWN", 1],
  [["MISSING_DRIVER"], "MISSING_DRIVER", 1],
] as const)("active selection for %j", async (states, expected, count) => {
  respond([...states]);
  const result = await new LiveDiagnosticProvider().discoverAndroidDevices();
  expect(result.data?.state).toBe(expected);
  expect(result.data?.count).toBe(count);
});

it("renders a runnable battery action after an A-to-B phone swap", async () => {
  respond(["OFFLINE", "CONNECTED"]);
  render(<AndroidStatus provider={new LiveDiagnosticProvider()} />);
  fireEvent.click(screen.getByRole("button", { name: /detect android/i }));
  expect(await screen.findByRole("button", { name: /run battery/i })).toBeEnabled();
  expect(screen.queryByText(/multiple.*devices/i)).not.toBeInTheDocument();
});
