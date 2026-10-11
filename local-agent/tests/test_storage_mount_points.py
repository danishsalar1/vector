"""Regression tests: `df -k /data` reports the /data filesystem under a sub-path mount point.

Observed on a Redmi Note 8 Pro (Android 11): `df` prints the mount point of the filesystem
that contains /data, which is /data/user/0 on that device. The parser must accept that, while
still rejecting unrelated filesystems so they are never reported as /data.
"""

from __future__ import annotations

import pytest

from vector_agent.devices.android.storage import parse_storage_df

# Captured read-only from the device: `adb shell df -k /data` (CRLF line endings preserved).
REDMI_DF = (
    "Filesystem       1K-blocks     Used Available Use% Mounted on\r\n"
    "/dev/block/sdc46 114936328 62522756  52266116  55% /data/user/0\r\n"
)


def _row(mount: str) -> str:
    return (
        "Filesystem 1K-blocks Used Available Use% Mounted on\n"
        f"/dev/block/x 1000 250 750 25% {mount}\n"
    )


class TestStorageDataMountPoints:
    def test_real_redmi_output_passes_with_correct_values(self) -> None:
        res = parse_storage_df(REDMI_DF)
        assert res.status == "PASS"
        assert res.telemetry is not None
        assert res.telemetry.total_bytes == 114936328 * 1024
        assert res.telemetry.used_bytes == 62522756 * 1024
        assert res.telemetry.available_bytes == 52266116 * 1024
        assert res.telemetry.utilization_percent == 55.0
        assert res.telemetry.logical_target == "/data"

    @pytest.mark.parametrize("mount", ["/data", "/data/", "/data/user/0", "/data/user/0/"])
    def test_accepts_data_filesystem_mount_points(self, mount: str) -> None:
        res = parse_storage_df(_row(mount))
        assert res.status == "PASS"
        assert res.telemetry is not None
        assert res.telemetry.total_bytes == 1000 * 1024

    def test_wrapped_device_name_with_sub_path_mount(self) -> None:
        stdout = (
            "Filesystem 1K-blocks Used Available Use% Mounted on\n"
            "/dev/block/bootdevice/by-name/userdata\n"
            "                     1000 250 750 25% /data/user/0\n"
        )
        assert parse_storage_df(stdout).status == "PASS"

    @pytest.mark.parametrize(
        "mount",
        ["/", "/system", "/storage/emulated", "/mnt/data", "/database", "/datafoo"],
    )
    def test_rejects_other_filesystems_instead_of_mislabelling_them_as_data(
        self, mount: str
    ) -> None:
        res = parse_storage_df(_row(mount))
        assert res.status == "INCONCLUSIVE"
        assert res.telemetry is None
        assert "No storage entry for /data" in (res.error or "")

    def test_coherence_checks_still_apply_to_sub_path_mount(self) -> None:
        res = parse_storage_df("/dev/block/x 1000 1200 0 120% /data/user/0\n")
        assert res.status == "INCONCLUSIVE"
        assert res.telemetry is None

    def test_malformed_numbers_under_sub_path_mount_stay_inconclusive(self) -> None:
        res = parse_storage_df("/dev/block/x NOT_A_NUMBER 100 900 10% /data/user/0\n")
        assert res.status == "INCONCLUSIVE"
        assert res.telemetry is None
        assert "Malformed numeric storage metrics" in (res.error or "")
