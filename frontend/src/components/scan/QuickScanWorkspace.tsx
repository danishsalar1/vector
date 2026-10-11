import { useState, type FC, type ReactNode } from "react";
import type { ConnectedDevice } from "../../lib/api/devices";
import { getDeviceEligibility } from "../../lib/scan/quickScanModel";
import { useDeviceList, type UseDeviceListResult } from "../../lib/scan/useDeviceList";
import { useQuickScan, type UseQuickScanOptions } from "../../lib/scan/useQuickScan";
import { DevicePanel } from "./DevicePanel";
import { ScanPanel } from "./ScanPanel";

export interface QuickScanWorkspaceProps {
  /** Test seam: polling cadence and tolerance. */
  scanOptions?: Pick<UseQuickScanOptions, "pollIntervalMs" | "maxPollFailures">;
}

const Layout: FC<{ side: ReactNode; children: ReactNode }> = ({ side, children }) => (
  <div className="qs-workspace">
    <aside className="qs-side">{side}</aside>
    <div className="qs-main">{children}</div>
  </div>
);

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
    <Layout
      side={
        <DevicePanel
          list={list}
          selectedId={device.device_id}
          onSelect={onSelect}
          locked={locked}
        />
      }
    >
      {eligibility.eligible ? (
        <ScanPanel device={device} session={session} />
      ) : (
        <section className="qs-panel" aria-labelledby="scan-heading">
          <h2 id="scan-heading" className="qs-panel-title">
            Quick Scan
          </h2>
          <p className="qs-muted" data-testid="scan-unavailable">
            Scanning is unavailable until this device is connected and authorized.
          </p>
        </section>
      )}
    </Layout>
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
    <Layout
      side={<DevicePanel list={list} selectedId={null} onSelect={setSelectedId} locked={false} />}
    >
      <section className="qs-panel" aria-labelledby="scan-heading">
        <h2 id="scan-heading" className="qs-panel-title">
          Quick Scan
        </h2>
        <p className="qs-muted" data-testid="scan-idle">
          {list.mode === "demo"
            ? "Quick Scan is unavailable in Demo mode."
            : "Connect and select a phone to see which diagnostics apply."}
        </p>
      </section>
    </Layout>
  );
};
