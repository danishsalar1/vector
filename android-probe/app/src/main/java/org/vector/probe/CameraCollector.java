package org.vector.probe;

import android.Manifest;
import android.content.pm.PackageManager;
import android.graphics.ImageFormat;
import android.hardware.camera2.*;
import android.hardware.camera2.params.StreamConfigurationMap;
import android.media.Image;
import android.media.ImageReader;
import android.util.Size;
import java.nio.ByteBuffer;
import java.util.Collections;

/**
 * One ephemeral YUV frame; only dimensions, luma statistics, and matched capture metadata escape.
 * The Camera2 callbacks only translate HAL objects into {@link #onFrame}, {@link #onCaptureResult}
 * and {@link #onCaptureFailed}, which hold every decision and are exercised directly by tests.
 */
final class CameraCollector implements AutoCloseable {
    private final DiagnosticController c;
    private final DiagnosticJob job;
    private CameraDevice device;
    private CameraCaptureSession session;
    private ImageReader reader;
    private boolean frameSeen;
    private boolean captureSeen;
    private long imageTime;
    private long captureTime;
    private boolean closed;
    private CameraCollector(DiagnosticController c, DiagnosticJob job) { this.c = c; this.job = job; }
    private static CameraOpener testOpener;
    interface CameraOpener {
        void openCamera(CameraManager manager, String camera, CameraDevice.StateCallback callback, android.os.Handler handler) throws CameraAccessException;
    }
    static void setCameraOpenerForTest(CameraOpener opener) { testOpener = opener; }

    static void start(DiagnosticController c, DiagnosticJob job, String camera) throws CameraAccessException {
        CameraCollector collector = new CameraCollector(c, job); if (!c.own(job, collector)) return;
        try { collector.open(camera); }
        catch (CameraAccessException error) {
            int reason = error.getReason();
            if (reason == CameraAccessException.CAMERA_DISABLED) {
                c.finish(job, "RESTRICTED", "CAMERA_DISABLED");
            } else if (reason == CameraAccessException.CAMERA_DISCONNECTED) {
                c.finish(job, "INCONCLUSIVE", "CAMERA_DISCONNECTED");
            } else if (reason == CameraAccessException.CAMERA_IN_USE || reason == CameraAccessException.MAX_CAMERAS_IN_USE) {
                c.finish(job, "INCONCLUSIVE", "CAMERA_BUSY");
            } else {
                c.finish(job, "ERROR", "INITIALIZATION_ERROR");
            }
        }
    }
    private void open(String camera) throws CameraAccessException {
        if (c.activity.checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            c.finish(job, "RESTRICTED", "PERMISSION_REQUIRED");
            return;
        }
        CameraManager manager = c.activity.getSystemService(CameraManager.class);
        if (manager == null) { c.finish(job, "UNSUPPORTED", "HARDWARE_ABSENT"); return; }
        CameraCharacteristics info = manager.getCameraCharacteristics(camera);
        job.metric("camera_facing", info.get(CameraCharacteristics.LENS_FACING), "enum");
        job.metric("camera_level", info.get(CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL), "enum");
        Boolean flash = info.get(CameraCharacteristics.FLASH_INFO_AVAILABLE);
        job.metric("flash_available", flash == null ? null : flash ? 1 : 0, "boolean");
        int[] modes = info.get(CameraCharacteristics.CONTROL_AF_AVAILABLE_MODES);
        boolean autofocus = false; if (modes != null) for (int mode : modes) if (mode == CaptureRequest.CONTROL_AF_MODE_AUTO) autofocus = true;
        job.metric("autofocus_available", modes == null ? null : autofocus ? 1 : 0, "boolean");
        StreamConfigurationMap configurations = info.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
        Size[] sizes = configurations == null ? null : configurations.getOutputSizes(ImageFormat.YUV_420_888);
        Size chosen = null;
        if (sizes != null) for (Size size : sizes) if (size.getWidth() > 0 && size.getHeight() > 0
                && (long) size.getWidth() * size.getHeight() <= 1920 * 1080
                && (chosen == null || (long) size.getWidth() * size.getHeight() < (long) chosen.getWidth() * chosen.getHeight())) chosen = size;
        if (chosen == null) { c.finish(job, "UNSUPPORTED", "CAPTURE_FORMAT_UNSUPPORTED"); return; }
        reader = ImageReader.newInstance(chosen.getWidth(), chosen.getHeight(), ImageFormat.YUV_420_888, 2);
        reader.setOnImageAvailableListener(source -> {
            if (closed || !c.current(job)) return;
            try (Image image = source.acquireLatestImage()) {
                if (image == null) return;
                Image.Plane[] planes = image.getPlanes();
                long bytes = 0;
                ByteBuffer luma = null;
                for (int i = 0; planes != null && i < planes.length; i++) {
                    ByteBuffer buffer = planes[i].getBuffer();
                    if (buffer == null) continue;
                    bytes += buffer.remaining();
                    if (i == 0) luma = buffer;
                }
                onFrame(image.getWidth(), image.getHeight(), bytes, image.getTimestamp(), luma);
            } catch (IllegalStateException error) { c.finish(job, "ERROR", "INVALID_FRAME"); }
        }, c.main);
        CameraDevice.StateCallback callback = new CameraDevice.StateCallback() {
            @Override public void onOpened(CameraDevice cameraDevice) {
                if (closed || !c.current(job)) { cameraDevice.close(); return; }
                device = cameraDevice;
                try {
                    device.createCaptureSession(Collections.singletonList(reader.getSurface()), new CameraCaptureSession.StateCallback() {
                        @Override public void onConfigured(CameraCaptureSession configured) {
                            if (closed || !c.current(job)) { configured.close(); return; }
                            session = configured;
                            try {
                                CaptureRequest.Builder request = device.createCaptureRequest(CameraDevice.TEMPLATE_STILL_CAPTURE);
                                request.addTarget(reader.getSurface());
                                session.capture(request.build(), new CameraCaptureSession.CaptureCallback() {
                                    @Override public void onCaptureCompleted(CameraCaptureSession s, CaptureRequest r, TotalCaptureResult result) {
                                        onCaptureResult(result.get(CaptureResult.SENSOR_TIMESTAMP), result.get(CaptureResult.CONTROL_AF_STATE));
                                    }
                                    @Override public void onCaptureFailed(CameraCaptureSession s, CaptureRequest r, CaptureFailure failure) { CameraCollector.this.onCaptureFailed(); }
                                }, c.main);
                            } catch (CameraAccessException | IllegalStateException error) { c.finish(job, "ERROR", "CAPTURE_ERROR"); }
                            catch (SecurityException error) { c.finish(job, "RESTRICTED", "PERMISSION_REQUIRED"); }
                        }
                        @Override public void onConfigureFailed(CameraCaptureSession s) { s.close(); if (c.current(job)) c.finish(job, "ERROR", "INITIALIZATION_ERROR"); }
                    }, c.main);
                } catch (CameraAccessException | IllegalStateException error) { c.finish(job, "ERROR", "INITIALIZATION_ERROR"); }
            }
            @Override public void onDisconnected(CameraDevice d) { if (d != null) d.close(); if (c.current(job)) c.finish(job, "INCONCLUSIVE", "CAMERA_DISCONNECTED"); }
            @Override public void onError(CameraDevice d, int error) {
                if (d != null) d.close();
                if (c.current(job)) {
                    if (error == ERROR_CAMERA_DISABLED) {
                        c.finish(job, "RESTRICTED", "CAMERA_DISABLED");
                    } else if (error == ERROR_CAMERA_IN_USE || error == ERROR_MAX_CAMERAS_IN_USE) {
                        c.finish(job, "INCONCLUSIVE", "CAMERA_BUSY");
                    } else {
                        c.finish(job, "ERROR", "INITIALIZATION_ERROR");
                    }
                }
            }
        };
        if (testOpener != null) {
            testOpener.openCamera(manager, camera, callback, c.main);
        } else {
            manager.openCamera(camera, callback, c.main);
        }
        c.main.postDelayed(() -> { if (c.current(job)) c.cancel(job, true); }, 10000);
    }

    /** HAL frame boundary: a valid frame has dimensions, bytes and a non-empty luma (Y) plane. */
    void onFrame(int width, int height, long bytes, long timestamp, ByteBuffer luma) {
        if (closed || !c.current(job)) return;
        if (width <= 0 || height <= 0 || bytes <= 0 || luma == null || !luma.hasRemaining()) {
            c.finish(job, "ERROR", "INVALID_FRAME");
            return;
        }
        double[] statistics = lumaStatistics(luma);
        job.metric("frame_width", width, "pixels"); job.metric("frame_height", height, "pixels");
        job.metric("frame_bytes", bytes, "bytes");
        job.metric("luma_mean", statistics[0], "unitless");
        job.metric("luma_variance", statistics[1], "unitless");
        imageTime = timestamp; frameSeen = true;
        complete();
    }

    /** HAL capture-result boundary; a result without a sensor timestamp cannot be matched. */
    void onCaptureResult(Long sensorTimestamp, Integer afState) {
        if (closed || !c.current(job)) return;
        if (sensorTimestamp == null) { c.finish(job, "INCONCLUSIVE", "METADATA_UNAVAILABLE"); return; }
        job.metric("capture_completed", 1, "boolean");
        job.metric("af_state", afState, "enum");
        captureTime = sensorTimestamp; captureSeen = true;
        complete();
    }

    void onCaptureFailed() { if (!closed && c.current(job)) c.finish(job, "ERROR", "CAPTURE_ERROR"); }

    /** Mean and variance of up to 4096 evenly spaced luma bytes, rounded to 0.01; pixels never escape. */
    static double[] lumaStatistics(ByteBuffer y) {
        int remaining = y.remaining();
        int step = Math.max(1, remaining / 4096);
        long sum = 0, squares = 0;
        int samples = 0;
        for (int i = 0; i < remaining; i += step) {
            int value = y.get(y.position() + i) & 0xFF;
            sum += value; squares += (long) value * value; samples++;
        }
        double mean = (double) sum / samples;
        double variance = Math.max(0.0, (double) squares / samples - mean * mean);
        return new double[]{Math.round(mean * 100.0) / 100.0, Math.round(variance * 100.0) / 100.0};
    }

    private void complete() {
        if (!c.current(job) || closed || !frameSeen || !captureSeen) return;
        if (c.activity.checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            c.finish(job, "RESTRICTED", "PERMISSION_REQUIRED");
            return;
        }
        boolean match = imageTime == captureTime;
        job.metric("frame_metadata_match", match ? 1 : 0, "boolean");
        c.finish(job, match ? "PASS" : "INCONCLUSIVE", match ? "CAPTURE_MATCH" : "METADATA_MISMATCH");
    }
    @Override public void close() {
        closed = true;
        try { if (session != null) session.close(); }
        finally { try { if (device != null) device.close(); } finally { if (reader != null) reader.close(); } }
    }
}
