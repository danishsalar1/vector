import { useState, type FC } from "react";
import type { ConnectedDevice } from "../../lib/api/devices";
import { getDeviceEligibility } from "../../lib/scan/quickScanModel";
import { useDeviceList, type UseDeviceListResult } from "../../lib/scan/useDeviceList";
import { useQuickScan, type UseQuickScanOptions } from "../../lib/scan/useQuickScan";
import { DeviceOverview } from "./DeviceOverview";
import { DevicePanel } from "./DevicePanel";
import { ScanPanel } from "./ScanPanel";

export interface QuickScanWorkspaceProps {
  /** Test seam: polling cadence and tolerance. */
  scanOptions?: Pick<UseQuickScanOptions, "pollIntervalMs" | "maxPollFailures">;
}

/**
 * One device's scan session. Mounted with key={device_id} so a different device
 * never inherits another device's plan or results.
 */
const ScanSession: FC<{
  device: ConnectedDevice;
  list: UseDeviceListResult;
  onSelect: (id: string) => void;
  scanOptions?: QuickScanWorkspaceProps["scanOptions"];
}> = ({ device, list, onSelect, scanOptions }) => {
  const eligibility = getDeviceEligibility(device);
  const session = useQuickScan(device.device_id, eligibility.eligible, scanOptions);
  const locked =
    session.phase === "STARTING" || session.phase === "RUNNING" || session.phase === "POLL_LOST";

  return (
    <div className="vx-stack">
      <DeviceOverview
        device={device}
        eligibility={eligibility}
        list={list}
        session={session}
        onSelect={onSelect}
        locked={locked}
      />
      {eligibility.eligible ? (
        <ScanPanel session={session} />
      ) : (
        <p className="vx-muted" data-testid="scan-unavailable">
          Scanning is unavailable until this device is connected and authorized.
        </p>
      )}
    </div>
  );
};

export const QuickScanWorkspace: FC<QuickScanWorkspaceProps> = ({ scanOptions }) => {
  const list = useDeviceList();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // A lone device is selected for convenience; with several, the user must choose.
  const selected =
    list.devices.find((d) => d.device_id === selectedId) ??
    (list.devices.length === 1 ? list.devices[0] : null);

  if (selected) {
    return (
      <ScanSession
        key={selected.device_id}
        device={selected}
        list={list}
        onSelect={setSelectedId}
        scanOptions={scanOptions}
      />
    );
  }

  return (
    <div className="vx-stack">
      <DevicePanel list={list} onSelect={setSelectedId} />
      <p className="vx-muted" data-testid="scan-idle">
        {list.mode === "demo"
          ? "Quick Scan is unavailable in Demo mode."
          : "Connect and select a phone to see which diagnostics apply."}
      </p>
    </div>
  );
};
