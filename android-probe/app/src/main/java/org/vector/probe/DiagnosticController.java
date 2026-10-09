package org.vector.probe;

import android.app.Activity;
import android.content.pm.PackageManager;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import java.util.List;
import java.util.Map;

/** Socket calls never wait for collectors or people. All Android resources belong to main. */
final class DiagnosticController implements AutoCloseable, ControlProtocol.Diagnostics {
    interface StatusListener {
        void onDiagnosticActive(String id);
        void onDiagnosticIdle();
    }

    final Activity activity;
    final Handler main = new Handler(Looper.getMainLooper());
    final DiagnosticRegistry registry;
    final DiagnosticUi ui;
    private DiagnosticJob active;
    private final DiagnosticSession session = new DiagnosticSession();
    private AutoCloseable resource;
    private boolean closed;
    private boolean cleaning;
    private StatusListener statusListener;

    DiagnosticController(Activity activity, android.widget.LinearLayout host) {
        this(activity, host, null);
    }

    DiagnosticController(Activity activity, android.widget.LinearLayout host, StatusListener statusListener) {
        this.activity = activity;
        this.registry = new DiagnosticRegistry(activity);
        this.ui = new DiagnosticUi(this, host);
        this.statusListener = statusListener;
    }

    void setStatusListener(StatusListener listener) {
        this.statusListener = listener;
    }

    DiagnosticJob getActiveJob() { return active; }

    @Override public boolean isExhausted() { return session.isExhausted(); }

    @Override public List<Map<String, Object>> capabilities() { return registry.snapshot(); }

    @Override public synchronized Map<String, Object> command(String operation, Map<String, Object> binding) {
        if (closed) return null;
        if (operation.equals("START_CHALLENGE")) {
            if (cleaning || (active != null && active.running())) return null;
            DiagnosticJob job = session.start(binding, now());
            if (job == null) return null;
            active = job;
            main.post(() -> start(job));
            main.postDelayed(() -> cancel(job, true), 60000);
        } else if (session.lookup(binding) == null) return null;
        if (operation.equals("CANCEL_CHALLENGE")) cancel(active, false);
        return active.snapshot(now());
    }

    static long now() { return SystemClock.elapsedRealtime(); }
    synchronized boolean current(DiagnosticJob job) { return !closed && session.current(job); }
    boolean own(DiagnosticJob job, AutoCloseable value) {
        if (!current(job)) { release(value); return false; }
        resource = value; return true;
    }

    private void start(DiagnosticJob job) {
        if (!current(job)) return;
        ui.progress(job);
        if (statusListener != null) statusListener.onDiagnosticActive(job.id);

        if (!registry.known(job.id)) {
            finish(job, "UNSUPPORTED", "API_UNSUPPORTED");
            return;
        }

        if (!registry.available(job.id)) {
            String outcome = registry.unavailableOutcome(job.id);
            finish(job, outcome, outcome.equals("RESTRICTED") ? "PERMISSION_REQUIRED"
                    : outcome.equals("ERROR") ? "EXECUTION_ERROR" : "HARDWARE_ABSENT");
            return;
        }

        String permission = DiagnosticRegistry.permission(job.id, registry.sensors.get(job.id));
        if (permission != null && activity.checkSelfPermission(permission) != PackageManager.PERMISSION_GRANTED) {
            finish(job, "RESTRICTED", "PERMISSION_REQUIRED");
            ui.permission(permission);
            return;
        }

        try {
            if (registry.sensors.containsKey(job.id)) SensorCollector.start(this, job, registry.sensors.get(job.id));
            else if (registry.cameras.containsKey(job.id)) CameraCollector.start(this, job, registry.cameras.get(job.id));
            else switch (job.id) {
                case "battery": BatteryCollector.start(this, job); break;
                case "system": case "storage": case "display": case "connectivity": case "audio_routes": SystemCollector.start(this, job); break;
                case "microphone": case "speaker": case "vibration": AudioCollector.start(this, job); break;
                case "pixels": case "touch": ui.interactive(job); break;
                default: finish(job, "UNSUPPORTED", "API_UNSUPPORTED");
            }
        } catch (SecurityException error) { finish(job, "RESTRICTED", "PERMISSION_REQUIRED"); }
        catch (Exception error) { finish(job, "ERROR", "EXECUTION_ERROR"); }
    }

    void confirm(DiagnosticJob job) { if (current(job)) ui.confirm(job); }

    void finish(DiagnosticJob job, String outcome, String reason) {
        if (Looper.myLooper() != Looper.getMainLooper()) { main.post(() -> finish(job, outcome, reason)); return; }
        if (now() - job.started >= 60000) { cancel(job, true); return; }
        synchronized (this) {
            if (!current(job)) return;
            cleaning = true;
        }
        boolean released = cleanup();
        synchronized (this) {
            if (job.running()) job.finish(released ? outcome : "ERROR", released ? reason : "CLEANUP_ERROR", now());
            else job.stopped(released, now()); // a cancel arrived during cleanup: keep the real result
            cleaning = false;
        }
        ui.complete(job);
        if (statusListener != null) statusListener.onDiagnosticIdle();
    }

    /**
     * Stops collection at once (STOPPING freezes evidence) but publishes the terminal state only
     * after main has released the owned resource, so a cleanup failure is reported, never dropped.
     */
    void cancel(DiagnosticJob job, boolean timeout) {
        synchronized (this) {
            if (!current(job)) return;
            cleaning = true; job.stop(timeout);
        }
        Runnable work = () -> {
            boolean released = cleanup();
            synchronized (this) { job.stopped(released, now()); cleaning = false; }
            ui.complete(job);
            if (statusListener != null) statusListener.onDiagnosticIdle();
        };
        if (Looper.myLooper() == Looper.getMainLooper()) work.run(); else main.post(work);
    }

    private boolean cleanup() {
        AutoCloseable old = resource; resource = null;
        ui.clearInteraction();
        return release(old);
    }

    private static boolean release(AutoCloseable value) {
        if (value == null) return true;
        try { value.close(); return true; } catch (Exception error) { return false; }
    }

    @Override public void close() {
        synchronized (this) { closed = true; session.close(now()); }
        if (Looper.myLooper() == Looper.getMainLooper()) {
            main.removeCallbacksAndMessages(null);
            cleanup();
            if (statusListener != null) statusListener.onDiagnosticIdle();
        } else {
            main.post(() -> {
                main.removeCallbacksAndMessages(null);
                cleanup();
                if (statusListener != null) statusListener.onDiagnosticIdle();
            });
        }
    }
}
