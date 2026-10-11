import type { FC } from "react";
import { describeDevice, formatPlatform } from "../../lib/scan/quickScanModel";
import type { UseDeviceListResult } from "../../lib/scan/useDeviceList";

export interface DevicePanelProps {
  list: UseDeviceListResult;
  onSelect: (deviceId: string) => void;
}

const AUTH_LABELS: Record<string, string> = {
  AUTHORIZED: "Authorized",
  AUTHORIZATION_REQUIRED: "Authorization required",
  RESTRICTED: "Restricted",
  UNKNOWN: "Unknown",
};

/**
 * Device discovery states shown when no device is selected: loading, error,
 * empty, demo, or a list to choose from. Once a device is selected the
 * DeviceOverview takes over.
 */
export const DevicePanel: FC<DevicePanelProps> = ({ list, onSelect }) => {
  const { mode, state, devices, errorMessage, refresh } = list;
  const isDemo = mode === "demo";

  return (
    <section className="vx-hero vx-hero-idle" aria-labelledby="device-heading" data-testid="device-panel">
      <div className="qs-panel-head">
        <div>
          <p className="vx-eyebrow">Device</p>
          <h2 id="device-heading" className="vx-device-name vx-device-name-idle">
            {devices.length > 1 ? "Choose a device" : "Connect a phone"}
          </h2>
        </div>
        <button
          type="button"
          className="qs-button qs-button-quiet"
          onClick={refresh}
          disabled={state === "CHECKING" || isDemo}
        >
          {state === "CHECKING" ? "Searching…" : "Refresh"}
        </button>
      </div>

      {isDemo && (
        <p className="qs-notice" data-testid="device-demo-banner">
          <strong>DEMO DATASET.</strong> Demo mode never contacts a phone. No device is
          simulated. Run VECTOR in Live mode with a connected device to scan.
        </p>
      )}

      {!isDemo && state === "CHECKING" && (
        <p className="vx-muted" role="status" data-testid="device-loading">
          Looking for connected phones…
        </p>
      )}

      {!isDemo && state === "ERROR" && (
        <div className="qs-alert" role="alert" data-testid="device-error">
          <p>{errorMessage ?? "Device discovery failed."}</p>
          <p className="vx-muted">
            Check that the VECTOR local agent is running, then press Refresh.
          </p>
        </div>
      )}

      {!isDemo && state === "COMPLETE" && devices.length === 0 && (
        <div className="qs-empty" data-testid="device-empty">
          <p className="qs-empty-title">No phone detected</p>
          <ol className="qs-steps">
            <li>Connect the phone with a USB data cable.</li>
            <li>Enable Developer options, then USB debugging.</li>
            <li>Unlock the phone and accept the “Allow USB debugging” prompt.</li>
          </ol>
        </div>
      )}

      {!isDemo && state === "COMPLETE" && devices.length > 1 && (
        <ul className="qs-device-list" aria-label="Discovered devices">
          {devices.map((device) => {
            const { title, os } = describeDevice(device);
            const authorization = device.authorization_state
              ? (AUTH_LABELS[device.authorization_state] ?? device.authorization_state)
              : "Not reported";
            return (
              <li key={device.device_id}>
                <button
                  type="button"
                  className="qs-device"
                  onClick={() => onSelect(device.device_id)}
                  data-testid="device-option"
                >
                  <span className="qs-device-title">{title}</span>
                  <span className="qs-device-sub">{os ?? formatPlatform(device.platform)}</span>
                  <span className="qs-chips">
                    <span className={`qs-chip tone-${device.connection_state === "CONNECTED" ? "ok" : "bad"}`}>
                      {device.connection_state}
                    </span>
                    <span className="qs-chip tone-neutral">{authorization}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
};
