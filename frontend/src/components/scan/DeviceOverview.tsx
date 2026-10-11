import type { FC } from "react";
import type { ConnectedDevice } from "../../lib/api/devices";
import {
  describeDevice,
  formatPlatform,
  type DeviceEligibility,
} from "../../lib/scan/quickScanModel";
import type { UseDeviceListResult } from "../../lib/scan/useDeviceList";
import type { QuickScanPhase, UseQuickScanResult } from "../../lib/scan/useQuickScan";

export interface DeviceOverviewProps {
  device: ConnectedDevice;
  eligibility: DeviceEligibility;
  list: UseDeviceListResult;
  session: UseQuickScanResult;
  onSelect: (deviceId: string) => void;
  /** True while a scan is starting or running; switching and refresh are frozen. */
  locked: boolean;
}

const AUTH_LABELS: Record<string, string> = {
  AUTHORIZED: "Authorized",
  AUTHORIZATION_REQUIRED: "Authorization required",
  RESTRICTED: "Restricted",
  UNKNOWN: "Unknown",
};

const START_LABELS: Partial<Record<QuickScanPhase, string>> = {
  PLAN_READY: "Start Quick Scan",
  START_ERROR: "Try again",
  FINISHED: "Run scan again",
  PLANNING: "Preparing plan…",
  STARTING: "Starting…",
  RUNNING: "Scan in progress…",
};

export const DeviceOverview: FC<DeviceOverviewProps> = ({
  device,
  eligibility,
  list,
  session,
  onSelect,
  locked,
}) => {
  const { title, os } = describeDevice(device);
  const id = device.identity;
  const authorization = device.authorization_state
    ? (AUTH_LABELS[device.authorization_state] ?? device.authorization_state)
    : "Not reported";
  const connected = device.connection_state === "CONNECTED";
  const authorized = device.authorization_state === "AUTHORIZED";
  const others = list.devices.filter((d) => d.device_id !== device.device_id);
  const { phase } = session;
  const canStart = phase === "PLAN_READY" || phase === "START_ERROR" || phase === "FINISHED";

  const subtitle = [
    os,
    id?.android_sdk_level != null ? `SDK ${id.android_sdk_level}` : null,
    id?.device_codename ?? null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <section className="vx-hero" aria-labelledby="device-heading" data-testid="device-panel">
      <div className="vx-hero-main">
        <div className="vx-hero-id">
          <p className="vx-eyebrow">{formatPlatform(device.platform)} device</p>
          <h2 id="device-heading" className="vx-device-name">
            {title}
          </h2>
          {subtitle && <p className="vx-device-sub">{subtitle}</p>}
          <div className="qs-chips">
            <span
              className={`qs-chip tone-${connected ? "ok" : "bad"}`}
              data-testid="device-connection"
            >
              {device.connection_state}
            </span>
            <span
              className={`qs-chip tone-${authorized ? "ok" : device.authorization_state === "RESTRICTED" ? "bad" : "warn"}`}
              data-testid="device-authorization"
            >
              {authorization}
            </span>
          </div>
        </div>

        <dl className="vx-facts" data-testid="device-facts">
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

        <div className="vx-hero-action">
          {eligibility.eligible ? (
            <>
              <button
                type="button"
                className="qs-button qs-button-primary"
                onClick={session.start}
                disabled={!canStart}
                data-testid="start-scan"
              >
                {START_LABELS[phase] ?? "Start Quick Scan"}
              </button>
              <p className="vx-muted">
                Read-only. VECTOR reads telemetry and inventory over ADB and changes nothing on
                the phone.
              </p>
            </>
          ) : (
            <p className="vx-muted">Scanning is unavailable until this device is ready.</p>
          )}
          <button
            type="button"
            className="qs-button qs-button-quiet"
            onClick={list.refresh}
            disabled={list.state === "CHECKING" || locked}
          >
            {list.state === "CHECKING" ? "Searching…" : "Refresh"}
          </button>
        </div>
      </div>

      {!eligibility.eligible && (
        <p className="qs-alert" role="alert" data-testid="device-blocked">
          {eligibility.reason}
        </p>
      )}

      {others.length > 0 && (
        <div className="vx-switch" aria-label="Other connected devices">
          <span className="vx-muted">Other devices:</span>
          {others.map((other) => {
            const name = describeDevice(other).title;
            return (
              <button
                key={other.device_id}
                type="button"
                className="qs-button qs-button-quiet"
                disabled={locked}
                onClick={() => onSelect(other.device_id)}
                data-testid="device-switch"
              >
                {name}
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
};
