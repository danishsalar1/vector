import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import App from "../App";

describe("App", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("renders VECTOR header and service subtitle", () => {
    globalThis.fetch = vi.fn().mockImplementation(() => new Promise(() => {}));

    render(<App />);

    expect(screen.getByRole("heading", { level: 1, name: "VECTOR" })).toBeInTheDocument();
    expect(screen.getByText("Local Diagnostic Service")).toBeInTheDocument();
  });
});
