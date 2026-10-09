import type { FC } from "react";
import { useAndroidDiscovery } from "../lib/api/useAndroidDiscovery";
import { useAndroidBattery } from "../lib/api/useAndroidBattery";
import type { DiagnosticProvider } from "../providers/DiagnosticProvider";
import type { AndroidDevice, BatteryDiagnosticStatus } from "../lib/api/types";

export interface AndroidStatusProps {
  provider?: DiagnosticProvider;
}

function batteryStatusBadgeClass(status: BatteryDiagnosticStatus): string {
  switch (status) {
    case "PASS":
      return "status-pass";
    case "INCONCLUSIVE":
      return "status-partial";
    case "ERROR":
      return "status-fail";
    default:
      return "status-checking";
  }
}

function formatTemperature(c: number | null | undefined): string {
  if (c == null) return "—";
  return `${c.toFixed(1)} °C`;
}

function formatVoltage(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${v.toFixed(2)} V`;
}

function formatPercent(n: number | null | undefined): string {
  if (n == null) return "—";
  return `${n}%`;
}

function formatString(s: string | null | undefined): string {
  return s ?? "—";
}

function formatTimestamp(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

/**
 * AndroidStatus component.
 *
 * Displays Android device discovery state and, when one authorized device
 * is found, allows the user to run the Battery Telemetry Verification.
 *
 * Design rules:
 * - Manual detection only (no continuous polling).
 * - Battery test enabled only when exactly one DEVICE-state device exists.
 * - PASS status note explicitly disclaims battery-health assessment.
 * - All displayed values come from real ADB evidence in Live mode.
 */
export const AndroidStatus: FC<AndroidStatusProps> = ({ provider }) => {
  const {
    mode,
    state: discoveryState,
    data: discoveryData,
    errorMessage: discoveryError,
    detect,
  } = useAndroidDiscovery({ provider });

  const {
    state: batteryState,
    data: batteryData,
    errorMessage: batteryError,
    runTest,
  } = useAndroidBattery({ provider });

  const isDemo = mode === "demo";

  // Find the single authorized device if present
  const authorizedDevice: AndroidDevice | null =
    discoveryData?.state === "DEVICE" && discoveryData.devices.length === 1
      ? discoveryData.devices[0]
      : null;

  const canRunBatteryTest =
    authorizedDevice !== null &&
    batteryState !== "RUNNING" &&
    discoveryState === "COMPLETE";

  const handleBatteryTest = () => {
    if (authorizedDevice) {
      runTest(authorizedDevice.device_id);
    }
  };

  // ------------------------------------------------------------------
  // Device section content
  // ------------------------------------------------------------------
  const renderDeviceContent = () => {
    if (isDemo) {
      return (
        <div className="offline-message" data-testid="android-demo-banner">
          <p>
            [DEMO] Android device discovery is not available in Demo mode.
            Switch to Live mode with a connected device.
          </p>
        </div>
      );
    }

    if (discoveryState === "IDLE") {
      return (
        <div className="offline-message" data-testid="android-idle">
          <p>
            Click <strong>Detect Android Device</strong> to search for a
            connected phone.
          </p>
        </div>
      );
    }

    if (discoveryState === "CHECKING") {
      return (
        <div className="preflight-loading" data-testid="android-checking">
          <p>Detecting Android device via ADB…</p>
        </div>
      );
    }

    if (discoveryState === "ERROR" || discoveryError) {
      return (
        <div className="offline-message" data-testid="android-error">
          <p>
            {discoveryError ??
              "VECTOR could not complete Android device detection."}
          </p>
        </div>
      );
    }

    if (!discoveryData) return null;

    // NO_DEVICE
    if (discoveryData.state === "NO_DEVICE") {
      return (
        <div className="offline-message" data-testid="android-no-device">
          <p>
            {discoveryData.adb_available === false
              ? "Android Platform Tools are required before VECTOR can discover an Android device. Install ADB and ensure it is on PATH."
              : "No Android device detected. Connect a phone with USB Debugging enabled and click Detect."}
          </p>
        </div>
      );
    }

    // UNAUTHORIZED
    if (discoveryData.state === "UNAUTHORIZED") {
      return (
        <div className="offline-message" data-testid="android-unauthorized">
          <p>
            Android device detected but not authorized. Unlock the phone and
            approve the USB debugging prompt on the device screen, then click
            Retry Detection.
          </p>
        </div>
      );
    }

    // OFFLINE
    if (discoveryData.state === "OFFLINE") {
      return (
        <div className="offline-message" data-testid="android-offline">
          <p>
            The agent has an Android device record that is currently offline.
            The phone may be disconnected, or ADB may be listing it as offline;
            this response does not say which. Reconnect the USB cable (use one
            that supports data transfer), unlock the phone, then click Retry
            Detection.
          </p>
        </div>
      );
    }

    // UNKNOWN — the agent could not classify the connection state
    if (discoveryData.state === "UNKNOWN") {
      return (
        <div className="offline-message" data-testid="android-unknown">
          <p>
            The agent could not determine the connection state of this Android
            device, so no diagnostics can run. Reconnect the phone, unlock it,
            and click Retry Detection.
          </p>
        </div>
      );
    }

    // MISSING_DRIVER — reported by the agent; do not claim more than that
    if (discoveryData.state === "MISSING_DRIVER") {
      return (
        <div className="offline-message" data-testid="android-missing-driver">
          <p>
            The agent reports that a USB driver for this Android device is
            missing, so no diagnostics can run. Install the phone
            manufacturer&apos;s USB driver, reconnect the phone, and click
            Retry Detection.
          </p>
        </div>
      );
    }

    // MULTIPLE_DEVICES
    if (discoveryData.state === "MULTIPLE_DEVICES") {
      return (
        <div className="offline-message" data-testid="android-multiple">
          <p>
            {discoveryData.count} Android devices detected. Connect only one
            device for VECTOR diagnostics and click Retry Detection.
          </p>
        </div>
      );
    }

    // DEVICE — authorized device present
    if (authorizedDevice) {
      return (
        <div className="online-details" data-testid="android-device-details">
          <div className="detail-row">
            <span className="detail-label">Manufacturer</span>
            <span className="detail-value" data-testid="android-manufacturer">
              {formatString(authorizedDevice.manufacturer)}
            </span>
          </div>
          <div className="detail-row">
            <span className="detail-label">Model</span>
            <span className="detail-value" data-testid="android-model">
              {formatString(authorizedDevice.model)}
            </span>
          </div>
          <div className="detail-row">
            <span className="detail-label">Android</span>
            <span
              className="detail-value"
              data-testid="android-version"
            >
              {formatString(authorizedDevice.android_version)}
            </span>
          </div>
          <div className="detail-row">
            <span className="detail-label">ADB</span>
            <span className="status-badge status-pass" data-testid="android-adb-status">
              AUTHORIZED
            </span>
          </div>
        </div>
      );
    }

    // Fallback for ERROR or unknown state from discovery
    return (
      <div className="offline-message" data-testid="android-discovery-error">
        <p>
          {discoveryData.message ||
            `VECTOR received an Android connection state it cannot interpret (${discoveryData.state}). No diagnostics can run for it. Reconnect the device and click Retry Detection.`}
        </p>
      </div>
    );
  };

  // ------------------------------------------------------------------
  // Battery section content
  // ------------------------------------------------------------------
  const renderBatteryContent = () => {
    if (!authorizedDevice) return null;

    if (batteryState === "IDLE") {
      return (
        <p className="demo-note" data-testid="battery-idle">
          Click <strong>Run Battery Test</strong> to collect telemetry from the
          connected device.
        </p>
      );
    }

    if (batteryState === "RUNNING") {
      return (
        <div className="preflight-loading" data-testid="battery-running">
          <p>Collecting battery telemetry via ADB…</p>
        </div>
      );
    }

    if (batteryState === "ERROR" || batteryError) {
      return (
        <div className="offline-message" data-testid="battery-error">
          <p>
            {batteryError ??
              "Battery telemetry collection failed. The device may have disconnected."}
          </p>
        </div>
      );
    }

    if (batteryState === "COMPLETE" && batteryData) {
      const statusClass = batteryStatusBadgeClass(batteryData.status);
      return (
        <div data-testid="battery-results">
          <div className="status-indicator-row" style={{ marginBottom: "12px" }}>
            <span className="status-label">Status</span>
            <span
              className={`status-badge ${statusClass}`}
              data-testid="battery-status-badge"
            >
              {batteryData.status}
            </span>
          </div>

          <div className="online-details" data-testid="battery-telemetry-values">
            {batteryData.present !== null && (
              <div className="detail-row">
                <span className="detail-label">Battery present</span>
                <span className="detail-value" data-testid="battery-present">
                  {batteryData.present ? "Yes" : "No"}
                </span>
              </div>
            )}
            {batteryData.level_pct !== null && (
              <div className="detail-row">
                <span className="detail-label">Charge level</span>
                <span className="detail-value" data-testid="battery-level">
                  {formatPercent(batteryData.level_pct)}
                </span>
              </div>
            )}
            {batteryData.charging_state && (
              <div className="detail-row">
                <span className="detail-label">Charging state</span>
                <span className="detail-value" data-testid="battery-charging-state">
                  {batteryData.charging_state}
                </span>
              </div>
            )}
            {batteryData.temperature_c !== null && (
              <div className="detail-row">
                <span className="detail-label">Temperature</span>
                <span className="detail-value" data-testid="battery-temperature">
                  {formatTemperature(batteryData.temperature_c)}
                </span>
              </div>
            )}
            {batteryData.voltage_v !== null && (
              <div className="detail-row">
                <span className="detail-label">Voltage</span>
                <span className="detail-value" data-testid="battery-voltage">
                  {formatVoltage(batteryData.voltage_v)}
                </span>
              </div>
            )}
          </div>

          <div
            className="online-details"
            style={{ marginTop: "12px" }}
            data-testid="battery-evidence"
          >
            <div className="detail-row">
              <span className="detail-label">Evidence source</span>
              <span className="detail-value" data-testid="battery-evidence-source">
                {batteryData.evidence_source}
              </span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Collected</span>
              <span className="detail-value" data-testid="battery-collected-at">
                {formatTimestamp(batteryData.collected_at)}
              </span>
            </div>
          </div>

          <p
            className="demo-note"
            style={{ marginTop: "12px" }}
            data-testid="battery-pass-note"
          >
            {batteryData.status_note}
          </p>
        </div>
      );
    }

    return null;
  };

  return (
    <section
      className="preflight-card"
      aria-labelledby="android-heading"
      data-testid="android-section"
    >
      {/* ---- Device discovery header ---- */}
      <div className="preflight-header">
        <div className="brand-row">
          <h2 id="android-heading" className="preflight-title">
            Android Device
          </h2>
          {isDemo && (
            <span
              className="mode-badge mode-demo"
              data-testid="android-mode-badge"
            >
              DEMO
            </span>
          )}
        </div>
        <p className="service-subtitle">
          {isDemo ? "Demo Mode — No real device" : "USB ADB Connection"}
        </p>
      </div>

      {/* ---- Device state ---- */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        data-testid="android-device-status"
      >
        {renderDeviceContent()}
      </div>

      {/* ---- Detect button ---- */}
      {!isDemo && (
        <div className="action-row" style={{ marginTop: "16px" }}>
          <button
            id="detect-android-btn"
            type="button"
            className="retry-button"
            onClick={detect}
            disabled={discoveryState === "CHECKING"}
            data-testid="detect-android-btn"
            aria-label={
              discoveryState === "CHECKING"
                ? "Detecting Android device…"
                : discoveryState === "IDLE"
                  ? "Detect Android Device"
                  : "Retry Detection"
            }
          >
            {discoveryState === "CHECKING"
              ? "Detecting…"
              : discoveryState === "IDLE"
                ? "Detect Android Device"
                : "Retry Detection"}
          </button>
        </div>
      )}

      {/* ---- Battery telemetry section ---- */}
      {authorizedDevice && !isDemo && (
        <div style={{ marginTop: "24px" }}>
          <div className="preflight-header" style={{ marginBottom: "16px" }}>
            <h3
              className="preflight-title"
              style={{ fontSize: "16px" }}
              data-testid="battery-section-heading"
            >
              Battery Telemetry
            </h3>
          </div>

          <div
            role="status"
            aria-live="polite"
            aria-atomic="true"
            data-testid="battery-status"
          >
            {renderBatteryContent()}
          </div>

          <div className="action-row" style={{ marginTop: "12px" }}>
            <button
              id="run-battery-test-btn"
              type="button"
              className="retry-button"
              onClick={handleBatteryTest}
              disabled={!canRunBatteryTest}
              data-testid="run-battery-test-btn"
              aria-label={
                batteryState === "RUNNING"
                  ? "Collecting battery telemetry…"
                  : "Run Battery Test"
              }
            >
              {batteryState === "RUNNING"
                ? "Collecting…"
                : "Run Battery Test"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
};
