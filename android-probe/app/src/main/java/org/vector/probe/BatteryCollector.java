package org.vector.probe;

import android.content.Intent;
import android.content.IntentFilter;
import android.os.BatteryManager;
import android.os.Build;

final class BatteryCollector {
    private BatteryCollector() { }
    static void start(DiagnosticController c, DiagnosticJob job) {
        collect(c, job, false);
        c.main.postDelayed(() -> {
            if (!c.current(job)) return;
            try { collect(c, job, true); c.finish(job, "INCONCLUSIVE", "TELEMETRY_ONLY"); }
            catch (SecurityException e) { c.finish(job, "RESTRICTED", "PERMISSION_DENIED"); }
            catch (RuntimeException e) { c.finish(job, "ERROR", "EXECUTION_ERROR"); }
        }, 3000);
    }
    private static void collect(DiagnosticController c, DiagnosticJob job, boolean second) {
        Intent value = c.activity.registerReceiver(null, new IntentFilter(Intent.ACTION_BATTERY_CHANGED));
        BatteryManager manager = c.activity.getSystemService(BatteryManager.class);
        String prefix = second ? "end_" : "";
        String[] keys = {BatteryManager.EXTRA_LEVEL, BatteryManager.EXTRA_SCALE, BatteryManager.EXTRA_STATUS,
                BatteryManager.EXTRA_PLUGGED, BatteryManager.EXTRA_TEMPERATURE, BatteryManager.EXTRA_VOLTAGE, BatteryManager.EXTRA_HEALTH};
        String[] names = {"battery_level", "battery_scale", "battery_status", "power_source", "battery_temperature", "battery_voltage", "battery_health"};
        String[] units = {"count", "count", "enum", "enum", "deci_celsius", "mV", "enum"};
        for (int i = 0; i < keys.length; i++) job.metric(prefix + names[i], value != null && value.hasExtra(keys[i]) ? value.getIntExtra(keys[i], -1) : null, units[i]);
        int[] properties = {BatteryManager.BATTERY_PROPERTY_CHARGE_COUNTER, BatteryManager.BATTERY_PROPERTY_CURRENT_NOW,
                BatteryManager.BATTERY_PROPERTY_CURRENT_AVERAGE, BatteryManager.BATTERY_PROPERTY_CAPACITY};
        String[] propNames = {"charge_counter", "current_now", "current_average", "capacity_percent"};
        String[] propUnits = {"uAh", "uA", "uA", "percent"};
        for (int i = 0; i < properties.length; i++) {
            int reading = manager == null ? Integer.MIN_VALUE : manager.getIntProperty(properties[i]);
            job.metric(prefix + propNames[i], reading == Integer.MIN_VALUE ? null : reading, propUnits[i]);
        }
        if (!second) job.metric("cycle_count", Build.VERSION.SDK_INT >= 34 && value != null && value.hasExtra(BatteryManager.EXTRA_CYCLE_COUNT)
                ? value.getIntExtra(BatteryManager.EXTRA_CYCLE_COUNT, -1) : null, "count");
    }
}
