package org.vector.probe;

import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;

final class SensorCollector {
    private SensorCollector() { }
    static void start(DiagnosticController c, DiagnosticJob job, Sensor sensor) {
        int type = sensor.getType();
        job.metric("sensor_type", type, "enum");
        String unit;
        int dimensions;
        switch (type) {
            case Sensor.TYPE_ACCELEROMETER: case Sensor.TYPE_GRAVITY: case Sensor.TYPE_LINEAR_ACCELERATION: unit = "m_s2"; dimensions = 3; break;
            case Sensor.TYPE_GYROSCOPE: unit = "rad_s"; dimensions = 3; break;
            case Sensor.TYPE_MAGNETIC_FIELD: unit = "uT"; dimensions = 3; break;
            case Sensor.TYPE_ROTATION_VECTOR: case Sensor.TYPE_GAME_ROTATION_VECTOR: case Sensor.TYPE_GEOMAGNETIC_ROTATION_VECTOR: unit = "unitless"; dimensions = 3; break;
            case Sensor.TYPE_LIGHT: unit = "lux"; dimensions = 1; break;
            case Sensor.TYPE_PROXIMITY: unit = "cm"; dimensions = 1; break;
            case Sensor.TYPE_PRESSURE: unit = "hPa"; dimensions = 1; break;
            case Sensor.TYPE_AMBIENT_TEMPERATURE: unit = "celsius"; dimensions = 1; break;
            case Sensor.TYPE_RELATIVE_HUMIDITY: unit = "percent"; dimensions = 1; break;
            case Sensor.TYPE_STEP_COUNTER: case Sensor.TYPE_STEP_DETECTOR: unit = "count"; dimensions = 1; break;
            default: c.finish(job, "UNSUPPORTED", "SAMPLING_UNSUPPORTED"); return;
        }
        SensorManager manager = c.activity.getSystemService(SensorManager.class);
        if (manager == null) { c.finish(job, "UNSUPPORTED", "HARDWARE_ABSENT"); return; }
        DiagnosticJob.Samples samples = new DiagnosticJob.Samples(dimensions);
        SensorEventListener listener = new SensorEventListener() {
            Float initialSteps;
            @Override public void onSensorChanged(SensorEvent event) {
                if (!c.current(job)) return;
                float[] values = event.values;
                if (type == Sensor.TYPE_STEP_COUNTER && values.length > 0) {
                    if (initialSteps == null) initialSteps = values[0];
                    values = new float[]{values[0] - initialSteps};
                }
                samples.add(values); samples.write(job, unit);
            }
            @Override public void onAccuracyChanged(Sensor changed, int accuracy) {
                if (c.current(job)) job.metric("sensor_accuracy", accuracy, "enum");
            }
        };
        if (!c.own(job, () -> manager.unregisterListener(listener))) return;
        boolean registered = manager.registerListener(listener, sensor, 100000, c.main);
        job.metric("registered", registered ? 1 : 0, "boolean");
        if (!registered) { c.finish(job, "INCONCLUSIVE", "REGISTRATION_REJECTED"); return; }
        c.main.postDelayed(() -> {
            if (!c.current(job)) return;
            String permission = DiagnosticRegistry.permission(job.id, sensor);
            if (permission != null && c.activity.checkSelfPermission(permission) != android.content.pm.PackageManager.PERMISSION_GRANTED) {
                c.finish(job, "RESTRICTED", "PERMISSION_DENIED"); return;
            }
            samples.write(job, unit);
            c.finish(job, "INCONCLUSIVE", samples.count > 0 ? "SAMPLES_OBSERVED" : "NO_SAMPLES");
        }, 3000);
    }
}
