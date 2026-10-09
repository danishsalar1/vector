package org.vector.probe;

import android.content.Context;
import android.content.pm.PackageManager;
import android.hardware.Sensor;
import android.hardware.SensorManager;
import android.hardware.camera2.CameraAccessException;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraManager;
import android.hardware.camera2.CaptureRequest;
import android.os.Build;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Runtime-owned opaque ordinals, never brand/model assumptions or hardware identifiers. */
final class DiagnosticRegistry {
    final Map<String, Sensor> sensors = new LinkedHashMap<>();
    final Map<String, String> cameras = new LinkedHashMap<>();
    private final List<Map<String, Object>> entries = new ArrayList<>();
    private String cameraDiscoveryOutcome = "UNSUPPORTED";

    DiagnosticRegistry(Context context) {
        for (String id : new String[]{"battery", "system", "storage", "display", "connectivity", "audio_routes"}) {
            add(id, true, false);
        }
        add("pixels", true, true);
        add("touch", context.getPackageManager().hasSystemFeature(PackageManager.FEATURE_TOUCHSCREEN), true);
        add("speaker", context.getPackageManager().hasSystemFeature(PackageManager.FEATURE_AUDIO_OUTPUT), true);
        add("microphone", context.getPackageManager().hasSystemFeature(PackageManager.FEATURE_MICROPHONE), true);
        android.os.Vibrator vibrator = context.getSystemService(android.os.Vibrator.class);
        add("vibration", vibrator != null && vibrator.hasVibrator(), true);

        SensorManager sm = context.getSystemService(SensorManager.class);
        if (sm != null) {
            List<Sensor> list = sm.getSensorList(Sensor.TYPE_ALL);
            java.util.Set<Sensor> assigned = new java.util.HashSet<>();
            int ordinal = 0;
            for (int type : new int[]{Sensor.TYPE_ACCELEROMETER, Sensor.TYPE_GYROSCOPE, Sensor.TYPE_MAGNETIC_FIELD,
                    Sensor.TYPE_LIGHT, Sensor.TYPE_PROXIMITY, Sensor.TYPE_PRESSURE, Sensor.TYPE_GRAVITY,
                    Sensor.TYPE_LINEAR_ACCELERATION, Sensor.TYPE_ROTATION_VECTOR, Sensor.TYPE_STEP_DETECTOR, Sensor.TYPE_STEP_COUNTER}) {
                Sensor sensor = sm.getDefaultSensor(type);
                String id = "sensor_" + ordinal++;
                Map<String, Object> entry = add(id, sensor != null, false);
                entry.put("sensor_type", type);
                if (sensor != null) {
                    populateSensorMetadata(entry, sensor);
                    sensors.put(id, sensor);
                    assigned.add(sensor);
                }
            }
            for (Sensor sensor : list) {
                if (assigned.contains(sensor)) continue;
                if (ordinal == 64) break;
                String id = "sensor_" + ordinal++;
                sensors.put(id, sensor);
                Map<String, Object> entry = add(id, true, false);
                populateSensorMetadata(entry, sensor);
            }
        }

        CameraManager cm = context.getSystemService(CameraManager.class);
        if (cm != null) try {
            for (String camera : cm.getCameraIdList()) {
                if (cameras.size() == 16) break;
                String id = "camera_" + cameras.size();
                cameras.put(id, camera);
                Map<String, Object> entry = add(id, true, false);
                try {
                    CameraCharacteristics info = cm.getCameraCharacteristics(camera);
                    entry.put("camera_facing", info.get(CameraCharacteristics.LENS_FACING));
                    entry.put("camera_level", info.get(CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL));
                    Boolean flash = info.get(CameraCharacteristics.FLASH_INFO_AVAILABLE);
                    entry.put("flash_available", flash);
                    int[] modes = info.get(CameraCharacteristics.CONTROL_AF_AVAILABLE_MODES);
                    boolean autofocus = false;
                    if (modes != null) {
                        for (int mode : modes) {
                            if (mode == CaptureRequest.CONTROL_AF_MODE_AUTO) autofocus = true;
                        }
                    }
                    entry.put("autofocus_available", modes == null ? null : autofocus);
                } catch (Exception ignored) {
                    // Safe best-effort capability discovery
                }
            }
            if (cameras.isEmpty()) add("camera_0", false, false);
        } catch (CameraAccessException error) {
            cameraDiscoveryOutcome = "ERROR";
            add("camera_unavailable", false, false);
        } catch (SecurityException error) {
            cameraDiscoveryOutcome = "RESTRICTED";
            add("camera_unavailable", false, false);
        }
    }

    private static void populateSensorMetadata(Map<String, Object> entry, Sensor sensor) {
        entry.put("sensor_type", sensor.getType());
        entry.put("reporting_mode", sensor.getReportingMode());
        float maxRange = sensor.getMaximumRange();
        if (Float.isFinite(maxRange) && maxRange >= 0.0f) {
            entry.put("max_range", (double) maxRange);
        } else {
            entry.put("max_range", null);
        }
        float resolution = sensor.getResolution();
        if (Float.isFinite(resolution) && resolution >= 0.0f) {
            entry.put("resolution", (double) resolution);
        } else {
            entry.put("resolution", null);
        }
    }

    private Map<String, Object> add(String id, boolean available, boolean interactive) {
        Map<String, Object> entry = new LinkedHashMap<>();
        entry.put("diagnostic_id", id);
        entry.put("available", available);
        entry.put("interactive", interactive);
        entry.put("sensor_type", null);
        entry.put("reporting_mode", null);
        entry.put("max_range", null);
        entry.put("resolution", null);
        entry.put("camera_facing", null);
        entry.put("camera_level", null);
        entry.put("flash_available", null);
        entry.put("autofocus_available", null);
        entries.add(entry);
        return entry;
    }

    List<Map<String, Object>> snapshot() { return new ArrayList<>(entries); }

    boolean known(String id) {
        for (Map<String, Object> entry : entries) {
            if (id.equals(entry.get("diagnostic_id"))) return true;
        }
        return false;
    }

    boolean available(String id) {
        for (Map<String, Object> entry : entries) {
            if (id.equals(entry.get("diagnostic_id"))) return Boolean.TRUE.equals(entry.get("available"));
        }
        return false;
    }

    String unavailableOutcome(String id) {
        return id.equals("camera_unavailable") ? cameraDiscoveryOutcome : "UNSUPPORTED";
    }

    static String permission(String id, Sensor sensor) {
        if (id.startsWith("camera_")) return android.Manifest.permission.CAMERA;
        if (id.equals("microphone")) return android.Manifest.permission.RECORD_AUDIO;
        if (sensor != null && Build.VERSION.SDK_INT >= 29
                && (sensor.getType() == Sensor.TYPE_STEP_COUNTER || sensor.getType() == Sensor.TYPE_STEP_DETECTOR)) {
            return android.Manifest.permission.ACTIVITY_RECOGNITION;
        }
        return null;
    }
}
