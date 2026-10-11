import type { FC } from "react";
import type { ConnectedDevice } from "../../lib/api/devices";
import {
  describeDevice,
  formatPlatform,
  getDeviceEligibility,
  statusTone,
} from "../../lib/scan/quickScanModel";
import type { UseDeviceListResult } from "../../lib/scan/useDeviceList";

export interface DevicePanelProps {
  list: UseDeviceListResult;
  selectedId: string | null;
  onSelect: (deviceId: string) => void;
  /** True while a scan is starting or running; selection and refresh are frozen. */
  locked: boolean;
}

const AUTH_LABELS: Record<string, string> = {
  AUTHORIZED: "Authorized",
  AUTHORIZATION_REQUIRED: "Authorization required",
  RESTRICTED: "Restricted",
  UNKNOWN: "Unknown",
};

function authorizationLabel(device: ConnectedDevice): string {
  return device.authorization_state
    ? (AUTH_LABELS[device.authorization_state] ?? device.authorization_state)
    : "Not reported";
}

function authorizationTone(device: ConnectedDevice): string {
  if (device.authorization_state === "AUTHORIZED") return "ok";
  if (device.authorization_state === "RESTRICTED") return "bad";
  return "warn";
}

export const DevicePanel: FC<DevicePanelProps> = ({
  list,
  selectedId,
  onSelect,
  locked,
}) => {
  const { mode, state, devices, errorMessage, refresh } = list;
  const isDemo = mode === "demo";

  return (
    <section className="qs-panel" aria-labelledby="device-heading" data-testid="device-panel">
      <div className="qs-panel-head">
        <h2 id="device-heading" className="qs-panel-title">
          Device
        </h2>
        <button
          type="button"
          className="qs-button qs-button-quiet"
          onClick={refresh}
          disabled={state === "CHECKING" || locked || isDemo}
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
        <p className="qs-muted" role="status" data-testid="device-loading">
          Looking for connected phones…
        </p>
      )}

      {!isDemo && state === "ERROR" && (
        <div className="qs-alert" role="alert" data-testid="device-error">
          <p>{errorMessage ?? "Device discovery failed."}</p>
          <p className="qs-muted">
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

      {!isDemo && state === "COMPLETE" && devices.length > 0 && (
        <ul className="qs-device-list" aria-label="Discovered devices">
          {devices.map((device) => {
            const { title, os } = describeDevice(device);
            const eligibility = getDeviceEligibility(device);
            const selected = device.device_id === selectedId;
            const id = device.identity;
            return (
              <li key={device.device_id}>
                <button
                  type="button"
                  className={`qs-device${selected ? " is-selected" : ""}`}
                  aria-pressed={selected}
                  disabled={locked && !selected}
                  onClick={() => onSelect(device.device_id)}
                  data-testid="device-option"
                >
                  <span className="qs-device-title">{title}</span>
                  <span className="qs-device-sub">
                    {os ?? formatPlatform(device.platform)}
                  </span>
                  <span className="qs-chips">
                    <span
                      className={`qs-chip tone-${statusTone(
                        device.connection_state === "CONNECTED" ? "PASS" : "ERROR"
                      )}`}
                      data-testid="device-connection"
                    >
                      {device.connection_state}
                    </span>
                    <span
                      className={`qs-chip tone-${authorizationTone(device)}`}
                      data-testid="device-authorization"
                    >
                      {authorizationLabel(device)}
                    </span>
                  </span>
                </button>
                {selected && (
                  <dl className="qs-facts" data-testid="device-facts">
                    <div>
                      <dt>Manufacturer</dt>
                      <dd>{id?.manufacturer ?? "—"}</dd>
                    </div>
                    <div>
                      <dt>Model</dt>
                      <dd>{id?.model ?? "—"}</dd>
                    </div>
                    <div>
                      <dt>{device.platform.toUpperCase() === "IOS" ? "iOS version" : "Android version"}</dt>
                      <dd>{id?.android_version ?? id?.ios_version ?? "—"}</dd>
                    </div>
                    {id?.android_sdk_level != null && (
                      <div>
                        <dt>SDK level</dt>
                        <dd>{id.android_sdk_level}</dd>
                      </div>
                    )}
                    {id?.device_codename && (
                      <div>
                        <dt>Codename</dt>
                        <dd>{id.device_codename}</dd>
                      </div>
                    )}
                  </dl>
                )}
                {selected && !eligibility.eligible && (
                  <p className="qs-alert" role="alert" data-testid="device-blocked">
                    {eligibility.reason}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {!isDemo && state === "COMPLETE" && devices.length > 1 && selectedId === null && (
        <p className="qs-muted">Select a device to plan a scan.</p>
      )}
    </section>
  );
};
