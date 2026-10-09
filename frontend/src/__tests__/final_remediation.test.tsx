import { afterEach, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { LiveDiagnosticProvider } from "../providers/LiveDiagnosticProvider";
import { AndroidStatus } from "../components/AndroidStatus";

afterEach(() => vi.unstubAllGlobals());

function respond(states: string[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        count: states.length,
        devices: states.map((state, i) => ({
          device_id: `android-test${i}`,
          platform: "ANDROID",
          connection_state: state,
          identity: null,
        })),
      }),
    })
  );
}

async function detect(states: string[]) {
  respond(states);
  render(<AndroidStatus provider={new LiveDiagnosticProvider()} />);
  fireEvent.click(screen.getByRole("button", { name: /detect android/i }));
}

it("explains an UNKNOWN connection state instead of rendering a blank message", async () => {
  await detect(["UNKNOWN"]);
  const box = await screen.findByTestId("android-unknown");
  expect(box.textContent).toMatch(/could not determine the connection state/i);
  expect(box.textContent).toMatch(/no diagnostics can run/i);
  expect(screen.queryByRole("button", { name: /run battery/i })).not.toBeInTheDocument();
});

it("explains MISSING_DRIVER without inventing a cause beyond the agent report", async () => {
  await detect(["MISSING_DRIVER"]);
  const box = await screen.findByTestId("android-missing-driver");
  expect(box.textContent).toMatch(/agent reports/i);
  expect(box.textContent).toMatch(/driver/i);
  expect(screen.queryByRole("button", { name: /run battery/i })).not.toBeInTheDocument();
});

it("does not claim ADB reported OFFLINE when the record may simply be disconnected", async () => {
  await detect(["OFFLINE"]);
  const box = await screen.findByTestId("android-offline");
  expect(box.textContent).not.toMatch(/listed as offline by ADB/i);
  expect(box.textContent).toMatch(/does not say which/i);
  expect(box.textContent).toMatch(/disconnected/i);
});

it("shows the state name for any state it cannot interpret, never a blank box", async () => {
  await detect(["NOT_TRUSTED"]);
  const box = await screen.findByTestId("android-discovery-error");
  expect(box.textContent).toMatch(/NOT_TRUSTED/);
  expect(box.textContent?.trim().length).toBeGreaterThan(20);
});
