import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { DiagnosticCard } from "../components/scan/DiagnosticCard";
import { EvidenceTable } from "../components/scan/EvidenceTable";
import type { CapabilityEvidenceRecord } from "../lib/api/types";
import type { DiagnosticRow } from "../lib/scan/quickScanModel";

// Fabricated ids; measurement values are from a real Redmi Note 8 Pro scan.
function ev(field: string, raw_value: string, unit: string | null): CapabilityEvidenceRecord {
  return {
    evidence_id: `ev-${field}`,
    diagnostic_id: "memory_telemetry",
    device_id: "android-testdev0001",
    source_type: "ADB_SHELL",
    source_name: "ADB / test",
    collection_method: "adb shell cat /proc/meminfo",
    timestamp: "2026-10-11T00:00:01Z",
    raw_value,
    unit,
    reliability: null,
    metadata: { field },
  };
}

const ROW: DiagnosticRow = {
  id: "memory_telemetry",
  name: "Memory Telemetry Verification",
  status: "PASS",
  result: {
    diagnostic_id: "memory_telemetry",
    diagnostic_name: "Memory Telemetry Verification",
    category: "memory",
    status: "PASS",
    summary: "PASS confirms successful memory telemetry collection. It does not represent RAM chip hardware integrity.",
    duration_seconds: 0.06,
    evidence: [ev("mem_total_bytes", "5909782528", "bytes"), ev("mem_available_bytes", "3390156800", "bytes")],
  },
  verificationLevel: "RUNTIME_DETECTION",
  requiresProbe: false,
};

function mockViewport(narrow: boolean) {
  vi.stubGlobal(
    "matchMedia",
    (query: string) =>
      ({
        matches: narrow && query.includes("max-width: 680px"),
        media: query,
        addEventListener: () => {},
        removeEventListener: () => {},
      }) as unknown as MediaQueryList
  );
}

function renderCard(onToggle = () => {}, expanded = false) {
  render(
    <ul>
      <DiagnosticCard row={ROW} scanStarted finished expanded={expanded} onToggle={onToggle} />
    </ul>
  );
  return screen.getByTestId("diagnostic-row");
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("limitations on narrow screens", () => {
  it("wide: limitation text is open and visible without interaction", () => {
    mockViewport(false);
    const card = renderCard();
    const details = card.querySelector("details.vx-limits") as HTMLDetailsElement;
    expect(details.open).toBe(true);
  });

  it("narrow: limitation text is collapsed behind a labelled disclosure but still in the DOM", () => {
    mockViewport(true);
    const card = renderCard();
    const details = card.querySelector("details.vx-limits") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    expect(within(card).getByText("Limitations: data collected, not hardware tested")).toBeInTheDocument();
    // Content is reachable (not removed): expanding reveals it.
    expect(within(card).getByTestId("diagnostic-summary")).toHaveTextContent("does not represent RAM chip");
    details.open = true;
    expect(details.open).toBe(true);
  });

  it("narrow: the RUNTIME_DETECTION label and metrics stay visible outside the disclosure", () => {
    mockViewport(true);
    const card = renderCard();
    const details = card.querySelector("details.vx-limits") as HTMLElement;
    const badge = within(card).getByText("RUNTIME_DETECTION");
    expect(details.contains(badge)).toBe(false);
    const metric = within(card).getAllByTestId("metric")[0];
    expect(details.contains(metric)).toBe(false);
    expect(metric).toHaveTextContent("5.91 GB");
  });

  it("keeps the runtime-detection vs functional-test statement in the card", () => {
    mockViewport(true);
    const card = renderCard();
    expect(card).toHaveTextContent(/data was read from the phone\. The component was not functionally tested/);
  });
});

describe("technical evidence disclosure", () => {
  it("is a real button that reports its state and is keyboard operable", () => {
    mockViewport(false);
    const onToggle = vi.fn();
    const card = renderCard(onToggle);
    const toggle = within(card).getByRole("button", { name: /Technical evidence \(2\)/ });
    expect(toggle.tagName).toBe("BUTTON");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveAttribute("aria-controls", "evidence-memory_telemetry");
    toggle.focus();
    expect(toggle).toHaveFocus();
    fireEvent.click(toggle); // Enter/Space on a <button> dispatch click
    expect(onToggle).toHaveBeenCalledTimes(1);
  });
});

describe("evidence table on narrow screens", () => {
  it("is a focusable, labelled scroll region so keyboard users can scroll it", () => {
    render(<EvidenceTable evidence={ROW.result!.evidence} />);
    const region = screen.getByRole("region", { name: /Evidence table/ });
    expect(region).toHaveAttribute("tabindex", "0");
    expect(region.querySelector("table")).toBeInTheDocument();
  });

  it("still exposes raw value, collection method, units, reliability, source and time", () => {
    render(<EvidenceTable evidence={ROW.result!.evidence} />);
    const table = screen.getByTestId("evidence-table");
    expect(within(table).getByText("5.91 GB")).toBeInTheDocument();
    expect(within(table).getByText("Raw: 5909782528 bytes")).toBeInTheDocument();
    expect(within(table).getAllByText("adb shell cat /proc/meminfo")).toHaveLength(2);
    expect(within(table).getAllByText("(ADB_SHELL)")).toHaveLength(2);
    expect(within(table).getAllByText("not modeled")).toHaveLength(2);
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "Item",
      "Value",
      "Collected by",
      "Reliability",
      "Time",
    ]);
  });

  it("announces a sideways-scroll hint only to sighted users (hidden from the accessibility tree)", () => {
    render(<EvidenceTable evidence={ROW.result!.evidence} />);
    expect(screen.getByText(/Swipe sideways/)).toHaveAttribute("aria-hidden", "true");
  });
});

describe("layout order", () => {
  const css = readFileSync(resolve(__dirname, "../workspace.css"), "utf-8");

  it("never uses dense grid packing, so focus order, reading order and visual order agree", () => {
    expect(css).not.toMatch(/grid-auto-flow\s*:[^;]*dense/);
  });

  it("expanded cards widen in place instead of reordering", () => {
    expect(css).toMatch(/\.vx-card\.is-expanded\s*\{[^}]*grid-column:\s*span 2/);
  });
});
