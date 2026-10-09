package org.vector.probe;

import android.app.ActivityManager;
import android.content.pm.PackageManager;
import android.hardware.display.DisplayManager;
import android.hardware.usb.UsbManager;
import android.location.LocationManager;
import android.media.AudioDeviceInfo;
import android.media.AudioManager;
import android.net.wifi.WifiManager;
import android.nfc.NfcAdapter;
import android.os.Build;
import android.os.PowerManager;
import android.os.StatFs;
import android.provider.Settings;
import android.view.Display;
import java.io.IOException;

final class SystemCollector {
    private SystemCollector() { }

    private static final String[][] CONNECTIVITY_FEATURES = {
        {"feature_wifi", "android.hardware.wifi"},
        {"feature_bluetooth", "android.hardware.bluetooth"},
        {"feature_bluetooth_le", "android.hardware.bluetooth_le"},
        {"feature_nfc", "android.hardware.nfc"},
        {"feature_gps", "android.hardware.location.gps"},
        {"feature_usb_host", "android.hardware.usb.host"},
        {"feature_usb_accessory", "android.hardware.usb.accessory"},
        {"feature_telephony", "android.hardware.telephony"},
        {"feature_fingerprint", "android.hardware.fingerprint"},
        {"feature_face", "android.hardware.biometrics.face"},
        {"feature_iris", "android.hardware.biometrics.iris"},
        {"feature_camera_any", "android.hardware.camera.any"},
        {"feature_microphone", "android.hardware.microphone"},
        {"feature_accelerometer", "android.hardware.sensor.accelerometer"},
        {"feature_gyroscope", "android.hardware.sensor.gyroscope"},
        {"feature_compass", "android.hardware.sensor.compass"},
        {"feature_light", "android.hardware.sensor.light"},
        {"feature_proximity", "android.hardware.sensor.proximity"},
        {"feature_barometer", "android.hardware.sensor.barometer"},
        {"feature_multitouch", "android.hardware.touchscreen.multitouch"},
        {"feature_audio_output", "android.hardware.audio.output"}
    };

    static void start(DiagnosticController c, DiagnosticJob j) throws IOException {
        switch (j.id) {
            case "storage": storage(c, j); return;
            case "system": {
                ActivityManager am = c.activity.getSystemService(ActivityManager.class);
                if (am == null) { c.finish(j, "UNSUPPORTED", "API_UNSUPPORTED"); return; }
                ActivityManager.MemoryInfo info = new ActivityManager.MemoryInfo(); am.getMemoryInfo(info);
                j.metric("ram_total", info.totalMem, "bytes"); j.metric("ram_available", info.availMem, "bytes");
                j.metric("ram_threshold", info.threshold, "bytes"); j.metric("low_memory", info.lowMemory ? 1 : 0, "boolean");
                PowerManager pm = c.activity.getSystemService(PowerManager.class);
                j.metric("thermal_status", Build.VERSION.SDK_INT >= 29 && pm != null ? pm.getCurrentThermalStatus() : null, "enum");
                break;
            }
            case "display": {
                DisplayManager dm = c.activity.getSystemService(DisplayManager.class);
                Display d = dm == null ? null : dm.getDisplay(Display.DEFAULT_DISPLAY);
                if (d == null) { c.finish(j, "UNSUPPORTED", "HARDWARE_ABSENT"); return; }
                Display.Mode mode = d.getMode();
                j.metric("width", mode.getPhysicalWidth(), "pixels"); j.metric("height", mode.getPhysicalHeight(), "pixels");
                j.metric("refresh_rate", mode.getRefreshRate(), "Hz"); j.metric("rotation", d.getRotation(), "enum");
                Display.Mode[] modes = d.getSupportedModes(); j.metric("mode_count", modes.length, "count");
                for (int i = 0; i < Math.min(8, modes.length); i++) {
                    j.metric("mode" + i + "_width", modes[i].getPhysicalWidth(), "pixels");
                    j.metric("mode" + i + "_height", modes[i].getPhysicalHeight(), "pixels");
                    j.metric("mode" + i + "_rate", modes[i].getRefreshRate(), "Hz");
                }
                int brightness = Settings.System.getInt(c.activity.getContentResolver(), Settings.System.SCREEN_BRIGHTNESS, -1);
                j.metric("brightness", brightness < 0 ? null : brightness, "level_255"); break;
            }
            case "audio_routes": {
                AudioManager am = c.activity.getSystemService(AudioManager.class);
                if (am == null) { c.finish(j, "UNSUPPORTED", "API_UNSUPPORTED"); return; }
                AudioDeviceInfo[] routes = am.getDevices(AudioManager.GET_DEVICES_INPUTS | AudioManager.GET_DEVICES_OUTPUTS);
                j.metric("route_count", routes.length, "count");
                for (int i = 0; i < Math.min(routes.length, 24); i++) {
                    j.metric("route" + i + "_type", routes[i].getType(), "enum");
                    j.metric("route" + i + "_input", routes[i].isSource() ? 1 : 0, "boolean");
                }
                break;
            }
            case "connectivity": {
                PackageManager pm = c.activity.getPackageManager();
                for (String[] pair : CONNECTIVITY_FEATURES) {
                    j.metric(pair[0], pm.hasSystemFeature(pair[1]) ? 1 : 0, "boolean");
                }
                WifiManager wifi = c.activity.getApplicationContext().getSystemService(WifiManager.class);
                j.metric("wifi_enabled", wifi == null ? null : wifi.isWifiEnabled() ? 1 : 0, "boolean");
                android.nfc.NfcManager nm = c.activity.getSystemService(android.nfc.NfcManager.class);
                NfcAdapter nfc = nm == null ? null : nm.getDefaultAdapter();
                j.metric("nfc_enabled", nfc == null ? null : nfc.isEnabled() ? 1 : 0, "boolean");
                LocationManager lm = c.activity.getSystemService(LocationManager.class);
                j.metric("gps_provider", lm == null ? null : lm.getAllProviders().contains(LocationManager.GPS_PROVIDER) ? 1 : 0, "boolean");
                UsbManager usb = c.activity.getSystemService(UsbManager.class);
                j.metric("usb_devices", usb == null ? null : usb.getDeviceList().size(), "count");
                break;
            }
            default: c.finish(j, "UNSUPPORTED", "API_UNSUPPORTED"); return;
        }
        c.finish(j, "INCONCLUSIVE", j.id.equals("connectivity") || j.id.equals("audio_routes") ? "CAPABILITY_ONLY" : "TELEMETRY_ONLY");
    }

    private static void storage(DiagnosticController c, DiagnosticJob j) throws IOException {
        StatFs stats = new StatFs(c.activity.getCacheDir().getAbsolutePath());
        j.metric("storage_total", stats.getTotalBytes(), "bytes"); j.metric("storage_available", stats.getAvailableBytes(), "bytes");
        if (stats.getAvailableBytes() < 1024 * 1024) { c.finish(j, "INCONCLUSIVE", "INSUFFICIENT_SPACE"); return; }
        StorageCollector.start(c, j);
    }
}
