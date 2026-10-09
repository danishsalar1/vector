package org.vector.probe;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import android.app.Activity;
import android.app.Application;
import android.content.pm.PackageManager;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorManager;
import android.hardware.camera2.CameraAccessException;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraDevice;
import android.hardware.camera2.CaptureRequest;
import android.hardware.camera2.CaptureResult;
import android.os.Looper;
import android.view.InputDevice;
import android.view.MotionEvent;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.File;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Consumer;
import org.junit.After;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.Shadows;
import org.robolectric.annotation.Config;
import org.robolectric.shadow.api.Shadow;
import org.robolectric.shadows.ShadowAudioRecord;
import org.robolectric.shadows.ShadowCameraCharacteristics;
import org.robolectric.shadows.ShadowSensor;
import org.robolectric.shadows.ShadowSensorManager;
import org.robolectric.shadows.ShadowStatFs;
import org.robolectric.shadows.StreamConfigurationMapBuilder;
import org.robolectric.util.ReflectionHelpers;

/**
 * Permanent Java side of the Probe v2 cross-language contract (local-agent/tests/fixtures/
 * cross_language/contract.json).
 *
 * <p>The production Python session's framed requests (python_requests.json) drive the REAL
 * DiagnosticController, collectors and ControlProtocol, answered off the main thread exactly as
 * ProbeServer does. Request MACs are verified and response MACs computed with ProbeServer.mac.
 * Every exchange must match the contract's expectations, and every response frame must equal
 * java_responses.json byte for byte. Fixtures are written ONLY when the build is run with
 * -Pvector.updateCrossLanguageFixtures=true for an approved protocol change; an ordinary run
 * never writes. Robolectric cannot deliver Camera2 HAL callbacks, so camera frames and capture
 * results enter at the CameraCollector event boundary after a real open/session/capture.
 */
@RunWith(RobolectricTestRunner.class)
@Config(sdk = 35)
public final class DiagnosticCrossLanguageExportTest {
    private static final File DIR = new File(System.getProperty(
            "vector.crossLanguageFixtures", "../../local-agent/tests/fixtures/cross_language"));
    private static final boolean UPDATE = Boolean.parseBoolean(
            System.getProperty("vector.updateCrossLanguageFixtures", "false"));
    private static final Gson COMPACT = new GsonBuilder().serializeNulls().create();
    private static final Gson PRETTY = new GsonBuilder().serializeNulls().setPrettyPrinting().disableHtmlEscaping().create();
    private static final long T_FRAME = 7_000_000_123L;

    private Session session;

    @After public void release() {
        StorageCollector.testIoHook = null;
        CameraCollector.setCameraOpenerForTest(null);
        ShadowAudioRecord.clearSource();
        if (session != null) session.close();
    }

    // ------------------------------------------------------------------ fixtures

    private static JsonObject json(File file) throws IOException {
        if (!file.isFile()) fail("Missing cross-language fixture " + file + ". See contract.json 'about'.");
        return JsonParser.parseString(new String(Files.readAllBytes(file.toPath()), StandardCharsets.UTF_8)).getAsJsonObject();
    }

    private static JsonObject contract() throws IOException { return json(new File(DIR, "contract.json")); }

    private static byte[] hex(String text) {
        byte[] out = new byte[text.length() / 2];
        for (int i = 0; i < out.length; i++) out[i] = (byte) Integer.parseInt(text.substring(2 * i, 2 * i + 2), 16);
        return out;
    }

    private static String hex(byte[] bytes) {
        StringBuilder text = new StringBuilder();
        for (byte b : bytes) text.append(String.format(Locale.ROOT, "%02x", b & 0xff));
        return text.toString();
    }

    private static byte[] framed(JsonObject frame) {
        byte[] payload = frame.get("payload").getAsString().getBytes(StandardCharsets.UTF_8);
        return ByteBuffer.allocate(36 + payload.length).putInt(payload.length)
                .put(hex(frame.get("mac").getAsString())).put(payload).array();
    }

    // ------------------------------------------------------------------ one Probe session

    /** Socket thread answers like ProbeServer; the test thread is the Android main looper. */
    private final class Session implements AutoCloseable {
        final String name;
        final JsonObject spec;
        final JsonArray exchanges;
        final JsonArray requests;
        final byte[] key;
        final Activity activity;
        final LinearLayout host;
        final DiagnosticController controller;
        final ControlProtocol protocol;
        final Instant issued;
        final ExecutorService socket = Executors.newSingleThreadExecutor();
        final List<JsonObject> produced = new ArrayList<>();
        long nanos = 1_000_000_000L;
        int index;

        Session(String name, Consumer<Activity> device) throws IOException {
            this.name = name;
            spec = contract();
            JsonObject scenario = null;
            for (JsonElement item : spec.getAsJsonArray("scenarios")) {
                if (item.getAsJsonObject().get("name").getAsString().equals(name)) scenario = item.getAsJsonObject();
            }
            assertNotNull("scenario " + name + " missing from contract.json", scenario);
            exchanges = scenario.getAsJsonArray("exchanges");
            requests = json(new File(DIR, "python_requests.json")).getAsJsonObject("scenarios").getAsJsonArray(name);
            assertEquals("python_requests.json is stale for " + name, exchanges.size(), requests.size());
            key = hex(spec.get("key_hex").getAsString());
            issued = Instant.parse(spec.get("issued_at").getAsString());
            activity = Robolectric.buildActivity(Activity.class).setup().get();
            host = new LinearLayout(activity);
            activity.setContentView(host);
            device.accept(activity);
            controller = new DiagnosticController(activity, host);
            protocol = new ControlProtocol(issued, nanos, spec.get("api_level").getAsInt(), controller);
        }

        String where() { return name + "#" + index + " " + exchanges.get(index).getAsJsonObject().get("op").getAsString(); }

        /** Answers the next contract request and checks it against the contract expectation. */
        JsonObject exchange() throws Exception {
            assertTrue("more exchanges than contract.json defines for " + name, index < exchanges.size());
            JsonObject expected = exchanges.get(index).getAsJsonObject();
            JsonObject request = requests.get(index).getAsJsonObject();
            byte[] payload = request.get("payload").getAsString().getBytes(StandardCharsets.UTF_8);
            assertArrayEquals("request MAC " + where(), ProbeServer.mac(key, "request", payload), hex(request.get("mac").getAsString()));
            long at = nanos += 1_000_000L;
            byte[] response = socket.submit(() -> protocol.respond(payload, issued, at)).get();
            JsonObject frame = new JsonObject();
            frame.addProperty("mac", hex(ProbeServer.mac(key, "response", response)));
            frame.addProperty("payload", new String(response, StandardCharsets.UTF_8));
            produced.add(frame);
            JsonObject decoded = JsonParser.parseString(new String(response, StandardCharsets.UTF_8)).getAsJsonObject();
            assertEquals("operation " + where(), expected.get("op").getAsString(), decoded.get("operation").getAsString());
            assertEquals("status " + where(), expected.get("status").getAsString(), decoded.get("status").getAsString());
            if (expected.has("report")) {
                JsonArray triple = expected.getAsJsonArray("report");
                JsonObject report = decoded.getAsJsonObject("diagnostic");
                String actual = report.get("state").getAsString() + "/" + report.get("outcome").getAsString() + "/" + report.get("reason").getAsString();
                assertEquals("report " + where(), triple.get(0).getAsString() + "/" + triple.get(1).getAsString() + "/" + triple.get(2).getAsString(), actual);
                if (expected.has("metrics")) {
                    for (Map.Entry<String, JsonElement> metric : expected.getAsJsonObject("metrics").entrySet()) {
                        JsonElement value = null;
                        for (JsonElement item : report.getAsJsonArray("metrics")) {
                            if (item.getAsJsonObject().get("name").getAsString().equals(metric.getKey())) value = item.getAsJsonObject().get("value");
                        }
                        assertNotNull("metric " + metric.getKey() + " " + where(), value);
                        assertEquals("metric " + metric.getKey() + " " + where(), metric.getValue().getAsDouble(), value.getAsDouble(), 0.0);
                    }
                }
            }
            index++;
            return decoded;
        }

        void connect() throws Exception { exchange(); exchange(); }
        void idle() { Shadows.shadowOf(Looper.getMainLooper()).idle(); }
        void idleFor(long millis) { Shadows.shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMillis(millis)); }

        /** Lets main and any collector worker reach the job's terminal state. */
        void awaitJob() throws InterruptedException {
            for (int i = 0; i < 200; i++) {
                idle();
                DiagnosticJob job = controller.getActiveJob();
                if (job != null && !job.running()) { idle(); return; }
                Thread.sleep(10);
            }
            fail("job did not reach a terminal state " + where());
        }

        CameraCollector camera() {
            Object resource = ReflectionHelpers.getField(controller, "resource");
            assertTrue("camera collector owns the active resource " + where(), resource instanceof CameraCollector);
            return (CameraCollector) resource;
        }

        Button button(View root, int label) {
            Button found = find(root, activity.getString(label));
            assertNotNull("button '" + activity.getString(label) + "' " + where(), found);
            return found;
        }

        void finish() throws Exception {
            assertEquals("every contract exchange answered for " + name, exchanges.size(), index);
            File responses = new File(DIR, "java_responses.json");
            if (UPDATE) {
                record(responses);
                return;
            }
            JsonArray committed = json(responses).getAsJsonObject("scenarios").getAsJsonArray(name);
            assertNotNull("java_responses.json lacks " + name + "; run the approved update operation", committed);
            assertEquals("frame count " + name, committed.size(), produced.size());
            for (int i = 0; i < produced.size(); i++) {
                assertEquals(name + "#" + i + " response payload changed; if this protocol change is approved, run "
                        + "gradle testDebugUnitTest -Pvector.updateCrossLanguageFixtures=true",
                        committed.get(i).getAsJsonObject().get("payload").getAsString(), produced.get(i).get("payload").getAsString());
                assertEquals(name + "#" + i + " response MAC", committed.get(i).getAsJsonObject().get("mac").getAsString(), produced.get(i).get("mac").getAsString());
            }
            for (Map.Entry<String, JsonElement> legacy : spec.getAsJsonObject("legacy_extracts").entrySet()) {
                JsonArray at = legacy.getValue().getAsJsonArray();
                if (!at.get(0).getAsString().equals(name)) continue;
                assertArrayEquals("legacy fixture " + legacy.getKey(), framed(produced.get(at.get(1).getAsInt())),
                        Files.readAllBytes(new File(DIR, legacy.getKey()).toPath()));
            }
            for (Map.Entry<String, JsonElement> legacy : spec.getAsJsonObject("legacy_capabilities").entrySet()) {
                if (!legacy.getValue().getAsString().equals(name)) continue;
                assertEquals("legacy fixture " + legacy.getKey(), capabilities(),
                        new String(Files.readAllBytes(new File(DIR, legacy.getKey()).toPath()), StandardCharsets.UTF_8));
            }
        }

        String capabilities() {
            JsonObject response = JsonParser.parseString(produced.get(1).get("payload").getAsString()).getAsJsonObject();
            return COMPACT.toJson(response.getAsJsonArray("diagnostic_capabilities"));
        }

        /** Approved protocol change only: rewrite this scenario's frames and its legacy extracts. */
        void record(File responses) throws IOException {
            JsonObject document = responses.isFile() ? json(responses) : new JsonObject();
            JsonObject old = document.has("scenarios") ? document.getAsJsonObject("scenarios") : new JsonObject();
            JsonObject ordered = new JsonObject();
            for (JsonElement item : spec.getAsJsonArray("scenarios")) {
                String scenario = item.getAsJsonObject().get("name").getAsString();
                if (scenario.equals(name)) {
                    JsonArray frames = new JsonArray();
                    for (JsonObject frame : produced) frames.add(frame);
                    ordered.add(scenario, frames);
                } else if (old.has(scenario)) {
                    ordered.add(scenario, old.get(scenario));
                }
            }
            JsonObject out = new JsonObject();
            out.addProperty("generator", "android-probe DiagnosticCrossLanguageExportTest (-Pvector.updateCrossLanguageFixtures=true)");
            out.add("scenarios", ordered);
            Files.write(responses.toPath(), (PRETTY.toJson(out) + "\n").getBytes(StandardCharsets.UTF_8));
            for (Map.Entry<String, JsonElement> legacy : spec.getAsJsonObject("legacy_extracts").entrySet()) {
                JsonArray at = legacy.getValue().getAsJsonArray();
                if (at.get(0).getAsString().equals(name)) {
                    Files.write(new File(DIR, legacy.getKey()).toPath(), framed(produced.get(at.get(1).getAsInt())));
                }
            }
            for (Map.Entry<String, JsonElement> legacy : spec.getAsJsonObject("legacy_capabilities").entrySet()) {
                if (legacy.getValue().getAsString().equals(name)) {
                    Files.write(new File(DIR, legacy.getKey()).toPath(), capabilities().getBytes(StandardCharsets.UTF_8));
                }
            }
        }

        @Override public void close() {
            controller.close();
            idle();
            socket.shutdownNow();
        }
    }

    // ------------------------------------------------------------------ device helpers

    private static Button find(View root, String text) {
        if (root instanceof Button && text.contentEquals(((Button) root).getText())) return (Button) root;
        if (root instanceof android.view.ViewGroup) {
            android.view.ViewGroup group = (android.view.ViewGroup) root;
            for (int i = 0; i < group.getChildCount(); i++) {
                Button found = find(group.getChildAt(i), text);
                if (found != null) return found;
            }
        }
        return null;
    }

    private static void features(Activity activity, String... names) {
        for (String feature : names) Shadows.shadowOf(activity.getPackageManager()).setSystemFeature(feature, true);
    }

    private static void vibrator(Activity activity, boolean present) {
        Shadows.shadowOf(activity.getSystemService(android.os.Vibrator.class)).setHasVibrator(present);
    }

    private static void grant(Activity activity, String permission) {
        Shadows.shadowOf((Application) activity.getApplicationContext()).grantPermissions(permission);
    }

    private static void deny(Activity activity, String permission) {
        Shadows.shadowOf((Application) activity.getApplicationContext()).denyPermissions(permission);
    }

    private static Sensor sensor(int type, float maxRange, float resolution) {
        Sensor sensor = ShadowSensor.newInstance(type);
        ShadowSensor shadow = Shadow.extract(sensor);
        shadow.setMaximumRange(maxRange);
        ReflectionHelpers.setField(sensor, "mResolution", resolution);
        return sensor;
    }

    private static void sensors(Activity activity, Sensor... list) {
        ShadowSensorManager manager = Shadows.shadowOf(activity.getSystemService(SensorManager.class));
        for (Sensor sensor : list) manager.addSensor(sensor);
    }

    private static void camera(Activity activity, String id, int facing, int level, boolean flash, boolean autofocus) {
        CameraCharacteristics characteristics = ShadowCameraCharacteristics.newCameraCharacteristics();
        ShadowCameraCharacteristics shadow = Shadows.shadowOf(characteristics);
        shadow.set(CameraCharacteristics.LENS_FACING, facing);
        shadow.set(CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL, level);
        shadow.set(CameraCharacteristics.FLASH_INFO_AVAILABLE, flash);
        shadow.set(CameraCharacteristics.CONTROL_AF_AVAILABLE_MODES, autofocus
                ? new int[]{CaptureRequest.CONTROL_AF_MODE_OFF, CaptureRequest.CONTROL_AF_MODE_AUTO}
                : new int[]{CaptureRequest.CONTROL_AF_MODE_OFF});
        shadow.set(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP, StreamConfigurationMapBuilder.newBuilder()
                .addOutputSize(android.graphics.ImageFormat.YUV_420_888, new android.util.Size(640, 480)).build());
        Shadows.shadowOf(activity.getSystemService(android.hardware.camera2.CameraManager.class)).addCamera(id, characteristics);
    }

    private static void statFs(Activity activity) {
        ShadowStatFs.registerStats(activity.getCacheDir(), 10000, 10000, 10000);
        ShadowStatFs.registerStats(activity.getCacheDir().getAbsolutePath(), 10000, 10000, 10000);
    }

    /** Deterministic luma (Y) plane for a 640x480 frame: a repeating 0..250 ramp. */
    private static ByteBuffer luma() {
        byte[] y = new byte[640 * 480];
        for (int i = 0; i < y.length; i++) y[i] = (byte) (i % 251);
        return ByteBuffer.wrap(y);
    }

    private static void touch(View grid, float x, float y) {
        MotionEvent event = MotionEvent.obtain(0, 0, MotionEvent.ACTION_DOWN, x, y, 0);
        assertTrue(grid.dispatchTouchEvent(event));
        event.recycle();
    }

    private static void touchCells(View grid, int cells) {
        int w = grid.getWidth(), h = grid.getHeight();
        for (int cell = 0; cell < cells; cell++) touch(grid, w * (2 * (cell % 4) + 1) / 8f, h * (2 * (cell / 4) + 1) / 12f);
    }

    private static void twoFingers(View grid) {
        MotionEvent.PointerProperties[] properties = {new MotionEvent.PointerProperties(), new MotionEvent.PointerProperties()};
        MotionEvent.PointerCoords[] coords = {new MotionEvent.PointerCoords(), new MotionEvent.PointerCoords()};
        for (int i = 0; i < 2; i++) {
            properties[i].id = i;
            properties[i].toolType = MotionEvent.TOOL_TYPE_FINGER;
            coords[i].x = grid.getWidth() * (i + 1) / 3f;
            coords[i].y = grid.getHeight() / 2f;
        }
        MotionEvent event = MotionEvent.obtain(0, 0, MotionEvent.ACTION_POINTER_DOWN | (1 << MotionEvent.ACTION_POINTER_INDEX_SHIFT),
                2, properties, coords, 0, 0, 1f, 1f, 0, 0, InputDevice.SOURCE_TOUCHSCREEN, 0);
        assertTrue(grid.dispatchTouchEvent(event));
        event.recycle();
    }

    private static void assertReleased(CameraCollector collector) {
        assertTrue("collector closed", (Boolean) ReflectionHelpers.getField(collector, "closed"));
        Object device = ReflectionHelpers.getField(collector, "device");
        Object reader = ReflectionHelpers.getField(collector, "reader");
        assertNotNull("camera device was opened", device);
        assertTrue("camera device closed", (Boolean) ReflectionHelpers.getField(Shadow.extract(device), "closed"));
        assertFalse("image reader closed",
                ((java.util.concurrent.atomic.AtomicBoolean) ReflectionHelpers.getField(Shadow.extract(reader), "readerValid")).get());
    }

    // ------------------------------------------------------------------ scenarios

    @Test public void typicalCapabilities() throws Exception {
        session = new Session("typical_capabilities", a -> {
            features(a, PackageManager.FEATURE_TOUCHSCREEN, PackageManager.FEATURE_MICROPHONE, PackageManager.FEATURE_AUDIO_OUTPUT);
            vibrator(a, true);
            sensors(a, sensor(Sensor.TYPE_ACCELEROMETER, 39.2266f, 0.0012f), sensor(Sensor.TYPE_GYROSCOPE, 34.906586f, 0.0010652645f),
                    sensor(Sensor.TYPE_MAGNETIC_FIELD, 4912f, 0.15f), sensor(Sensor.TYPE_LIGHT, 65535f, 1f),
                    sensor(Sensor.TYPE_PROXIMITY, 5f, 5f), sensor(Sensor.TYPE_PRESSURE, 1100f, 0.01f),
                    sensor(Sensor.TYPE_GRAVITY, 39.2266f, 0.0012f), sensor(Sensor.TYPE_LINEAR_ACCELERATION, 39.2266f, 0.0012f),
                    sensor(Sensor.TYPE_ROTATION_VECTOR, 1f, 5.9604645E-8f), sensor(Sensor.TYPE_STEP_DETECTOR, 1f, 1f),
                    sensor(Sensor.TYPE_STEP_COUNTER, 16777216f, 1f));
            camera(a, "0", CameraCharacteristics.LENS_FACING_BACK, CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL_LIMITED, true, true);
            camera(a, "1", CameraCharacteristics.LENS_FACING_FRONT, CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL_FULL, false, false);
        });
        session.connect();
        session.finish();
    }

    @Test public void sparseCapabilities() throws Exception {
        session = new Session("sparse_capabilities", a -> {
            features(a, PackageManager.FEATURE_TOUCHSCREEN);
            vibrator(a, false);
            sensors(a, sensor(Sensor.TYPE_ACCELEROMETER, 39.2266f, 0.0012f), sensor(Sensor.TYPE_LIGHT, 10000f, 1f));
        });
        session.connect();
        session.finish();
    }

    @Test public void extremeCapabilities() throws Exception {
        session = new Session("extreme_capabilities", a -> {
            sensors(a, sensor(Sensor.TYPE_ACCELEROMETER, Float.MAX_VALUE, 0f), sensor(Sensor.TYPE_GYROSCOPE, Float.POSITIVE_INFINITY, Float.NaN),
                    sensor(Sensor.TYPE_MAGNETIC_FIELD, -1f, 1.1920929E-7f), sensor(Sensor.TYPE_LIGHT, 120000f, 1f),
                    sensor(Sensor.TYPE_PROXIMITY, 5f, 5f), sensor(Sensor.TYPE_PRESSURE, 1100f, 0.01f),
                    sensor(Sensor.TYPE_GRAVITY, 19.6f, 0.0012f), sensor(Sensor.TYPE_LINEAR_ACCELERATION, 19.6f, 0.0012f),
                    sensor(Sensor.TYPE_ROTATION_VECTOR, 1f, 5.9604645E-8f), sensor(Sensor.TYPE_STEP_DETECTOR, 1f, 1f),
                    sensor(Sensor.TYPE_STEP_COUNTER, 4294967296f, 1f));
            for (int type : new int[]{Sensor.TYPE_GAME_ROTATION_VECTOR, Sensor.TYPE_AMBIENT_TEMPERATURE, Sensor.TYPE_RELATIVE_HUMIDITY, Sensor.TYPE_HEART_RATE}) {
                sensors(a, sensor(type, 100f, 0.1f));
            }
            for (int i = 0; i < 70; i++) sensors(a, sensor(0x10001 + i, i % 7 == 0 ? Float.MAX_VALUE : 50f + i, i % 5 == 0 ? 0f : 0.001f));
            sensors(a, sensor(Integer.MAX_VALUE, 1f, 1f));
            for (String id : new String[]{"0", "1", "2", "3", "4", "20", "21", "22", "23", "40", "41", "42", "50", "51", "52", "60", "61", "62"}) {
                camera(a, id, CameraCharacteristics.LENS_FACING_EXTERNAL, CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL_EXTERNAL, false, false);
            }
        });
        session.connect();
        session.finish();
    }

    @Test public void storage() throws Exception {
        session = new Session("storage", DiagnosticCrossLanguageExportTest::statFs);
        Session s = session;
        s.connect();
        s.exchange(); s.awaitJob(); s.exchange();                               // PASS
        StorageCollector.testIoHook = file -> {                                 // FAIL: one flipped byte
            try (java.io.RandomAccessFile raf = new java.io.RandomAccessFile(file, "rw")) {
                int first = raf.read(); raf.seek(0); raf.write(first ^ 0xFF);
            }
        };
        s.exchange(); s.awaitJob(); s.exchange();
        StorageCollector.testIoHook = file -> { throw new IOException("injected read fault"); };
        s.exchange(); s.awaitJob(); s.exchange();                               // READ_ERROR
        StorageCollector.testIoHook = new StorageCollector.StorageIoHook() {
            @Override public void onBeforeWrite(File file) throws IOException { throw new IOException("injected write fault"); }
            @Override public void onBeforeRead(File file) { }
        };
        s.exchange(); s.awaitJob(); s.exchange();                               // WRITE_ERROR
        File[] leftover = new File[1];
        StorageCollector.testIoHook = file -> {                                 // CLEANUP_ERROR
            assertTrue(file.delete() && file.mkdir() && new File(file, "pinned").createNewFile());
            leftover[0] = file;
        };
        s.exchange(); s.awaitJob(); s.exchange();
        assertTrue("undeletable temporary entry reported, still present", leftover[0].isDirectory());
        assertTrue(new File(leftover[0], "pinned").delete() && leftover[0].delete());
        s.finish();
    }

    @Test public void camera() throws Exception {
        session = new Session("camera", a -> {
            grant(a, android.Manifest.permission.CAMERA);
            camera(a, "0", CameraCharacteristics.LENS_FACING_BACK, CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL_LIMITED, true, true);
        });
        Session s = session;
        s.connect();
        s.exchange(); s.idle();                                                 // PASS
        CameraCollector camera = s.camera();
        camera.onCaptureResult(T_FRAME, CaptureResult.CONTROL_AF_STATE_FOCUSED_LOCKED);
        camera.onFrame(640, 480, 460800, T_FRAME, luma());
        s.exchange();
        assertReleased(camera);
        s.exchange(); s.idle();                                                 // METADATA_MISMATCH
        camera = s.camera();
        camera.onCaptureResult(T_FRAME, CaptureResult.CONTROL_AF_STATE_FOCUSED_LOCKED);
        camera.onFrame(640, 480, 460800, T_FRAME + 33_000_000L, luma());
        s.exchange();
        s.exchange(); s.idle();                                                 // INVALID_FRAME
        s.camera().onFrame(640, 480, 153600, T_FRAME, ByteBuffer.allocate(0));
        s.exchange();
        s.exchange(); s.idle();                                                 // METADATA_UNAVAILABLE
        s.camera().onCaptureResult(null, null);
        s.exchange();
        s.exchange(); s.idle();                                                 // CAPTURE_ERROR
        s.camera().onCaptureFailed();
        s.exchange();
        for (int error : new int[]{CameraDevice.StateCallback.ERROR_CAMERA_DISABLED, CameraDevice.StateCallback.ERROR_CAMERA_IN_USE,
                CameraDevice.StateCallback.ERROR_CAMERA_DEVICE}) {
            CameraCollector.setCameraOpenerForTest((manager, id, callback, handler) -> handler.post(() -> callback.onError(null, error)));
            s.exchange(); s.idle(); s.exchange();
        }
        CameraCollector.setCameraOpenerForTest((manager, id, callback, handler) -> {
            throw new CameraAccessException(CameraAccessException.CAMERA_DISCONNECTED);
        });
        s.exchange(); s.idle(); s.exchange();                                   // CAMERA_DISCONNECTED
        CameraCollector.setCameraOpenerForTest(null);
        s.exchange(); s.idle();                                                 // stall -> TIMEOUT
        camera = s.camera();
        s.idleFor(10_000);
        s.exchange();
        assertReleased(camera);
        s.exchange(); s.idle();                                                 // desktop cancel
        camera = s.camera();
        s.exchange();                                                           // STOPPING: main has not released yet
        assertFalse("camera still owned while STOPPING", (Boolean) ReflectionHelpers.getField(camera, "closed"));
        s.idle();
        s.exchange();                                                           // CANCELLED after release
        assertReleased(camera);
        deny(s.activity, android.Manifest.permission.CAMERA);
        s.exchange(); s.idle(); s.exchange();                                   // PERMISSION_REQUIRED
        s.finish();
    }

    @Test @Config(qualifiers = "w411dp-h891dp-xxhdpi")
    public void touchDisplay() throws Exception {
        session = new Session("touch_display", a -> features(a, PackageManager.FEATURE_TOUCHSCREEN));
        Session s = session;
        s.connect();
        s.exchange(); s.idle();                                                 // touch PASS
        DiagnosticUi.TouchView grid = s.controller.ui.touchView;
        touchCells(grid, 24);
        twoFingers(grid);
        s.button(s.controller.ui.touchDialog.getWindow().getDecorView(), R.string.diag_done).performClick();
        s.idle(); s.exchange();
        s.exchange(); s.idle();                                                 // geometry too small -> PARTIAL
        grid = s.controller.ui.touchView;
        grid.layout(0, 0, 180, 180);
        touchCells(grid, 24);
        assertEquals("all cells of the tiny grid covered", 24, grid.touch.count);
        s.button(s.controller.ui.touchDialog.getWindow().getDecorView(), R.string.diag_done).performClick();
        s.idle(); s.exchange();
        s.exchange(); s.idle();                                                 // desktop cancel
        touchCells(s.controller.ui.touchView, 5);
        s.exchange(); s.idle(); s.exchange();
        s.exchange(); s.idle();                                                 // pixels: person reports a defect
        Button next = s.button(s.controller.ui.colorsDialog.getWindow().getDecorView(), R.string.diag_next_color);
        for (int i = 0; i < 5; i++) { next.performClick(); s.idle(); }
        s.button(s.host, R.string.diag_pixels_no).performClick();
        s.idle(); s.exchange();
        s.exchange(); s.idle(); s.exchange();                                   // display telemetry
        s.finish();
    }

    @Test public void audioHaptics() throws Exception {
        ShadowAudioRecord.setSource(new ShadowAudioRecord.AudioRecordSource() {
            @Override public int readInShortArray(short[] data, int offset, int size, boolean blocking) {
                for (int i = 0; i < size; i++) data[offset + i] = (short) (12000 * Math.sin(i / 8.0));
                return size;
            }
        });
        session = new Session("audio_haptics", a -> {
            features(a, PackageManager.FEATURE_MICROPHONE, PackageManager.FEATURE_AUDIO_OUTPUT);
            vibrator(a, true);
            grant(a, android.Manifest.permission.RECORD_AUDIO);
        });
        Session s = session;
        s.connect();
        s.exchange(); s.idle();                                                 // microphone
        assertEquals("live measured level shown", s.activity.getString(R.string.diag_mic_level, 30), s.controller.ui.status.getText().toString());
        s.idleFor(3100);
        assertEquals(s.activity.getString(R.string.diag_confirmation_mic), s.controller.ui.status.getText().toString());
        s.button(s.host, R.string.diag_mic_yes).performClick();
        s.idle(); s.exchange();
        s.exchange(); s.idle();                                                 // vibration
        s.button(s.host, R.string.diag_vibrate_no).performClick();
        s.idle(); s.exchange();
        deny(s.activity, android.Manifest.permission.RECORD_AUDIO);
        s.exchange(); s.idle(); s.exchange();                                   // permission required
        s.finish();
    }

    @Test public void sensorsBattery() throws Exception {
        session = new Session("sensors_battery", a -> sensors(a, sensor(Sensor.TYPE_ACCELEROMETER, 39.2266f, 0.0012f),
                sensor(Sensor.TYPE_LIGHT, 10000f, 1f), sensor(Sensor.TYPE_STEP_COUNTER, 16777216f, 1f)));
        Session s = session;
        s.connect();
        s.exchange(); s.idle();                                                 // accelerometer samples
        SensorManager manager = s.activity.getSystemService(SensorManager.class);
        Sensor accelerometer = manager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER);
        float[][] events = {{0.5f, 0.25f, 9.75f}, {1e20f, 0f, 9.8f}, {Float.NaN, 0f, 9.8f}, {-0.5f, 0f, 9.5f}, {0f, 0.5f, 9.25f}};
        for (float[] values : events) {
            SensorEvent event = ShadowSensorManager.createSensorEvent(3);
            System.arraycopy(values, 0, event.values, 0, 3);
            Shadows.shadowOf(manager).sendSensorEventToListeners(event, accelerometer);
        }
        s.idleFor(3000); s.exchange();
        s.exchange(); s.idle(); s.idleFor(3000); s.exchange();                   // light: no samples
        s.exchange(); s.idle(); s.exchange();                                   // gyroscope absent
        s.exchange(); s.idle(); s.exchange();                                   // step counter restricted
        s.exchange(); s.idle(); s.idleFor(3000); s.exchange();                   // battery telemetry
        s.finish();
    }
}
