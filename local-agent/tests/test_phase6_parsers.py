"""Comprehensive parser tests for Phase 6 Android standard diagnostics.

Tests every pure parser across all required testing conditions:
1. Valid representative output
2. Whitespace variation
3. Extra unknown lines (OEM additions)
4. Missing optional fields
5. Missing required fields
6. Empty output
7. Malformed numbers
8. Impossible / incoherent values
9. Truncated output
10. Non-zero exit code
11. Permission denied / SecurityException (RESTRICTED)
12. Privacy: sensitive data is never captured in telemetry or results
"""

from __future__ import annotations

from vector_agent.devices.android.camera import parse_camera_inventory
from vector_agent.devices.android.display import parse_display_metrics
from vector_agent.devices.android.memory import parse_proc_meminfo
from vector_agent.devices.android.storage import parse_storage_df
from vector_agent.devices.android.thermal import parse_dumpsys_thermal

# ============================================================
# Storage Telemetry Parser Tests (df -k /data)
# ============================================================


class TestStorageParser:
    """Tests for parse_storage_df."""

    # 1. Valid representative output
    def test_valid_output(self) -> None:
        stdout = (
            "Filesystem     1K-blocks     Used Available Use% Mounted on\n"
            "/dev/block/dm-46 111582236 25642188  85806652  23% /data\n"
        )
        res = parse_storage_df(stdout)
        assert res.status == "PASS"
        assert res.confidence == 1.0
        assert res.telemetry is not None
        assert res.telemetry.total_bytes == 111582236 * 1024
        assert res.telemetry.used_bytes == 25642188 * 1024
        assert res.telemetry.available_bytes == 85806652 * 1024
        assert res.telemetry.utilization_percent == 23.0
        assert res.telemetry.logical_target == "/data"

    # 2. Whitespace variation
    def test_whitespace_variation(self) -> None:
        stdout = (
            "  Filesystem \t 1K-blocks   Used \t Available Use% Mounted on\r\n"
            "  /dev/block/dm-0   50000000   10000000   40000000   20%   /data  \r\n"
        )
        res = parse_storage_df(stdout)
        assert res.status == "PASS"
        assert res.telemetry is not None
        assert res.telemetry.total_bytes == 50000000 * 1024
        assert res.telemetry.utilization_percent == 20.0

    # 3. Extra unknown lines & line wrapping (typical when device path is long)
    def test_extra_lines_and_wrapping(self) -> None:
        stdout = (
            "Filesystem 1K-blocks Used Available Use% Mounted on\n"
            "/dev/block/bootdevice/by-name/userdata\n"
            "                60000000 20000000 40000000 33% /data\n"
            "tmpfs            2000000      500  1999500   1% /dev\n"
        )
        res = parse_storage_df(stdout)
        assert res.status == "PASS"
        assert res.telemetry is not None
        assert res.telemetry.total_bytes == 60000000 * 1024
        assert res.telemetry.used_bytes == 20000000 * 1024

    # 4. Missing optional field (e.g. utilization % without % sign or missing)
    def test_calculated_utilization_when_missing(self) -> None:
        stdout = (
            "Filesystem 1K-blocks Used Available Use% Mounted on\n"
            "/dev/block/dm-0 1000000 250000 750000 - /data\n"
        )
        res = parse_storage_df(stdout)
        assert res.status == "PASS"
        assert res.telemetry is not None
        assert res.telemetry.utilization_percent == 25.0

    # 5. Missing required field (/data entry not in output)
    def test_missing_data_entry(self) -> None:
        stdout = (
            "Filesystem 1K-blocks Used Available Use% Mounted on\n"
            "/dev/block/system 2000000 1500000 500000 75% /system\n"
        )
        res = parse_storage_df(stdout)
        assert res.status == "INCONCLUSIVE"
        assert res.telemetry is None
        assert "No storage entry for /data" in (res.error or "")

    # 6. Empty output
    def test_empty_output(self) -> None:
        res = parse_storage_df("   \n\t")
        assert res.status == "INCONCLUSIVE"
        assert "empty output" in (res.error or "")

    # 7. Malformed numbers
    def test_malformed_numbers(self) -> None:
        stdout = "/dev/block/dm-0 NOT_A_NUMBER 1000 4000 20% /data\n"
        res = parse_storage_df(stdout)
        assert res.status == "INCONCLUSIVE"
        assert "Malformed" in (res.error or "")

    # 8. Impossible / incoherent values (never hardware FAIL!)
    def test_impossible_values(self) -> None:
        # Negative or 0 total
        stdout = "/dev/block/dm-0 0 0 0 0% /data\n"
        res = parse_storage_df(stdout)
        assert res.status == "INCONCLUSIVE"
        assert "Impossible" in (res.error or "")

        # Contradictory capacity (available is 10x total)
        stdout_contra = "/dev/block/dm-0 1000 100 50000 50% /data\n"
        res_contra = parse_storage_df(stdout_contra)
        assert res_contra.status == "INCONCLUSIVE"
        assert "contradictory" in (res_contra.error or "")

    def test_used_greater_than_total_is_inconclusive(self) -> None:
        stdout = "/dev/block/dm-0 1000 1200 0 120% /data\n"
        res = parse_storage_df(stdout)
        assert res.status == "INCONCLUSIVE"
        assert "contradictory" in (res.error or "")

    def test_available_greater_than_total_is_inconclusive(self) -> None:
        stdout = "/dev/block/dm-0 1000 0 1200 0% /data\n"
        res = parse_storage_df(stdout)
        assert res.status == "INCONCLUSIVE"
        assert "contradictory" in (res.error or "")

    # 9. Truncated output
    def test_truncated_output(self) -> None:
        stdout = "/dev/block/dm-0 1000000 200000 800000 20% /data\n"
        res = parse_storage_df(stdout, truncated=True)
        assert res.status == "INCONCLUSIVE"
        assert "truncated" in (res.error or "")

    # 10. Non-zero exit code
    def test_nonzero_exit_code(self) -> None:
        res = parse_storage_df("", stderr="error: device offline", return_code=1)
        assert res.status == "ERROR"
        assert res.telemetry is None

    # 11. Permission denied / SecurityException (RESTRICTED)
    def test_permission_denied(self) -> None:
        res = parse_storage_df("", stderr="df: /data: Permission denied", return_code=1)
        assert res.status == "RESTRICTED"
        assert "restricted" in (res.error or "")

    # 12. Privacy: personal paths/names not exposed
    def test_privacy_no_personal_paths(self) -> None:
        stdout = (
            "Filesystem 1K-blocks Used Available Use% Mounted on\n"
            "/dev/block/userdata_secret_partition 50000000 10000000 40000000 20% /data\n"
        )
        res = parse_storage_df(stdout)
        assert res.status == "PASS"
        assert res.telemetry is not None
        assert res.telemetry.logical_target == "/data"


# ============================================================
# Memory Telemetry Parser Tests (/proc/meminfo)
# ============================================================


class TestMemoryParser:
    """Tests for parse_proc_meminfo."""

    # 1. Valid representative output
    def test_valid_output(self) -> None:
        stdout = (
            "MemTotal:        5857280 kB\n"
            "MemFree:          124560 kB\n"
            "MemAvailable:    2845620 kB\n"
            "Buffers:           45120 kB\n"
            "Cached:          2100450 kB\n"
        )
        res = parse_proc_meminfo(stdout)
        assert res.status == "PASS"
        assert res.telemetry is not None
        assert res.telemetry.mem_total_bytes == 5857280 * 1024
        assert res.telemetry.mem_free_bytes == 124560 * 1024
        assert res.telemetry.mem_available_bytes == 2845620 * 1024

    # 2. Whitespace variation
    def test_whitespace_variation(self) -> None:
        stdout = "MemTotal:    4000000   kB \r\nMemFree:\t500000  kB\r\n"
        res = parse_proc_meminfo(stdout)
        assert res.status == "PASS"
        assert res.telemetry is not None
        assert res.telemetry.mem_total_bytes == 4000000 * 1024
        assert res.telemetry.mem_free_bytes == 500000 * 1024

    # 3. Extra unknown lines
    def test_extra_lines(self) -> None:
        stdout = (
            "MemTotal:        8000000 kB\n"
            "UnknownKernelParam: 999999 kB\n"
            "AnotherVendorSpecificLine: hello world\n"
            "MemFree:         2000000 kB\n"
            "MemAvailable:    5000000 kB\n"
        )
        res = parse_proc_meminfo(stdout)
        assert res.status == "PASS"
        assert res.telemetry is not None
        assert res.telemetry.mem_total_bytes == 8000000 * 1024

    # 4. Missing optional field (MemAvailable absent on older kernels)
    def test_missing_mem_available_not_fabricated(self) -> None:
        stdout = (
            "MemTotal:        2000000 kB\n"
            "MemFree:          500000 kB\n"
            "Buffers:           10000 kB\n"
        )
        res = parse_proc_meminfo(stdout)
        assert res.status == "PASS"
        assert res.telemetry is not None
        assert res.telemetry.mem_total_bytes == 2000000 * 1024
        assert res.telemetry.mem_available_bytes is None  # NOT fabricated

    # 5. Missing required field (MemTotal missing)
    def test_missing_mem_total(self) -> None:
        stdout = "MemFree:          500000 kB\nMemAvailable:    1000000 kB\n"
        res = parse_proc_meminfo(stdout)
        assert res.status == "INCONCLUSIVE"
        assert res.telemetry is None
        assert "MemTotal not found" in (res.error or "")

    # 6. Empty output
    def test_empty_output(self) -> None:
        res = parse_proc_meminfo("")
        assert res.status == "INCONCLUSIVE"
        assert "empty output" in (res.error or "")

    # 7. Malformed numbers
    def test_malformed_numbers(self) -> None:
        stdout = "MemTotal: abc kB\n"
        res = parse_proc_meminfo(stdout)
        assert res.status == "INCONCLUSIVE"

    # 8. Impossible / incoherent values (never hardware FAIL!)
    def test_impossible_values(self) -> None:
        # MemFree > MemTotal * 1.05
        stdout = "MemTotal:        1000000 kB\nMemFree:         9999999 kB\n"
        res = parse_proc_meminfo(stdout)
        assert res.status == "INCONCLUSIVE"
        assert "out of coherent bounds" in (res.error or "")

    # 9. Truncated output
    def test_truncated_output(self) -> None:
        stdout = "MemTotal: 8000000 kB\nMemFree: 2000000 kB\n"
        res = parse_proc_meminfo(stdout, truncated=True)
        assert res.status == "INCONCLUSIVE"
        assert "truncated" in (res.error or "")

    # 10. Non-zero exit code
    def test_nonzero_exit_code(self) -> None:
        res = parse_proc_meminfo("", stderr="cat: /proc/meminfo: closed", return_code=1)
        assert res.status == "ERROR"

    # 11. Permission denied (RESTRICTED)
    def test_permission_denied(self) -> None:
        res = parse_proc_meminfo("", stderr="cat: /proc/meminfo: Permission denied", return_code=1)
        assert res.status == "RESTRICTED"

    # 13. Unit validation tests (strictly requires kB, rejects missing/unknown/truncated)
    def test_invalid_unit_on_mem_total(self) -> None:
        stdout = "MemTotal: 100 furlongs\nMemFree: 50 kB\n"
        res = parse_proc_meminfo(stdout)
        assert res.status == "INCONCLUSIVE"
        assert "expected 'kB'" in (res.error or "")

    def test_missing_or_truncated_unit_on_optional_field_omitted(self) -> None:
        stdout = (
            "MemTotal:        4000000 kB\n"
            "MemFree:         2\n"  # missing unit
            "MemAvailable:    2 k\n"  # truncated unit
        )
        res = parse_proc_meminfo(stdout)
        assert res.status == "PASS"
        assert res.telemetry is not None
        assert res.telemetry.mem_total_bytes == 4000000 * 1024
        assert res.telemetry.mem_free_bytes is None  # omitted due to invalid unit
        assert res.telemetry.mem_available_bytes is None  # omitted due to invalid unit

    # 14. Duplicate key handling (identical tolerated, conflicting -> INCONCLUSIVE)
    def test_conflicting_duplicate_mem_total(self) -> None:
        stdout = (
            "MemTotal:        1000000 kB\n"
            "MemTotal:        5000000 kB\n"
            "MemFree:          500000 kB\n"
        )
        res = parse_proc_meminfo(stdout)
        assert res.status == "INCONCLUSIVE"
        assert "Conflicting duplicate" in (res.error or "")

    def test_identical_duplicate_mem_total(self) -> None:
        stdout = (
            "MemTotal:        1000000 kB\n"
            "MemTotal:        1000000 kB\n"
            "MemFree:          500000 kB\n"
        )
        res = parse_proc_meminfo(stdout)
        assert res.status == "PASS"
        assert res.telemetry is not None
        assert res.telemetry.mem_total_bytes == 1000000 * 1024


# ============================================================
# Thermal Telemetry Parser Tests (dumpsys thermalservice)
# ============================================================


class TestThermalParser:
    """Tests for parse_dumpsys_thermal."""

    # 1. Valid representative output
    def test_valid_output(self) -> None:
        stdout = (
            "Current Thermal Status: 0\n"
            "Thermal Temperatures:\n"
            "    Temperature{mValue=35.5, mType=3, mName=cpu-0-0-usr, mStatus=0}\n"
            "    Temperature{mValue=31.2, mType=0, mName=battery, mStatus=0}\n"
            "Thermal Hal Ready: true\n"
        )
        res = parse_dumpsys_thermal(stdout)
        assert res.status == "PASS"
        assert res.telemetry is not None
        assert res.telemetry.thermal_status_code == 0
        assert res.telemetry.thermal_status_label == "NONE"
        assert res.telemetry.sensor_count == 2
        assert res.telemetry.sensors[0].name == "cpu-0-0-usr"
        assert res.telemetry.sensors[0].temperature_celsius == 35.5
        assert res.telemetry.sensors[1].name == "battery"
        assert res.telemetry.sensors[1].temperature_celsius == 31.2

    # 2. Whitespace variation
    def test_whitespace_variation(self) -> None:
        stdout = (
            "  Current   Thermal   Status:   2  \r\n"
            "  Temperature{ mValue=42.0 , mType=1 , mName=gpu , mStatus=0 } \r\n"
        )
        res = parse_dumpsys_thermal(stdout)
        assert res.status == "PASS"
        assert res.telemetry is not None
        assert res.telemetry.thermal_status_code == 2
        assert res.telemetry.thermal_status_label == "MODERATE"
        assert res.telemetry.sensor_count == 1
        assert res.telemetry.sensors[0].temperature_celsius == 42.0

    # 3. Extra unknown lines / vendor extensions
    def test_extra_lines(self) -> None:
        stdout = (
            "Some vendor thermal header\n"
            "Cooling Devices:\n"
            "    CoolingDevice{mValue=0, mType=1, mName=fan}\n"
            "Current Thermal Status: 1\n"
            "Thermal Temperatures:\n"
            "    Temperature{mValue=38.0, mType=3, mName=cpu-cluster, mStatus=0}\n"
        )
        res = parse_dumpsys_thermal(stdout)
        assert res.status == "PASS"
        assert res.telemetry is not None
        assert res.telemetry.thermal_status_code == 1
        assert res.telemetry.thermal_status_label == "LIGHT"
        assert res.telemetry.sensor_count == 1

    # 4. Status only (no individual sensor objects)
    def test_status_only_valid(self) -> None:
        stdout = "Current Thermal Status: 0\nThermal Hal Ready: true\n"
        res = parse_dumpsys_thermal(stdout)
        assert res.status == "PASS"
        assert res.telemetry is not None
        assert res.telemetry.thermal_status_code == 0
        assert res.telemetry.sensor_count == 0

    # 5. Missing required fields (neither status nor sensors)
    def test_missing_all_thermal_fields(self) -> None:
        stdout = "Thermal Hal Ready: false\n"
        res = parse_dumpsys_thermal(stdout)
        assert res.status == "INCONCLUSIVE"
        assert res.telemetry is None

    # 6. Empty output
    def test_empty_output(self) -> None:
        res = parse_dumpsys_thermal("")
        assert res.status == "INCONCLUSIVE"
        assert "empty output" in (res.error or "")

    # 7. Malformed numbers (unparseable temp)
    def test_malformed_numbers(self) -> None:
        stdout = "Temperature{mValue=bad_number, mName=cpu}\n"
        res = parse_dumpsys_thermal(stdout)
        assert res.status == "INCONCLUSIVE"

    # 8. Impossible values skipped (e.g. 50000 millidegree or negative error codes)
    def test_impossible_values_skipped(self) -> None:
        stdout = (
            "Current Thermal Status: 0\n"
            "Temperature{mValue=45000.0, mName=sensor_millideg}\n"  # implausible Celsius, should be skipped
            "Temperature{mValue=-999.0, mName=sensor_error}\n"  # error reading, should be skipped
            "Temperature{mValue=36.0, mName=cpu}\n"  # valid
        )
        res = parse_dumpsys_thermal(stdout)
        assert res.status == "PASS"
        assert res.telemetry is not None
        assert res.telemetry.sensor_count == 1
        assert res.telemetry.sensors[0].name == "cpu"
        assert res.telemetry.sensors[0].temperature_celsius == 36.0

    # 9. Truncated output
    def test_truncated_output(self) -> None:
        stdout = "Current Thermal Status: 0\nTemperature{mValue=35.0"
        res = parse_dumpsys_thermal(stdout, truncated=True)
        assert res.status == "INCONCLUSIVE"
        assert "truncated" in (res.error or "")

    # 10. Service absent (UNSUPPORTED)
    def test_service_absent(self) -> None:
        stdout = "Can't find service: thermalservice\n"
        res = parse_dumpsys_thermal(stdout)
        assert res.status == "UNSUPPORTED"
        assert "not available" in (res.error or "")

    # 11. Permission denied (RESTRICTED)
    def test_permission_denied(self) -> None:
        stdout = "Permission Denial: can't dump thermalservice\n"
        res = parse_dumpsys_thermal(stdout)
        assert res.status == "RESTRICTED"

    # 12. Privacy
    def test_privacy_no_leakage(self) -> None:
        stdout = (
            "Current Thermal Status: 0\n"
            "Active Client: com.secret.package.name\n"
            "Temperature{mValue=33.0, mName=cpu}\n"
        )
        res = parse_dumpsys_thermal(stdout)
        assert res.status == "PASS"
        assert res.telemetry is not None
        assert "com.secret.package" not in str(res.telemetry)

    # 13. Rejection of NaN, +inf, -inf
    def test_nan_inf_temperatures_rejected(self) -> None:
        stdout = (
            "Current Thermal Status: 0\n"
            "Temperature{mValue=NaN, mName=cpu-nan}\n"
            "Temperature{mValue=Infinity, mName=cpu-inf}\n"
            "Temperature{mValue=-Infinity, mName=cpu-neginf}\n"
            "Temperature{mValue=inf, mName=cpu-inf2}\n"
            "Temperature{mValue=-inf, mName=cpu-neginf2}\n"
        )
        res = parse_dumpsys_thermal(stdout)
        assert res.status == "PASS"  # Still PASSes because thermal status 0 is valid
        assert res.telemetry is not None
        assert res.telemetry.sensor_count == 0  # All non-finite sensors rejected!
        assert len(res.telemetry.sensors) == 0

    # 14. Deduplication of sensors across HAL and Cached sections (HAL preferred)
    def test_cached_and_hal_sensor_deduplication(self) -> None:
        stdout = (
            "Current Thermal Status: 0\n"
            "Current temperatures from HAL:\n"
            "    Temperature{mValue=38.5, mType=3, mName=cpu-0, mStatus=0}\n"
            "    Temperature{mValue=41.0, mType=3, mName=cpu-1, mStatus=0}\n"
            "Cached temperatures:\n"
            "    Temperature{mValue=35.0, mType=3, mName=cpu-0, mStatus=0}\n"
            "    Temperature{mValue=39.0, mType=3, mName=cpu-1, mStatus=0}\n"
        )
        res = parse_dumpsys_thermal(stdout)
        assert res.status == "PASS"
        assert res.telemetry is not None
        # Assert each logical sensor is counted exactly once
        assert res.telemetry.sensor_count == 2
        assert len(res.telemetry.sensors) == 2
        sensor_map = {s.name: s.temperature_celsius for s in res.telemetry.sensors}
        # Assert HAL reading (38.5) was preferred over cached (35.0)
        assert sensor_map["cpu-0"] == 38.5
        assert sensor_map["cpu-1"] == 41.0


# ============================================================
# Display Metrics Parser Tests (wm size + wm density)
# ============================================================


class TestDisplayParser:
    """Tests for parse_display_metrics."""

    # 1. Valid representative output
    def test_valid_output(self) -> None:
        size_out = "Physical size: 1080x2400\n"
        density_out = "Physical density: 440\n"
        res = parse_display_metrics(size_out, density_out)
        assert res.status == "PASS"
        assert res.metrics is not None
        assert res.metrics.physical_width == 1080
        assert res.metrics.physical_height == 2400
        assert res.metrics.physical_density == 440
        assert res.metrics.override_width is None
        assert res.metrics.override_height is None
        assert res.metrics.override_density is None

    # 2. Output with overrides
    def test_valid_with_overrides(self) -> None:
        size_out = "Physical size: 1440x3200\nOverride size: 1080x2400\n"
        density_out = "Physical density: 560\nOverride density: 420\n"
        res = parse_display_metrics(size_out, density_out)
        assert res.status == "PASS"
        assert res.metrics is not None
        assert res.metrics.physical_width == 1440
        assert res.metrics.physical_height == 3200
        assert res.metrics.physical_density == 560
        assert res.metrics.override_width == 1080
        assert res.metrics.override_height == 2400
        assert res.metrics.override_density == 420

    # 3. Whitespace variation
    def test_whitespace_variation(self) -> None:
        size_out = "  Physical   size:   720x1600  \r\n"
        density_out = "  Physical   density:   320  \r\n"
        res = parse_display_metrics(size_out, density_out)
        assert res.status == "PASS"
        assert res.metrics is not None
        assert res.metrics.physical_width == 720
        assert res.metrics.physical_height == 1600
        assert res.metrics.physical_density == 320

    # 4. Extra lines
    def test_extra_lines(self) -> None:
        size_out = "Display 0:\nPhysical size: 1080x2340\nDisplay state: ON\n"
        density_out = "Display 0:\nPhysical density: 400\n"
        res = parse_display_metrics(size_out, density_out)
        assert res.status == "PASS"
        assert res.metrics is not None
        assert res.metrics.physical_width == 1080
        assert res.metrics.physical_height == 2340
        assert res.metrics.physical_density == 400

    # 5. Missing required field (size missing density present)
    def test_missing_size_field(self) -> None:
        size_out = "Display state: ON\n"
        density_out = "Physical density: 400\n"
        res = parse_display_metrics(size_out, density_out)
        assert res.status == "INCONCLUSIVE"
        assert res.metrics is None
        assert "Could not parse physical display size" in (res.error or "")

    # 6. Empty output
    def test_empty_output(self) -> None:
        res = parse_display_metrics("", "Physical density: 400\n")
        assert res.status == "INCONCLUSIVE"
        assert "empty output" in (res.error or "")

    # 7. Malformed numbers
    def test_malformed_numbers(self) -> None:
        size_out = "Physical size: 1080xABC\n"
        density_out = "Physical density: 400\n"
        res = parse_display_metrics(size_out, density_out)
        assert res.status == "INCONCLUSIVE"

    # 8. Impossible values (e.g. 0x0 resolution, or 500,000 dpi)
    def test_impossible_values(self) -> None:
        size_out = "Physical size: 0x0\n"
        density_out = "Physical density: 400\n"
        res = parse_display_metrics(size_out, density_out)
        assert res.status == "INCONCLUSIVE"
        assert "bounds" in (res.error or "") or "positive" in (res.error or "")

    # 9. Truncated output
    def test_truncated_output(self) -> None:
        size_out = "Physical size: 1080x2400\n"
        density_out = "Physical density: 440\n"
        res = parse_display_metrics(size_out, density_out, truncated=True)
        assert res.status == "INCONCLUSIVE"
        assert "truncated" in (res.error or "")

    # 10. Non-zero exit code
    def test_nonzero_exit_code(self) -> None:
        res = parse_display_metrics("out", "out", size_rc=1)
        assert res.status == "ERROR"

    # 11. Command not found (UNSUPPORTED)
    def test_command_not_found(self) -> None:
        res = parse_display_metrics(
            "", "", size_stderr="/system/bin/sh: wm: not found", size_rc=127
        )
        assert res.status == "UNSUPPORTED"
        assert "not available" in (res.error or "")

    # 12. Permission denied (RESTRICTED)
    def test_permission_denied(self) -> None:
        res = parse_display_metrics(
            "", "", size_stderr="SecurityException: Permission Denial", size_rc=1
        )
        assert res.status == "RESTRICTED"


# ============================================================
# Camera Inventory Parser Tests (dumpsys media.camera)
# ============================================================


class TestCameraParser:
    """Tests for parse_camera_inventory."""

    # 1. Valid representative output
    def test_valid_output(self) -> None:
        stdout = (
            "Camera module HAL API version: 0x204\n"
            "Camera [0]:\n"
            "    Facing: BACK\n"
            "    Orientation: 90\n"
            "Camera [1]:\n"
            "    Facing: FRONT\n"
            "    Orientation: 270\n"
            "Number of camera devices: 2\n"
        )
        res = parse_camera_inventory(stdout)
        assert res.status == "PASS"
        assert res.inventory is not None
        assert res.inventory.camera_count == 2
        assert len(res.inventory.cameras) == 2
        assert res.inventory.cameras[0].camera_id == "0"
        assert res.inventory.cameras[0].facing == "BACK"
        assert res.inventory.cameras[1].camera_id == "1"
        assert res.inventory.cameras[1].facing == "FRONT"

    # 2. Format variant (HAL Device info)
    def test_format_variant_hal_info(self) -> None:
        stdout = (
            "== Camera Hal Device Information ==\n"
            "Device 0:\n"
            "  Facing: Back\n"
            "Device 1:\n"
            "  Facing: Front\n"
            "Device 2:\n"
            "  Facing: External\n"
            "Number of normal camera devices: 3\n"
        )
        res = parse_camera_inventory(stdout)
        assert res.status == "PASS"
        assert res.inventory is not None
        assert res.inventory.camera_count == 3
        assert len(res.inventory.cameras) == 3
        assert res.inventory.cameras[0].facing == "BACK"
        assert res.inventory.cameras[1].facing == "FRONT"
        assert res.inventory.cameras[2].facing == "EXTERNAL"

    # 3. Numeric facing codes (0=BACK, 1=FRONT, 2=EXTERNAL)
    def test_numeric_facing_codes(self) -> None:
        stdout = (
            "Camera ID 0:\n"
            "    Facing: 0\n"
            "Camera ID 1:\n"
            "    Facing: 1\n"
            "Number of camera devices: 2\n"
        )
        res = parse_camera_inventory(stdout)
        assert res.status == "PASS"
        assert res.inventory is not None
        assert res.inventory.cameras[0].facing == "BACK"
        assert res.inventory.cameras[1].facing == "FRONT"

    # 4. Whitespace variation
    def test_whitespace_variation(self) -> None:
        stdout = (
            "  Number   of   camera   devices:   1  \r\n"
            "  Camera [0]: \r\n"
            "      Facing:   BACK  \r\n"
        )
        res = parse_camera_inventory(stdout)
        assert res.status == "PASS"
        assert res.inventory is not None
        assert res.inventory.camera_count == 1
        assert res.inventory.cameras[0].camera_id == "0"

    # 5. Missing required field (no count, no camera sections)
    def test_missing_required_fields(self) -> None:
        stdout = "Camera module API version: 0x200\nNo further details\n"
        res = parse_camera_inventory(stdout)
        assert res.status == "INCONCLUSIVE"
        assert res.inventory is None

    # 6. Empty output
    def test_empty_output(self) -> None:
        res = parse_camera_inventory("")
        assert res.status == "INCONCLUSIVE"
        assert "empty output" in (res.error or "")

    # 7. Conservative handling of 0 cameras (INCONCLUSIVE, never hardware FAIL)
    def test_zero_cameras_is_inconclusive(self) -> None:
        stdout = "Number of camera devices: 0\n"
        res = parse_camera_inventory(stdout)
        assert res.status == "INCONCLUSIVE"
        assert res.inventory is not None
        assert res.inventory.camera_count == 0
        assert "0 camera" in (res.error or "")

    # 8. Truncated output
    def test_truncated_output(self) -> None:
        stdout = "Number of camera devices: 2\nCamera [0]:\n"
        res = parse_camera_inventory(stdout, truncated=True)
        assert res.status == "INCONCLUSIVE"
        assert "truncated" in (res.error or "")

    # 9. Service absent (UNSUPPORTED)
    def test_service_absent(self) -> None:
        stdout = "Can't find service: media.camera\n"
        res = parse_camera_inventory(stdout)
        assert res.status == "UNSUPPORTED"

    # 10. Permission denied (RESTRICTED)
    def test_permission_denied(self) -> None:
        stdout = "Permission Denial: cannot access media.camera service\n"
        res = parse_camera_inventory(stdout)
        assert res.status == "RESTRICTED"

    # 11. Non-zero exit code
    def test_nonzero_exit_code(self) -> None:
        res = parse_camera_inventory("", stderr="binder transaction failed", return_code=1)
        assert res.status == "ERROR"

    # 12. Privacy filter: Active clients, packages, and PIDs actively discarded!
    def test_privacy_active_clients_discarded(self) -> None:
        stdout = (
            "Number of camera devices: 1\n"
            "Camera [0]:\n"
            "    Facing: BACK\n"
            "Active Camera Clients:\n"
            "[\n"
            "    Client[0] (PID 1337, package com.sensitive.banking.app)\n"
            "    User: /data/user/0/com.sensitive.banking.app/files\n"
            "]\n"
        )
        res = parse_camera_inventory(stdout)
        assert res.status == "PASS"
        assert res.inventory is not None
        assert res.inventory.camera_count == 1
        assert len(res.inventory.cameras) == 1

        # Assert no sensitive string was preserved anywhere in the result
        res_str = repr(res)
        assert "com.sensitive.banking" not in res_str
        assert "1337" not in res_str
        assert "/data/user" not in res_str

    # 13. Explicit count > 0 but zero parsed devices -> INCONCLUSIVE (NO synthetic IDs!)
    def test_explicit_count_without_parsed_devices_is_inconclusive(self) -> None:
        stdout = "Number of camera devices: 2\nNo individual device blocks here\n"
        res = parse_camera_inventory(stdout)
        assert res.status == "INCONCLUSIVE"
        assert res.inventory is None
        assert "zero camera device records could be parsed" in (res.error or "")

    # 14. Count consistency: explicit count != parsed records -> INCONCLUSIVE
    def test_count_mismatch_fewer_devices_is_inconclusive(self) -> None:
        stdout = "Number of camera devices: 2\nCamera [0]:\n    Facing: BACK\n"
        res = parse_camera_inventory(stdout)
        assert res.status == "INCONCLUSIVE"
        assert res.inventory is None
        assert "Camera count mismatch" in (res.error or "")

    def test_count_mismatch_more_devices_is_inconclusive(self) -> None:
        stdout = (
            "Number of camera devices: 1\n"
            "Camera [0]:\n"
            "    Facing: BACK\n"
            "Camera [1]:\n"
            "    Facing: FRONT\n"
        )
        res = parse_camera_inventory(stdout)
        assert res.status == "INCONCLUSIVE"
        assert res.inventory is None
        assert "Camera count mismatch" in (res.error or "")

    # 15. Oversized camera count sanity bound
    def test_oversized_count_is_inconclusive(self) -> None:
        stdout = "Number of camera devices: 5000000\n"
        res = parse_camera_inventory(stdout)
        assert res.status == "INCONCLUSIVE"
        assert res.inventory is None
        assert "exceeds sanity bound" in (res.error or "")

    # 16. Duplicate camera references deduplicated
    def test_duplicate_camera_references_deduplicated(self) -> None:
        stdout = (
            "Number of camera devices: 1\n"
            "Device 0:\n"
            "    Facing: BACK\n"
            "Device 0 (v3.4) is closed, no client instance\n"
            "    Facing: BACK\n"
        )
        res = parse_camera_inventory(stdout)
        assert res.status == "PASS"
        assert res.inventory is not None
        assert res.inventory.camera_count == 1
        assert len(res.inventory.cameras) == 1

    # 17. Modern AOSP 'Device X is closed, no client instance' parsing
    def test_modern_aosp_closed_device_parsing(self) -> None:
        stdout = (
            "== Camera HAL device info: ==\n"
            "Number of camera devices: 2\n"
            "Device 0 (v3.4) is closed, no client instance\n"
            "    Facing: BACK\n"
            "Device 1 (v3.4) is closed, no client instance\n"
            "    Facing: FRONT\n"
        )
        res = parse_camera_inventory(stdout)
        assert res.status == "PASS"
        assert res.inventory is not None
        assert res.inventory.camera_count == 2
        assert len(res.inventory.cameras) == 2
        assert res.inventory.cameras[0].camera_id == "0"
        assert res.inventory.cameras[0].facing == "BACK"
        assert res.inventory.cameras[1].camera_id == "1"
        assert res.inventory.cameras[1].facing == "FRONT"

    # 18. Client section ignored safely without swallowing subsequent camera devices
    def test_client_section_ignored_and_subsequent_devices_parsed(self) -> None:
        stdout = (
            "Active Camera Clients:\n"
            'Client[0] (PID 5555, package "fake.sensitive.package")\n'
            "Client history:\n"
            "User sessions logged here\n"
            "== Camera HAL device info: ==\n"
            "Number of camera devices: 2\n"
            "Device 0:\n"
            "    Facing: BACK\n"
            "Device 1:\n"
            "    Facing: FRONT\n"
        )
        res = parse_camera_inventory(stdout)
        assert res.status == "PASS"
        assert res.inventory is not None
        assert res.inventory.camera_count == 2
        assert len(res.inventory.cameras) == 2
        assert "fake.sensitive.package" not in repr(res)
