package org.vector.probe;

import static org.junit.Assert.*;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Looper;
import android.provider.Settings;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.Shadows;
import org.robolectric.annotation.Config;
import org.robolectric.android.controller.ActivityController;

@RunWith(RobolectricTestRunner.class)
@Config(sdk = {26, 35})
public final class DiagnosticAndroidTest {
    private ActivityController<Activity> activity;
    private DiagnosticController c;
    private LinearLayout host;

    @Before public void setup() {
        activity = Robolectric.buildActivity(Activity.class).setup();
        Shadows.shadowOf(activity.get().getPackageManager()).setSystemFeature(PackageManager.FEATURE_MICROPHONE, true);
        Shadows.shadowOf(activity.get().getPackageManager()).setSystemFeature(PackageManager.FEATURE_TOUCHSCREEN, true);
        host = new LinearLayout(activity.get()); activity.get().setContentView(host);
        c = new DiagnosticController(activity.get(), host);
    }

    @After public void teardown() { c.close(); activity.pause().stop().destroy(); }

    private Map<String, Object> start(String id) {
        Map<String, Object> b = DiagnosticJobTest.binding(id); b.put("diagnostic_id", id);
        assertEquals("RUNNING", c.command("START_CHALLENGE", b).get("state"));
        Shadows.shadowOf(Looper.getMainLooper()).idle(); return b;
    }

    @Test public void runtimeFeaturesAndPermissionDeniedAreNotPass() {
        assertTrue(c.capabilities().stream().anyMatch(e -> "microphone".equals(e.get("diagnostic_id")) && Boolean.TRUE.equals(e.get("available"))));
        Map<String, Object> b = start("microphone");
        assertEquals("RESTRICTED", c.command("FETCH_OBSERVATIONS", b).get("outcome"));
        assertEquals("PERMISSION_REQUIRED", c.command("FETCH_OBSERVATIONS", b).get("reason"));
    }

    @Test public void missingHardwareIsUnsupported() {
        Map<String, Object> b = start("sensor_63");
        assertEquals("UNSUPPORTED", c.command("FETCH_OBSERVATIONS", b).get("outcome"));
    }

    @Test public void unknownDiagnosticIdIsUnsupportedApi() {
        Map<String, Object> b = DiagnosticJobTest.binding("nonexistent_id");
        b.put("diagnostic_id", "nonexistent_id");
        c.command("START_CHALLENGE", b);
        Shadows.shadowOf(Looper.getMainLooper()).idle();
        assertEquals("UNSUPPORTED", c.command("FETCH_OBSERVATIONS", b).get("outcome"));
        assertEquals("API_UNSUPPORTED", c.command("FETCH_OBSERVATIONS", b).get("reason"));
    }

    @Test public void interactiveCancellationClosesOwnedResourceOnce() {
        Map<String, Object> b = start("touch"); AtomicInteger closes = new AtomicInteger();
        DiagnosticJob job = new DiagnosticJob(b, DiagnosticController.now());
        assertFalse(c.own(job, closes::incrementAndGet)); assertEquals(1, closes.get());
        assertEquals("CANCELLED", c.command("CANCEL_CHALLENGE", b).get("state"));
        assertEquals("INCONCLUSIVE", c.command("FETCH_OBSERVATIONS", b).get("outcome"));
    }

    @Test public void deadlineIsBoundedAndOldCallbacksCannotTouchNewWork() {
        Map<String, Object> b = start("touch");
        Shadows.shadowOf(Looper.getMainLooper()).idleFor(Duration.ofSeconds(60));
        assertEquals("EXPIRED", c.command("FETCH_OBSERVATIONS", b).get("state"));
        Map<String, Object> next = DiagnosticJobTest.binding("second"); next.put("diagnostic_id", "touch");
        assertNotNull(c.command("START_CHALLENGE", next)); Shadows.shadowOf(Looper.getMainLooper()).idle();
        assertNull(c.command("FETCH_OBSERVATIONS", b)); assertEquals("RUNNING", c.command("FETCH_OBSERVATIONS", next).get("state"));
    }

    @Test public void closeRevokesOutputAndQueuedWork() {
        Map<String, Object> b = DiagnosticJobTest.binding("a"); b.put("diagnostic_id", "touch");
        c.command("START_CHALLENGE", b); c.close(); Shadows.shadowOf(Looper.getMainLooper()).idle();
        assertNull(c.command("FETCH_OBSERVATIONS", b)); assertNull(c.command("START_CHALLENGE", b));
    }

    @Test public void batteryUnavailableIsNullAndOlderThermalApiIsNotCalled() {
        Map<String, Object> b = start("battery");
        Shadows.shadowOf(Looper.getMainLooper()).idleFor(Duration.ofSeconds(3));
        Map<String, Object> report = c.command("FETCH_OBSERVATIONS", b);
        assertEquals("INCONCLUSIVE", report.get("outcome"));
        List<?> metrics = (List<?>) report.get("metrics");
        boolean checkedCycle = false;
        for (Object m : metrics) {
            Map<?, ?> map = (Map<?, ?>) m;
            if ("cycle_count".equals(map.get("name"))) {
                checkedCycle = true;
                assertNull(map.get("value"));
            }
        }
        assertTrue(checkedCycle);

        Map<String, Object> system = start("system");
        Map<String, Object> sysReport = c.command("FETCH_OBSERVATIONS", system);
        assertEquals("INCONCLUSIVE", sysReport.get("outcome"));
        List<?> sysMetrics = (List<?>) sysReport.get("metrics");
        boolean checkedThermal = false;
        for (Object m : sysMetrics) {
            Map<?, ?> map = (Map<?, ?>) m;
            if ("thermal_status".equals(map.get("name"))) {
                checkedThermal = true;
                if (android.os.Build.VERSION.SDK_INT < 29) {
                    assertNull(map.get("value"));
                } else {
                    assertNotNull(map.get("value"));
                }
            }
        }
        assertTrue(checkedThermal);
    }

    @Test public void sensorTimeoutAndCancellationActuallyUnregisterListeners() {
        android.hardware.SensorManager manager = activity.get().getSystemService(android.hardware.SensorManager.class);
        org.robolectric.shadows.ShadowSensorManager sensors = Shadows.shadowOf(manager);
        sensors.addSensor(org.robolectric.shadows.ShadowSensor.newInstance(android.hardware.Sensor.TYPE_ACCELEROMETER));
        c.close(); c = new DiagnosticController(activity.get(), host);
        Map<String, Object> b = start("sensor_0"); assertEquals(1, sensors.getListeners().size());
        Shadows.shadowOf(Looper.getMainLooper()).idleFor(Duration.ofSeconds(3));
        assertEquals("NO_SAMPLES", c.command("FETCH_OBSERVATIONS", b).get("reason")); assertTrue(sensors.getListeners().isEmpty());
        Map<String, Object> next = DiagnosticJobTest.binding("next"); next.put("diagnostic_id", "sensor_0");
        c.command("START_CHALLENGE", next); Shadows.shadowOf(Looper.getMainLooper()).idle(); assertEquals(1, sensors.getListeners().size());
        c.command("CANCEL_CHALLENGE", next); assertTrue(sensors.getListeners().isEmpty());
    }

    @Test public void sensorRegistrationFailureIsNotHardwareFailure() {
        android.hardware.SensorManager manager = activity.get().getSystemService(android.hardware.SensorManager.class);
        org.robolectric.shadows.ShadowSensorManager sensors = Shadows.shadowOf(manager);
        sensors.addSensor(org.robolectric.shadows.ShadowSensor.newInstance(android.hardware.Sensor.TYPE_ACCELEROMETER));
        sensors.setForceListenersToFail(true); c.close(); c = new DiagnosticController(activity.get(), host);
        Map<String, Object> b = start("sensor_0");
        assertEquals("REGISTRATION_REJECTED", c.command("FETCH_OBSERVATIONS", b).get("reason")); assertTrue(sensors.getListeners().isEmpty());
    }

    @Test public void touchViewConsumesRealMotionEventsAndCompletion() {
        Map<String, Object> b = start("touch");
        DiagnosticUi.TouchView grid = c.ui.touchView;
        assertNotNull(grid);
        int w = 320;
        int h = 470;
        if (c.ui.touchDialog != null && c.ui.touchDialog.getWindow() != null) {
            android.view.View decor = c.ui.touchDialog.getWindow().getDecorView();
            if (decor != null && decor.getWidth() > 0 && decor.getHeight() > 0) {
                w = decor.getWidth();
                h = decor.getHeight();
            }
        }
        grid.layout(0, 0, w, h);
        for (int y = 0; y < 6; y++) for (int x = 0; x < 4; x++) {
            android.view.MotionEvent event = android.view.MotionEvent.obtain(0, 0, android.view.MotionEvent.ACTION_DOWN, (w / 8.0f) + (w / 4.0f) * x, (h / 12.0f) + (h / 6.0f) * y, 0);
            assertTrue(grid.dispatchTouchEvent(event)); event.recycle();
        }
        c.ui.finishTouch(c.getActiveJob());
        assertEquals("PASS", c.command("FETCH_OBSERVATIONS", b).get("outcome"));
        assertEquals("TOUCH_COVERED", c.command("FETCH_OBSERVATIONS", b).get("reason"));
    }

    @Test public void orientationResizeInvalidatesOldTouchCoverage() {
        Map<String, Object> b = start("touch");
        DiagnosticUi.TouchView grid = c.ui.touchView;
        assertNotNull(grid);
        grid.layout(0, 0, 400, 600);
        android.view.MotionEvent event = android.view.MotionEvent.obtain(0, 0, android.view.MotionEvent.ACTION_DOWN, 50, 50, 0);
        grid.dispatchTouchEvent(event); event.recycle();
        grid.layout(0, 0, 600, 400);
        c.ui.finishTouch(c.getActiveJob());
        assertEquals("INCONCLUSIVE", c.command("FETCH_OBSERVATIONS", b).get("outcome"));
        assertEquals("PARTIAL", c.command("FETCH_OBSERVATIONS", b).get("reason"));
    }

    @Test public void actualActivityPauseAndDestroyRevokeControllerAndScreenFlag() {
        try (ActivityController<ProbeActivity> probe = Robolectric.buildActivity(ProbeActivity.class).setup()) {
            DiagnosticController controller = new DiagnosticController(probe.get(), new LinearLayout(probe.get()));
            org.robolectric.util.ReflectionHelpers.setField(probe.get(), "diagnostics", controller);
            Map<String, Object> b = DiagnosticJobTest.binding("pause"); b.put("diagnostic_id", "touch");
            controller.command("START_CHALLENGE", b);
            probe.get().getWindow().addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            probe.pause();
            assertNull(controller.command("FETCH_OBSERVATIONS", b));
            assertEquals(0, probe.get().getWindow().getAttributes().flags & android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            probe.stop().destroy();
        }
    }

    @org.robolectric.annotation.Implements(android.media.AudioRecord.class)
    public static class FailingAudioRecord {
        static int released;
        @org.robolectric.annotation.Implementation protected void __constructor__(int source, int rate, int channels, int encoding, int buffer) { }
        @org.robolectric.annotation.Implementation protected static int getMinBufferSize(int rate, int channels, int encoding) { return 4096; }
        @org.robolectric.annotation.Implementation protected int getState() { return android.media.AudioRecord.STATE_UNINITIALIZED; }
        @org.robolectric.annotation.Implementation protected int getRecordingState() { return android.media.AudioRecord.RECORDSTATE_STOPPED; }
        @org.robolectric.annotation.Implementation protected void release() { released++; }
    }

    @Test @Config(shadows = FailingAudioRecord.class)
    public void microphoneInitializationFailureReleasesRecorder() {
        Shadows.shadowOf((android.app.Application) activity.get().getApplicationContext()).grantPermissions(android.Manifest.permission.RECORD_AUDIO);
        FailingAudioRecord.released = 0; Map<String, Object> b = start("microphone");
        assertEquals("ERROR", c.command("FETCH_OBSERVATIONS", b).get("outcome"));
        assertEquals("INITIALIZATION_ERROR", c.command("FETCH_OBSERVATIONS", b).get("reason"));
        assertEquals(1, FailingAudioRecord.released);
    }

    @Test public void storageWriteSyncAndReadbackProducesPassAndCleansFile() throws Exception {
        org.robolectric.shadows.ShadowStatFs.registerStats(activity.get().getCacheDir(), 10000, 10000, 10000);
        org.robolectric.shadows.ShadowStatFs.registerStats(activity.get().getCacheDir().getAbsolutePath(), 10000, 10000, 10000);
        Map<String, Object> b = start("storage");
        for (int i = 0; i < 30; i++) {
            Shadows.shadowOf(Looper.getMainLooper()).idle();
            Map<String, Object> report = c.command("FETCH_OBSERVATIONS", b);
            if (!"RUNNING".equals(report.get("state"))) break;
            Thread.sleep(50);
        }
        Map<String, Object> report = c.command("FETCH_OBSERVATIONS", b);
        assertEquals("COMPLETED", report.get("state"));
        assertEquals("PASS", report.get("outcome"));
        assertEquals("READBACK_MATCH", report.get("reason"));
        File[] tmp = activity.get().getCacheDir().listFiles((d, n) -> n.matches("vector-io-.*\\.tmp"));
        assertTrue(tmp == null || tmp.length == 0);
    }

    @Test public void storageCorruptedReadbackProducesFail() throws Exception {
        org.robolectric.shadows.ShadowStatFs.registerStats(activity.get().getCacheDir(), 10000, 10000, 10000);
        org.robolectric.shadows.ShadowStatFs.registerStats(activity.get().getCacheDir().getAbsolutePath(), 10000, 10000, 10000);
        try {
            StorageCollector.testIoHook = file -> {
                try (java.io.RandomAccessFile raf = new java.io.RandomAccessFile(file, "rw")) {
                    int b = raf.read();
                    raf.seek(0);
                    raf.write(b ^ 0xFF);
                }
            };
            Map<String, Object> b = start("storage");
            for (int i = 0; i < 30; i++) {
                Shadows.shadowOf(Looper.getMainLooper()).idle();
                Map<String, Object> report = c.command("FETCH_OBSERVATIONS", b);
                if (!"RUNNING".equals(report.get("state"))) break;
                Thread.sleep(50);
            }
            Map<String, Object> report = c.command("FETCH_OBSERVATIONS", b);
            assertEquals("COMPLETED", report.get("state"));
            assertEquals("FAIL", report.get("outcome"));
            assertEquals("READBACK_MISMATCH", report.get("reason"));
            List<?> metrics = (List<?>) report.get("metrics");
            boolean readbackChecked = false;
            for (Object m : metrics) {
                Map<?, ?> map = (Map<?, ?>) m;
                if ("readback_match".equals(map.get("name"))) {
                    readbackChecked = true;
                    assertEquals(0L, ((Number) map.get("value")).longValue());
                }
            }
            assertTrue(readbackChecked);
            File[] tmp = activity.get().getCacheDir().listFiles((d, n) -> n.matches("vector-io-.*\\.tmp"));
            assertTrue(tmp == null || tmp.length == 0);
        } finally {
            StorageCollector.testIoHook = null;
        }
    }

    @Test public void storageIoExceptionDuringReadReportsError() throws Exception {
        org.robolectric.shadows.ShadowStatFs.registerStats(activity.get().getCacheDir(), 10000, 10000, 10000);
        org.robolectric.shadows.ShadowStatFs.registerStats(activity.get().getCacheDir().getAbsolutePath(), 10000, 10000, 10000);
        try {
            StorageCollector.testIoHook = file -> {
                throw new java.io.IOException("Injected I/O fault before read");
            };
            Map<String, Object> b = start("storage");
            for (int i = 0; i < 30; i++) {
                Shadows.shadowOf(Looper.getMainLooper()).idle();
                Map<String, Object> report = c.command("FETCH_OBSERVATIONS", b);
                if (!"RUNNING".equals(report.get("state"))) break;
                Thread.sleep(50);
            }
            Map<String, Object> report = c.command("FETCH_OBSERVATIONS", b);
            assertEquals("COMPLETED", report.get("state"));
            assertEquals("ERROR", report.get("outcome"));
            assertEquals("READ_ERROR", report.get("reason"));
            File[] tmp = activity.get().getCacheDir().listFiles((d, n) -> n.matches("vector-io-.*\\.tmp"));
            assertTrue(tmp == null || tmp.length == 0);
        } finally {
            StorageCollector.testIoHook = null;
        }
    }

    @Test public void speakerAudioTrackLifecycleAndErrorHandling() {
        Shadows.shadowOf(activity.get().getPackageManager()).setSystemFeature(PackageManager.FEATURE_AUDIO_OUTPUT, true);
        c.close(); c = new DiagnosticController(activity.get(), host);
        Map<String, Object> b = start("speaker");
        Shadows.shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMillis(2000));
        Map<String, Object> report = c.command("FETCH_OBSERVATIONS", b);
        String outcome = (String) report.get("outcome");
        if ("ERROR".equals(outcome)) {
            assertEquals("INITIALIZATION_ERROR", report.get("reason"));
        } else {
            Button yes = null;
            for (int i = 0; i < host.getChildCount(); i++) {
                if (host.getChildAt(i) instanceof Button) {
                    Button btn = (Button) host.getChildAt(i);
                    if (activity.get().getString(R.string.diag_speaker_yes).contentEquals(btn.getText())) {
                        yes = btn; break;
                    }
                }
            }
            assertNotNull(yes);
            yes.performClick();
            assertEquals("USER_REPORTED", c.command("FETCH_OBSERVATIONS", b).get("reason"));
        }
    }

    @Test public void vibrationSchedulesEffectAndUserConfirmation() {
        android.os.Vibrator vibrator = activity.get().getSystemService(android.os.Vibrator.class);
        Shadows.shadowOf(vibrator).setHasVibrator(true);
        c.close(); c = new DiagnosticController(activity.get(), host);
        Map<String, Object> b = start("vibration");
        Shadows.shadowOf(Looper.getMainLooper()).idle();
        Button yes = null;
        for (int i = 0; i < host.getChildCount(); i++) {
            if (host.getChildAt(i) instanceof Button) {
                Button btn = (Button) host.getChildAt(i);
                if (activity.get().getString(R.string.diag_vibrate_yes).contentEquals(btn.getText())) {
                    yes = btn; break;
                }
            }
        }
        assertNotNull(yes);
        yes.performClick();
        Map<String, Object> report = c.command("FETCH_OBSERVATIONS", b);
        assertEquals("INCONCLUSIVE", report.get("outcome"));
        assertEquals("USER_REPORTED", report.get("reason"));
    }

    @Test public void pixelsCyclesColorsAndUserConfirmationPositive() {
        Map<String, Object> b = start("pixels");
        Shadows.shadowOf(Looper.getMainLooper()).idle();
        android.app.Dialog dialog = c.ui.colorsDialog;
        assertNotNull(dialog);
        assertTrue(dialog.isShowing());
        Button next = findButton(dialog.getWindow().getDecorView(), activity.get().getString(R.string.diag_next_color));
        assertNotNull(next);
        for (int i = 0; i < 5; i++) {
            next.performClick();
            Shadows.shadowOf(Looper.getMainLooper()).idle();
        }
        assertFalse(dialog.isShowing());
        Button yes = findButton(host, activity.get().getString(R.string.diag_pixels_yes));
        assertNotNull(yes);
        assertEquals(activity.get().getString(R.string.diag_pixels_yes), yes.getText());
        yes.performClick();
        Shadows.shadowOf(Looper.getMainLooper()).idle();
        Map<String, Object> report = c.command("FETCH_OBSERVATIONS", b);
        assertEquals("INCONCLUSIVE", report.get("outcome"));
        assertEquals("USER_REPORTED", report.get("reason"));
        List<?> metrics = (List<?>) report.get("metrics");
        boolean checkedReport = false;
        for (Object m : metrics) {
            Map<?, ?> map = (Map<?, ?>) m;
            if ("user_report".equals(map.get("name"))) {
                checkedReport = true;
                assertEquals(1L, ((Number) map.get("value")).longValue());
            }
        }
        assertTrue(checkedReport);
    }

    @Test public void pixelsCyclesColorsAndUserConfirmationNegative() {
        Map<String, Object> b = start("pixels");
        Shadows.shadowOf(Looper.getMainLooper()).idle();
        android.app.Dialog dialog = c.ui.colorsDialog;
        assertNotNull(dialog);
        Button next = findButton(dialog.getWindow().getDecorView(), activity.get().getString(R.string.diag_next_color));
        assertNotNull(next);
        for (int i = 0; i < 5; i++) {
            next.performClick();
            Shadows.shadowOf(Looper.getMainLooper()).idle();
        }
        assertFalse(dialog.isShowing());
        Button no = findButton(host, activity.get().getString(R.string.diag_pixels_no));
        assertNotNull(no);
        assertEquals(activity.get().getString(R.string.diag_pixels_no), no.getText());
        no.performClick();
        Shadows.shadowOf(Looper.getMainLooper()).idle();
        Map<String, Object> report = c.command("FETCH_OBSERVATIONS", b);
        assertEquals("INCONCLUSIVE", report.get("outcome"));
        assertEquals("USER_REPORTED", report.get("reason"));
        List<?> metrics = (List<?>) report.get("metrics");
        boolean checkedReport = false;
        for (Object m : metrics) {
            Map<?, ?> map = (Map<?, ?>) m;
            if ("user_report".equals(map.get("name"))) {
                checkedReport = true;
                assertEquals(0L, ((Number) map.get("value")).longValue());
            }
        }
        assertTrue(checkedReport);
    }

    @Test public void pixelsCancellationProducesCancelled() {
        Map<String, Object> b = start("pixels");
        Shadows.shadowOf(Looper.getMainLooper()).idle();
        android.app.Dialog dialog = c.ui.colorsDialog;
        assertNotNull(dialog);
        dialog.cancel();
        Shadows.shadowOf(Looper.getMainLooper()).idle();
        Map<String, Object> report = c.command("FETCH_OBSERVATIONS", b);
        assertEquals("INCONCLUSIVE", report.get("outcome"));
        assertEquals("CANCELLED", report.get("reason"));
    }

    private void configureCamera() {
        android.hardware.camera2.CameraManager manager = activity.get().getSystemService(android.hardware.camera2.CameraManager.class);
        org.robolectric.shadows.ShadowCameraManager shadowCameraManager = Shadows.shadowOf(manager);
        android.hardware.camera2.CameraCharacteristics chars = org.robolectric.shadows.ShadowCameraCharacteristics.newCameraCharacteristics();
        org.robolectric.shadows.ShadowCameraCharacteristics shadowChars = Shadows.shadowOf(chars);
        shadowChars.set(android.hardware.camera2.CameraCharacteristics.LENS_FACING, android.hardware.camera2.CameraCharacteristics.LENS_FACING_BACK);
        shadowChars.set(android.hardware.camera2.CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL, android.hardware.camera2.CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL_LIMITED);
        shadowChars.set(android.hardware.camera2.CameraCharacteristics.FLASH_INFO_AVAILABLE, true);
        shadowChars.set(android.hardware.camera2.CameraCharacteristics.CONTROL_AF_AVAILABLE_MODES, new int[]{android.hardware.camera2.CaptureRequest.CONTROL_AF_MODE_AUTO});
        shadowChars.set(android.hardware.camera2.CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP,
                org.robolectric.shadows.StreamConfigurationMapBuilder.newBuilder()
                        .addOutputSize(android.graphics.ImageFormat.YUV_420_888, new android.util.Size(640, 480))
                        .build());
        shadowCameraManager.addCamera("0", chars);
    }

    @Test public void cameraOpenFailureProducesInitializationError() throws Exception {
        Shadows.shadowOf((android.app.Application) activity.get().getApplicationContext()).grantPermissions(android.Manifest.permission.CAMERA);
        configureCamera();
        c.close(); c = new DiagnosticController(activity.get(), host);
        try {
            CameraCollector.setCameraOpenerForTest((mgr, cam, cb, handler) -> {
                handler.post(() -> cb.onError(null, android.hardware.camera2.CameraDevice.StateCallback.ERROR_CAMERA_DEVICE));
            });
            Map<String, Object> b = start("camera_0");
            Shadows.shadowOf(Looper.getMainLooper()).idle();
            Map<String, Object> report = c.command("FETCH_OBSERVATIONS", b);
            assertEquals("ERROR", report.get("outcome"));
            assertEquals("INITIALIZATION_ERROR", report.get("reason"));
        } finally {
            CameraCollector.setCameraOpenerForTest(null);
        }
    }

    @Test public void cameraDisabledPolicyProducesRestricted() throws Exception {
        Shadows.shadowOf((android.app.Application) activity.get().getApplicationContext()).grantPermissions(android.Manifest.permission.CAMERA);
        configureCamera();
        c.close(); c = new DiagnosticController(activity.get(), host);
        try {
            CameraCollector.setCameraOpenerForTest((mgr, cam, cb, handler) -> {
                handler.post(() -> cb.onError(null, android.hardware.camera2.CameraDevice.StateCallback.ERROR_CAMERA_DISABLED));
            });
            Map<String, Object> b = start("camera_0");
            Shadows.shadowOf(Looper.getMainLooper()).idle();
            Map<String, Object> report = c.command("FETCH_OBSERVATIONS", b);
            assertEquals("RESTRICTED", report.get("outcome"));
            assertEquals("CAMERA_DISABLED", report.get("reason"));
        } finally {
            CameraCollector.setCameraOpenerForTest(null);
        }
    }

    @Test public void cameraBusyProducesInconclusive() throws Exception {
        Shadows.shadowOf((android.app.Application) activity.get().getApplicationContext()).grantPermissions(android.Manifest.permission.CAMERA);
        configureCamera();
        c.close(); c = new DiagnosticController(activity.get(), host);
        try {
            CameraCollector.setCameraOpenerForTest((mgr, cam, cb, handler) -> {
                handler.post(() -> cb.onError(null, android.hardware.camera2.CameraDevice.StateCallback.ERROR_CAMERA_IN_USE));
            });
            Map<String, Object> b = start("camera_0");
            Shadows.shadowOf(Looper.getMainLooper()).idle();
            Map<String, Object> report = c.command("FETCH_OBSERVATIONS", b);
            assertEquals("INCONCLUSIVE", report.get("outcome"));
            assertEquals("CAMERA_BUSY", report.get("reason"));
        } finally {
            CameraCollector.setCameraOpenerForTest(null);
        }
    }

    @Test public void cameraTimeoutCancelsJob() throws Exception {
        Shadows.shadowOf((android.app.Application) activity.get().getApplicationContext()).grantPermissions(android.Manifest.permission.CAMERA);
        configureCamera();
        c.close(); c = new DiagnosticController(activity.get(), host);
        try {
            CameraCollector.setCameraOpenerForTest((mgr, cam, cb, handler) -> {
                // Stalls without callback
            });
            Map<String, Object> b = start("camera_0");
            Shadows.shadowOf(Looper.getMainLooper()).idleFor(Duration.ofSeconds(11));
            Map<String, Object> report = c.command("FETCH_OBSERVATIONS", b);
            assertEquals("INCONCLUSIVE", report.get("outcome"));
            assertEquals("TIMEOUT", report.get("reason"));
        } finally {
            CameraCollector.setCameraOpenerForTest(null);
        }
    }

    /** Touches the centre of every one of the 24 cells of the grid's current layout. */
    private static void touchAllCells(DiagnosticUi.TouchView grid) {
        for (int cell = 0; cell < 24; cell++) {
            android.view.MotionEvent event = android.view.MotionEvent.obtain(0, 0, android.view.MotionEvent.ACTION_DOWN,
                    grid.getWidth() * (2 * (cell % 4) + 1) / 8f, grid.getHeight() * (2 * (cell / 4) + 1) / 12f, 0);
            assertTrue(grid.dispatchTouchEvent(event)); event.recycle();
        }
    }

    private Map<String, Object> finishedTouch(Map<String, Object> b) {
        DiagnosticUi.TouchView grid = c.ui.touchView;
        assertEquals("all 24 cells covered, so only geometry can block PASS", 24, grid.touch.count);
        assertTrue(grid.touch.simultaneous >= 1 && grid.touch.layoutGeneration >= 1);
        c.ui.finishTouch(c.getActiveJob());
        return c.command("FETCH_OBSERVATIONS", b);
    }

    /** 180 px wide display: grid == window == display (100% coverage) but below the 200 px minimum. */
    @Test @Config(qualifiers = "w180dp-h640dp-mdpi")
    public void touchFullCoverageOfTooNarrowGridIsPartialSolelyForGeometry() {
        Map<String, Object> b = start("touch");
        DiagnosticUi.TouchView grid = c.ui.touchView;
        assertEquals(180, grid.getWidth());
        assertEquals(grid.getWidth(), grid.touch.displayWidth);
        assertEquals(Long.valueOf(100), grid.touch.testedDisplayAreaPercent());
        touchAllCells(grid);
        Map<String, Object> report = finishedTouch(b);
        assertEquals("INCONCLUSIVE", report.get("outcome"));
        assertEquals("PARTIAL", report.get("reason"));
    }

    /** A large but window-local grid covering 30% of the display never stands in for the touchscreen. */
    @Test @Config(qualifiers = "w411dp-h891dp-xxhdpi")
    public void touchFullCoverageOfSmallShareOfDisplayIsPartial() {
        Map<String, Object> b = start("touch");
        DiagnosticUi.TouchView grid = c.ui.touchView;
        grid.layout(0, 0, 1000, 1000);
        assertEquals(Long.valueOf(30), grid.touch.testedDisplayAreaPercent());
        touchAllCells(grid);
        Map<String, Object> report = finishedTouch(b);
        assertEquals("PARTIAL", report.get("reason"));
        assertEquals(1000, DiagnosticJobTest.metric(c.getActiveJob(), "tested_width"));
    }

    /** The app-window size is never fabricated from the grid size; unknown stays null and blocks PASS. */
    @Test @Config(qualifiers = "w411dp-h891dp-xxhdpi")
    public void touchWithUnknownAppWindowNeverPassesOnGridSizeAlone() {
        Map<String, Object> b = start("touch");
        android.app.Dialog dialog = c.ui.touchDialog;
        c.ui.touchDialog = null; // window size unavailable for the next layout
        try {
            DiagnosticUi.TouchView grid = c.ui.touchView;
            grid.layout(0, 0, 1233, 2600);
            assertEquals(0, grid.touch.windowWidth);
            touchAllCells(grid);
            Map<String, Object> report = finishedTouch(b);
            assertEquals("PARTIAL", report.get("reason"));
            assertNull(DiagnosticJobTest.metric(c.getActiveJob(), "window_width"));
            assertNull(DiagnosticJobTest.metric(c.getActiveJob(), "tested_window_area_percent"));
        } finally { c.ui.touchDialog = dialog; }
    }

    @Test @Config(qualifiers = "w411dp-h891dp-xxhdpi")
    public void touchFullCoverageOfFullDisplayGridIsPassWithCompleteGeometry() {
        Map<String, Object> b = start("touch");
        touchAllCells(c.ui.touchView);
        Map<String, Object> report = finishedTouch(b);
        assertEquals("PASS", report.get("outcome"));
        assertEquals("TOUCH_COVERED", report.get("reason"));
        DiagnosticJob job = c.getActiveJob();
        assertEquals(1233, DiagnosticJobTest.metric(job, "display_width"));
        assertEquals(2673, DiagnosticJobTest.metric(job, "display_height"));
        assertEquals(1233, DiagnosticJobTest.metric(job, "window_width"));
        assertEquals(100L, DiagnosticJobTest.metric(job, "tested_display_area_percent"));
        for (String legacy : new String[]{"coverage_percent", "tested_area_percent"}) {
            for (Object m : (List<?>) report.get("metrics")) assertNotEquals(legacy, ((Map<?, ?>) m).get("name"));
        }
    }

    @SuppressWarnings("unchecked")
    @Test public void challengeBudgetExhaustionRejects257thChallengeWithStatusError() throws Exception {
        java.time.Instant now = java.time.Instant.parse("2026-10-08T00:00:00Z");
        ControlProtocol protocol = new ControlProtocol(now, 0, 35, c);
        int[] seq = {0};
        java.util.function.BiFunction<String, Integer, com.google.gson.JsonObject> send = (op, n) -> {
            Map<String, Object> r = DiagnosticProtocolTest.request(op, seq[0], DiagnosticProtocolTest.challenge(n));
            if (r.get("binding") != null) ((Map<String, Object>) r.get("binding")).put("diagnostic_id", "display");
            try { return DiagnosticProtocolTest.json(protocol.respond(DiagnosticProtocolTest.wire(r), now, ++seq[0])); }
            catch (java.io.IOException error) { throw new AssertionError(error); }
        };
        assertEquals("OK", send.apply("HELLO", 0).get("status").getAsString());
        for (int i = 0; i < 256; i++) {
            assertEquals("Challenge " + i + " should succeed", "OK", send.apply("START_CHALLENGE", i).get("status").getAsString());
            Shadows.shadowOf(Looper.getMainLooper()).idle();
        }
        assertTrue(c.isExhausted());
        com.google.gson.JsonObject refused = send.apply("START_CHALLENGE", 256);
        assertEquals("257th START must be refused with ERROR", "ERROR", refused.get("status").getAsString());
        assertTrue(refused.get("diagnostic").isJsonNull());
        assertEquals("stale FETCH is merely unavailable", "UNAVAILABLE", send.apply("FETCH_OBSERVATIONS", 0).get("status").getAsString());
        assertEquals("stale CANCEL is merely unavailable", "UNAVAILABLE", send.apply("CANCEL_CHALLENGE", 7).get("status").getAsString());
        assertEquals("OK", send.apply("FETCH_OBSERVATIONS", 255).get("status").getAsString());
    }

    @Test public void connectivityReportsNamedFeatures() {
        Shadows.shadowOf(activity.get().getPackageManager()).setSystemFeature("android.hardware.wifi", true);
        Map<String, Object> b = start("connectivity");
        Shadows.shadowOf(Looper.getMainLooper()).idle();
        Map<String, Object> report = c.command("FETCH_OBSERVATIONS", b);
        assertEquals("INCONCLUSIVE", report.get("outcome"));
        assertEquals("CAPABILITY_ONLY", report.get("reason"));
        List<?> metrics = (List<?>) report.get("metrics");
        boolean foundWifi = false;
        for (Object m : metrics) {
            Map<?, ?> map = (Map<?, ?>) m;
            if ("feature_wifi".equals(map.get("name"))) {
                foundWifi = true;
                assertEquals(1L, ((Number) map.get("value")).longValue());
            }
        }
        assertTrue(foundWifi);
    }

    private static Map<String, Object> entry(DiagnosticRegistry registry, String id) {
        for (Map<String, Object> item : registry.snapshot()) if (id.equals(item.get("diagnostic_id"))) return item;
        throw new AssertionError(id + " not advertised");
    }

    @Test public void cameraCharacteristicsDiscoveredWithoutPermission() {
        assertEquals(PackageManager.PERMISSION_DENIED, activity.get().checkSelfPermission(android.Manifest.permission.CAMERA));
        configureCamera();
        Map<String, Object> camera = entry(new DiagnosticRegistry(activity.get()), "camera_0");
        assertEquals(Boolean.TRUE, camera.get("available"));
        assertEquals(android.hardware.camera2.CameraCharacteristics.LENS_FACING_BACK, camera.get("camera_facing"));
        assertEquals(android.hardware.camera2.CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL_LIMITED, camera.get("camera_level"));
        assertEquals(Boolean.TRUE, camera.get("flash_available"));
        assertEquals(Boolean.TRUE, camera.get("autofocus_available"));
    }

    @Test public void missingCameraIsAdvertisedUnavailableWithoutInventedMetadata() {
        Map<String, Object> camera = entry(new DiagnosticRegistry(activity.get()), "camera_0");
        assertEquals(Boolean.FALSE, camera.get("available"));
        for (String field : new String[]{"camera_facing", "camera_level", "flash_available", "autofocus_available"}) assertNull(camera.get(field));
    }

    @Test public void probeActivityAccuratePermissionStatesAndSettingsFlow() {
        activity.get().getSharedPreferences("probe_permissions", Activity.MODE_PRIVATE).edit().clear().commit();
        try (ActivityController<ProbeActivity> probe = Robolectric.buildActivity(ProbeActivity.class).setup()) {
            ProbeActivity act = probe.get();
            // 1. First launch: Not requested
            TextView camStatus = findText(act.getWindow().getDecorView(), "Camera: Not requested");
            assertNotNull("Expected Camera: Not requested on first launch", camStatus);
            Button grantBtn = findButton(act.getWindow().getDecorView(), "Grant Camera:");
            assertNotNull("Expected Grant button on first launch", grantBtn);
            Button settingsBtn = findButton(act.getWindow().getDecorView(), "Open Settings");
            assertNull("Open Settings should not be visible on first launch", settingsBtn);

            // 2. Click Grant button - triggers request and records in prefs
            grantBtn.performClick();
            Shadows.shadowOf(Looper.getMainLooper()).idle();

            // 3. User denies, shouldShowRequestPermissionRationale returns true
            Shadows.shadowOf(act.getPackageManager()).setShouldShowRequestPermissionRationale(android.Manifest.permission.CAMERA, true);
            probe.resume();
            TextView retryStatus = findText(act.getWindow().getDecorView(), "Camera: Denied (can request again)");
            assertNotNull("Expected Denied (can request again)", retryStatus);
            Button grantRetryBtn = findButton(act.getWindow().getDecorView(), "Grant Camera:");
            assertNotNull("Expected Grant button still available", grantRetryBtn);
            assertNull("Open Settings should still not be shown", findButton(act.getWindow().getDecorView(), "Open Settings"));

            // 4. Repeated denial with Don't ask again (rationale = false)
            Shadows.shadowOf(act.getPackageManager()).setShouldShowRequestPermissionRationale(android.Manifest.permission.CAMERA, false);
            probe.resume();
            TextView settingsStatus = findText(act.getWindow().getDecorView(), "Camera: Denied / Settings required");
            assertNotNull("Expected Denied / Settings required", settingsStatus);
            Button openSettingsBtn = findButton(act.getWindow().getDecorView(), "Open Settings");
            assertNotNull("Expected Open Settings button", openSettingsBtn);
            openSettingsBtn.performClick();
            Intent nextIntent = Shadows.shadowOf(act).getNextStartedActivity();
            assertNotNull(nextIntent);
            assertEquals(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, nextIntent.getAction());

            // 5. Grant permission
            Shadows.shadowOf((android.app.Application) act.getApplicationContext()).grantPermissions(android.Manifest.permission.CAMERA);
            probe.resume();
            TextView grantedStatus = findText(act.getWindow().getDecorView(), "Camera: Granted");
            assertNotNull("Expected Granted status", grantedStatus);
            assertNull("Grant button should disappear", findButton(act.getWindow().getDecorView(), "Grant Camera:"));
            assertNull("Settings button should disappear", findButton(act.getWindow().getDecorView(), "Open Settings"));
        }
    }

    @Test public void probeActivityConsentDisclosureStatementsPinned() {
        try (ActivityController<ProbeActivity> probe = Robolectric.buildActivity(ProbeActivity.class).setup()) {
            ProbeActivity act = probe.get();
            TextView purpose = findTextWithSubstring(act.getWindow().getDecorView(), "Sensitive tests require your on-screen interaction or runtime permissions");
            assertNotNull("Expected consent disclosure text", purpose);
            String text = purpose.getText().toString();
            assertTrue(text.contains("Camera frames and audio samples are processed locally and are never stored or transmitted"));
            assertTrue(text.contains("Only derived numeric results are sent to the computer: audio level (RMS and peak), camera frame size and brightness statistics (luma mean and variance)"));
            assertTrue(text.contains("Storage testing writes a temporary 64 KiB file and deletes it immediately; a failed deletion is reported"));
            assertTrue(text.contains("Leaving this screen, locking the phone or opening a permission dialog ends the session"));
        }
    }

    // ---- Camera: real Camera2 open/session/capture wiring (API 35); HAL delivery at the event boundary ----

    private static final long FRAME_TIME = 7_000_000_123L;

    private static java.nio.ByteBuffer lumaPlane() {
        byte[] y = new byte[640 * 480];
        for (int i = 0; i < y.length; i++) y[i] = (byte) (i % 251);
        return java.nio.ByteBuffer.wrap(y);
    }

    /** Starts camera_0 for real: permission, characteristics, ImageReader, open, session and capture. */
    private CameraCollector openCamera(Map<String, Object> binding) {
        Object resource = org.robolectric.util.ReflectionHelpers.getField(c, "resource");
        assertTrue("camera collector owns the resource", resource instanceof CameraCollector);
        CameraCollector camera = (CameraCollector) resource;
        assertNotNull("capture session configured", org.robolectric.util.ReflectionHelpers.getField(camera, "session"));
        assertEquals("RUNNING", c.command("FETCH_OBSERVATIONS", binding).get("state"));
        return camera;
    }

    private Map<String, Object> startCamera() {
        Shadows.shadowOf((android.app.Application) activity.get().getApplicationContext()).grantPermissions(android.Manifest.permission.CAMERA);
        configureCamera();
        c.close(); c = new DiagnosticController(activity.get(), host);
        return start("camera_0");
    }

    private static void assertCameraReleased(CameraCollector camera) {
        Object device = org.robolectric.util.ReflectionHelpers.getField(camera, "device");
        Object reader = org.robolectric.util.ReflectionHelpers.getField(camera, "reader");
        assertTrue((Boolean) org.robolectric.util.ReflectionHelpers.getField(camera, "closed"));
        assertTrue("camera device closed", (Boolean) org.robolectric.util.ReflectionHelpers.getField(org.robolectric.shadow.api.Shadow.extract(device), "closed"));
        assertFalse("image reader closed", ((java.util.concurrent.atomic.AtomicBoolean) org.robolectric.util.ReflectionHelpers.getField(
                org.robolectric.shadow.api.Shadow.extract(reader), "readerValid")).get());
    }

    @Test @Config(sdk = 35)
    public void cameraSuccessfulCaptureIsPassWithFrameEvidenceAndReleasesCamera() {
        Map<String, Object> b = startCamera();
        CameraCollector camera = openCamera(b);
        camera.onCaptureResult(FRAME_TIME, android.hardware.camera2.CaptureResult.CONTROL_AF_STATE_FOCUSED_LOCKED);
        assertEquals("RUNNING", c.command("FETCH_OBSERVATIONS", b).get("state"));
        camera.onFrame(640, 480, 460800, FRAME_TIME, lumaPlane());
        Map<String, Object> report = c.command("FETCH_OBSERVATIONS", b);
        assertEquals("PASS", report.get("outcome"));
        assertEquals("CAPTURE_MATCH", report.get("reason"));
        DiagnosticJob job = c.getActiveJob();
        assertEquals(1, DiagnosticJobTest.metric(job, "frame_metadata_match"));
        assertEquals(640, DiagnosticJobTest.metric(job, "frame_width"));
        assertEquals(460800L, DiagnosticJobTest.metric(job, "frame_bytes"));
        assertEquals(124.96, ((Number) DiagnosticJobTest.metric(job, "luma_mean")).doubleValue(), 0);
        assertEquals(5250.54, ((Number) DiagnosticJobTest.metric(job, "luma_variance")).doubleValue(), 0);
        assertCameraReleased(camera);
    }

    @Test @Config(sdk = 35)
    public void cameraTimestampMismatchIsInconclusiveNeverPass() {
        Map<String, Object> b = startCamera();
        CameraCollector camera = openCamera(b);
        camera.onFrame(640, 480, 460800, FRAME_TIME + 1, lumaPlane());
        camera.onCaptureResult(FRAME_TIME, 2);
        Map<String, Object> report = c.command("FETCH_OBSERVATIONS", b);
        assertEquals("INCONCLUSIVE", report.get("outcome"));
        assertEquals("METADATA_MISMATCH", report.get("reason"));
        assertEquals(0, DiagnosticJobTest.metric(c.getActiveJob(), "frame_metadata_match"));
        assertCameraReleased(camera);
    }

    @Test @Config(sdk = 35)
    public void cameraFrameWithoutDimensionsBytesOrLumaIsInvalid() {
        Object[][] frames = {
            {0, 480, 460800L, lumaPlane()}, {640, 0, 460800L, lumaPlane()}, {640, 480, 0L, lumaPlane()},
            {640, 480, 460800L, java.nio.ByteBuffer.allocate(0)}, {640, 480, 460800L, null}};
        Map<String, Object> b = startCamera();
        for (int i = 0; i < frames.length; i++) {
            if (i > 0) {
                b = DiagnosticJobTest.binding("frame" + i); b.put("diagnostic_id", "camera_0");
                assertEquals("RUNNING", c.command("START_CHALLENGE", b).get("state"));
                Shadows.shadowOf(Looper.getMainLooper()).idle();
            }
            CameraCollector camera = openCamera(b);
            camera.onCaptureResult(FRAME_TIME, 2);
            camera.onFrame((Integer) frames[i][0], (Integer) frames[i][1], (Long) frames[i][2], FRAME_TIME, (java.nio.ByteBuffer) frames[i][3]);
            Map<String, Object> report = c.command("FETCH_OBSERVATIONS", b);
            assertEquals("frame " + i, "ERROR", report.get("outcome"));
            assertEquals("frame " + i, "INVALID_FRAME", report.get("reason"));
            assertCameraReleased(camera);
        }
    }

    @Test @Config(sdk = 35)
    public void cameraMissingTimestampOrFailedCaptureIsNotPass() {
        Map<String, Object> b = startCamera();
        openCamera(b).onCaptureResult(null, null);
        assertEquals("METADATA_UNAVAILABLE", c.command("FETCH_OBSERVATIONS", b).get("reason"));
        Map<String, Object> next = DiagnosticJobTest.binding("failed"); next.put("diagnostic_id", "camera_0");
        c.command("START_CHALLENGE", next); Shadows.shadowOf(Looper.getMainLooper()).idle();
        CameraCollector camera = openCamera(next);
        camera.onCaptureFailed();
        Map<String, Object> report = c.command("FETCH_OBSERVATIONS", next);
        assertEquals("ERROR", report.get("outcome")); assertEquals("CAPTURE_ERROR", report.get("reason"));
        assertCameraReleased(camera);
    }

    @Test @Config(sdk = 35)
    public void cameraStallTimesOutAndReleasesCamera() {
        Map<String, Object> b = startCamera();
        CameraCollector camera = openCamera(b);
        Shadows.shadowOf(Looper.getMainLooper()).idleFor(Duration.ofSeconds(10));
        Map<String, Object> report = c.command("FETCH_OBSERVATIONS", b);
        assertEquals("EXPIRED", report.get("state")); assertEquals("TIMEOUT", report.get("reason"));
        assertCameraReleased(camera);
        camera.onCaptureResult(FRAME_TIME, 2);
        camera.onFrame(640, 480, 460800, FRAME_TIME, lumaPlane());
        assertEquals("late HAL callbacks cannot rewrite a terminal result", report, c.command("FETCH_OBSERVATIONS", b));
    }

    @Test @Config(sdk = 35)
    public void desktopCancelReportsStoppingUntilMainReleasesCamera() throws Exception {
        Map<String, Object> b = startCamera();
        CameraCollector camera = openCamera(b);
        java.util.concurrent.ExecutorService socket = java.util.concurrent.Executors.newSingleThreadExecutor();
        try {
            Map<String, Object> stopping = socket.submit(() -> c.command("CANCEL_CHALLENGE", b)).get();
            assertEquals("RUNNING", stopping.get("state")); assertEquals("STOPPING", stopping.get("reason"));
            assertFalse("camera not yet released", (Boolean) org.robolectric.util.ReflectionHelpers.getField(camera, "closed"));
            assertNull("no new START while stopping", socket.submit(() -> {
                Map<String, Object> other = DiagnosticJobTest.binding("other"); other.put("diagnostic_id", "camera_0");
                return c.command("START_CHALLENGE", other);
            }).get());
        } finally { socket.shutdownNow(); }
        camera.onCaptureResult(FRAME_TIME, 2);
        camera.onFrame(640, 480, 460800, FRAME_TIME, lumaPlane());
        assertEquals("STOPPING", c.command("FETCH_OBSERVATIONS", b).get("reason"));
        Shadows.shadowOf(Looper.getMainLooper()).idle();
        Map<String, Object> report = c.command("FETCH_OBSERVATIONS", b);
        assertEquals("CANCELLED", report.get("state")); assertEquals("CANCELLED", report.get("reason"));
        assertCameraReleased(camera);
    }

    @Test public void lumaStatisticsAreExactAndHonourBufferPosition() {
        double[] flat = CameraCollector.lumaStatistics(java.nio.ByteBuffer.wrap(new byte[]{(byte) 200, (byte) 200, (byte) 200}));
        assertEquals(200.0, flat[0], 0); assertEquals(0.0, flat[1], 0);
        java.nio.ByteBuffer split = java.nio.ByteBuffer.wrap(new byte[]{99, 0, (byte) 255});
        split.position(1);
        double[] stats = CameraCollector.lumaStatistics(split);
        assertEquals(127.5, stats[0], 0); assertEquals(16256.25, stats[1], 0);
    }

    // ---- TG-05 / TG-11: cancellation and cleanup failures are reported, never dropped ----

    @Test public void socketThreadCancelIsStoppingUntilMainRunsCleanup() throws Exception {
        Map<String, Object> b = start("touch");
        java.util.concurrent.ExecutorService socket = java.util.concurrent.Executors.newSingleThreadExecutor();
        try {
            assertEquals("STOPPING", socket.submit(() -> c.command("CANCEL_CHALLENGE", b)).get().get("reason"));
        } finally { socket.shutdownNow(); }
        assertNotNull("grid still shown until main releases it", c.ui.touchDialog);
        Shadows.shadowOf(Looper.getMainLooper()).idle();
        assertEquals("CANCELLED", c.command("FETCH_OBSERVATIONS", b).get("state"));
        assertNull(c.ui.touchDialog);
    }

    @Test public void cleanupFailureDuringCancelIsCleanupError() throws Exception {
        for (boolean socketThread : new boolean[]{false, true}) {
            Map<String, Object> b = DiagnosticJobTest.binding("cleanup" + socketThread); b.put("diagnostic_id", "touch");
            c.command("START_CHALLENGE", b); Shadows.shadowOf(Looper.getMainLooper()).idle();
            assertTrue(c.own(c.getActiveJob(), () -> { throw new java.io.IOException("stuck resource"); }));
            if (socketThread) {
                java.util.concurrent.ExecutorService socket = java.util.concurrent.Executors.newSingleThreadExecutor();
                try { socket.submit(() -> c.command("CANCEL_CHALLENGE", b)).get(); } finally { socket.shutdownNow(); }
                Shadows.shadowOf(Looper.getMainLooper()).idle();
            } else {
                c.command("CANCEL_CHALLENGE", b);
            }
            Map<String, Object> report = c.command("FETCH_OBSERVATIONS", b);
            assertEquals("CANCELLED", report.get("state"));
            assertEquals("ERROR", report.get("outcome"));
            assertEquals("CLEANUP_ERROR", report.get("reason"));
        }
    }

    @Test public void timeoutCleanupFailureIsExpiredCleanupError() {
        Map<String, Object> b = start("touch");
        assertTrue(c.own(c.getActiveJob(), () -> { throw new java.io.IOException("stuck resource"); }));
        Shadows.shadowOf(Looper.getMainLooper()).idleFor(Duration.ofSeconds(60));
        Map<String, Object> report = c.command("FETCH_OBSERVATIONS", b);
        assertEquals("EXPIRED", report.get("state")); assertEquals("CLEANUP_ERROR", report.get("reason"));
    }

    @Test public void cancelArrivingDuringFinishCleanupKeepsTheRealCleanupResult() {
        Map<String, Object> b = start("touch");
        DiagnosticJob job = c.getActiveJob();
        assertTrue(c.own(job, () -> {
            Thread socket = new Thread(() -> c.command("CANCEL_CHALLENGE", b));
            socket.start(); socket.join();
            throw new java.io.IOException("stuck resource");
        }));
        c.finish(job, "PASS", "TOUCH_COVERED");
        Shadows.shadowOf(Looper.getMainLooper()).idle();
        Map<String, Object> report = c.command("FETCH_OBSERVATIONS", b);
        assertEquals("CANCELLED", report.get("state"));
        assertEquals("CLEANUP_ERROR", report.get("reason"));
    }

    private Map<String, Object> runStorage() throws Exception {
        org.robolectric.shadows.ShadowStatFs.registerStats(activity.get().getCacheDir(), 10000, 10000, 10000);
        org.robolectric.shadows.ShadowStatFs.registerStats(activity.get().getCacheDir().getAbsolutePath(), 10000, 10000, 10000);
        Map<String, Object> b = start("storage");
        for (int i = 0; i < 100; i++) {
            Shadows.shadowOf(Looper.getMainLooper()).idle();
            if (!"RUNNING".equals(c.command("FETCH_OBSERVATIONS", b).get("state"))) break;
            Thread.sleep(20);
        }
        return c.command("FETCH_OBSERVATIONS", b);
    }

    @Test public void storageUndeletableTemporaryFileIsReportedAsCleanupError() throws Exception {
        File[] leftover = new File[1];
        try {
            StorageCollector.testIoHook = file -> {
                assertTrue(file.delete() && file.mkdir() && new File(file, "pinned").createNewFile());
                leftover[0] = file;
            };
            Map<String, Object> report = runStorage();
            assertEquals("COMPLETED", report.get("state"));
            assertEquals("ERROR", report.get("outcome"));
            assertEquals("CLEANUP_ERROR", report.get("reason"));
            assertTrue(leftover[0].isDirectory());
        } finally {
            StorageCollector.testIoHook = null;
            if (leftover[0] != null) { new File(leftover[0], "pinned").delete(); leftover[0].delete(); }
        }
    }

    @Test public void storageWriteFaultIsWriteErrorAndCleansFile() throws Exception {
        try {
            StorageCollector.testIoHook = new StorageCollector.StorageIoHook() {
                @Override public void onBeforeWrite(File file) throws java.io.IOException { throw new java.io.IOException("injected"); }
                @Override public void onBeforeRead(File file) { }
            };
            Map<String, Object> report = runStorage();
            assertEquals("ERROR", report.get("outcome")); assertEquals("WRITE_ERROR", report.get("reason"));
            File[] tmp = activity.get().getCacheDir().listFiles((d, n) -> n.matches("vector-io-.*\\.tmp"));
            assertTrue(tmp == null || tmp.length == 0);
        } finally { StorageCollector.testIoHook = null; }
    }

    // ---- TG-07: sensor samples outside the desktop numeric contract never invalidate a report ----

    @Test public void outOfContractSensorSamplesAreRejectedAndCounted() {
        android.hardware.SensorManager manager = activity.get().getSystemService(android.hardware.SensorManager.class);
        org.robolectric.shadows.ShadowSensorManager sensors = Shadows.shadowOf(manager);
        sensors.addSensor(org.robolectric.shadows.ShadowSensor.newInstance(android.hardware.Sensor.TYPE_ACCELEROMETER));
        c.close(); c = new DiagnosticController(activity.get(), host);
        Map<String, Object> b = start("sensor_0");
        android.hardware.Sensor accelerometer = manager.getDefaultSensor(android.hardware.Sensor.TYPE_ACCELEROMETER);
        for (float x : new float[]{1e20f, Float.MAX_VALUE, Float.NaN, 0.5f}) {
            android.hardware.SensorEvent event = org.robolectric.shadows.ShadowSensorManager.createSensorEvent(3);
            event.values[0] = x; event.values[1] = 1f; event.values[2] = 9.8f;
            sensors.sendSensorEventToListeners(event, accelerometer);
        }
        Shadows.shadowOf(Looper.getMainLooper()).idleFor(Duration.ofSeconds(3));
        Map<String, Object> report = c.command("FETCH_OBSERVATIONS", b);
        assertEquals("SAMPLES_OBSERVED", report.get("reason"));
        DiagnosticJob job = c.getActiveJob();
        assertEquals(1, DiagnosticJobTest.metric(job, "sample_count"));
        assertEquals(3, DiagnosticJobTest.metric(job, "rejected_samples"));
        assertEquals(0.5, ((Number) DiagnosticJobTest.metric(job, "axis0_max")).doubleValue(), 1e-6);
    }

    // ---- TG-09: microphone asks about the measured level; uniform user_report polarity ----

    @Test public void microphoneShowsMeasuredLevelAndUsesMatchingLabels() {
        org.robolectric.shadows.ShadowAudioRecord.setSource(new org.robolectric.shadows.ShadowAudioRecord.AudioRecordSource() {
            @Override public int readInShortArray(short[] data, int offset, int size, boolean blocking) {
                for (int i = 0; i < size; i++) data[offset + i] = (short) (20000 * Math.sin(i / 8.0));
                return size;
            }
        });
        try {
            Shadows.shadowOf((android.app.Application) activity.get().getApplicationContext()).grantPermissions(android.Manifest.permission.RECORD_AUDIO);
            Map<String, Object> b = start("microphone");
            assertEquals(activity.get().getString(R.string.diag_mic_level, 60), c.ui.status.getText().toString());
            Shadows.shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMillis(3100));
            assertEquals(activity.get().getString(R.string.diag_confirmation_mic), c.ui.status.getText().toString());
            assertNull("generic labels are not used for the microphone", findButton(host, activity.get().getString(R.string.diag_yes)));
            assertNotNull(findButton(host, activity.get().getString(R.string.diag_mic_yes)));
            findButton(host, activity.get().getString(R.string.diag_mic_no)).performClick();
            Map<String, Object> report = c.command("FETCH_OBSERVATIONS", b);
            assertEquals("USER_REPORTED", report.get("reason"));
            assertEquals(0, DiagnosticJobTest.metric(c.getActiveJob(), "user_report"));
        } finally { org.robolectric.shadows.ShadowAudioRecord.clearSource(); }
    }

    @Test public void microphoneWithoutSamplesReportsNoLevelInsteadOfZero() {
        org.robolectric.shadows.ShadowAudioRecord.setSource(new org.robolectric.shadows.ShadowAudioRecord.AudioRecordSource() {
            @Override public int readInShortArray(short[] data, int offset, int size, boolean blocking) { return 0; }
        });
        try {
            Shadows.shadowOf((android.app.Application) activity.get().getApplicationContext()).grantPermissions(android.Manifest.permission.RECORD_AUDIO);
            start("microphone");
            Shadows.shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMillis(3100));
            DiagnosticJob job = c.getActiveJob();
            assertEquals(0L, DiagnosticJobTest.metric(job, "audio_samples"));
            assertNull(DiagnosticJobTest.metric(job, "audio_peak"));
            assertNull(DiagnosticJobTest.metric(job, "audio_rms"));
        } finally { org.robolectric.shadows.ShadowAudioRecord.clearSource(); }
    }

    @Test public void confirmationLabelsAreDiagnosticSpecific() {
        int[][] labels = {
            {R.string.diag_speaker_yes, R.string.diag_speaker_no}, {R.string.diag_mic_yes, R.string.diag_mic_no},
            {R.string.diag_vibrate_yes, R.string.diag_vibrate_no}, {R.string.diag_pixels_yes, R.string.diag_pixels_no}};
        java.util.Set<String> seen = new java.util.HashSet<>();
        for (int[] pair : labels) for (int label : pair) assertTrue(seen.add(activity.get().getString(label)));
        assertFalse(seen.contains(activity.get().getString(R.string.diag_yes)));
    }

    // ---- TG-10: in-session Settings recovery only after a requested, permanently denied permission ----

    private boolean settingsOffered() {
        return findButton(host, activity.get().getString(R.string.diag_settings_open)) != null;
    }

    @Test public void inSessionSettingsRecoveryNeedsAPriorRequestAndNoRationale() {
        activity.get().getSharedPreferences("probe_permissions", Activity.MODE_PRIVATE).edit().clear().commit();
        Shadows.shadowOf(activity.get().getPackageManager()).setShouldShowRequestPermissionRationale(android.Manifest.permission.RECORD_AUDIO, false);
        start("microphone");
        assertNotNull(findButton(host, activity.get().getString(R.string.diag_permission)));
        assertFalse("never requested: rationale is false but Settings is not the recovery", settingsOffered());
        findButton(host, activity.get().getString(R.string.diag_permission)).performClick();
        assertTrue(PermissionHistory.requested(activity.get(), android.Manifest.permission.RECORD_AUDIO));
        Map<String, Object> again = DiagnosticJobTest.binding("again"); again.put("diagnostic_id", "microphone");
        c.command("START_CHALLENGE", again); Shadows.shadowOf(Looper.getMainLooper()).idle();
        assertTrue("requested and denied without rationale: Settings offered", settingsOffered());
        Shadows.shadowOf(activity.get().getPackageManager()).setShouldShowRequestPermissionRationale(android.Manifest.permission.RECORD_AUDIO, true);
        Map<String, Object> retry = DiagnosticJobTest.binding("retry"); retry.put("diagnostic_id", "microphone");
        c.command("START_CHALLENGE", retry); Shadows.shadowOf(Looper.getMainLooper()).idle();
        assertFalse("rationale available: request again instead of Settings", settingsOffered());
    }

    private static Button findButton(android.view.View root, String text) {
        if (root instanceof Button) {
            Button b = (Button) root;
            if (text.contentEquals(b.getText())) return b;
        }
        if (root instanceof android.view.ViewGroup) {
            android.view.ViewGroup group = (android.view.ViewGroup) root;
            for (int i = 0; i < group.getChildCount(); i++) {
                Button found = findButton(group.getChildAt(i), text);
                if (found != null) return found;
            }
        }
        return null;
    }

    private static TextView findText(android.view.View root, String text) {
        if (root instanceof TextView) {
            TextView tv = (TextView) root;
            if (text.contentEquals(tv.getText())) return tv;
        }
        if (root instanceof android.view.ViewGroup) {
            android.view.ViewGroup group = (android.view.ViewGroup) root;
            for (int i = 0; i < group.getChildCount(); i++) {
                TextView found = findText(group.getChildAt(i), text);
                if (found != null) return found;
            }
        }
        return null;
    }

    private static TextView findTextWithSubstring(android.view.View root, String substring) {
        if (root instanceof TextView) {
            TextView tv = (TextView) root;
            if (tv.getText() != null && tv.getText().toString().contains(substring)) return tv;
        }
        if (root instanceof android.view.ViewGroup) {
            android.view.ViewGroup group = (android.view.ViewGroup) root;
            for (int i = 0; i < group.getChildCount(); i++) {
                TextView found = findTextWithSubstring(group.getChildAt(i), substring);
                if (found != null) return found;
            }
        }
        return null;
    }
}
