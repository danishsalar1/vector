package org.vector.probe;

import static org.junit.Assert.*;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.*;
import org.junit.Test;

public final class DiagnosticProtocolTest {
    static final Instant NOW = Instant.parse("2026-10-08T00:00:00Z");
    static Map<String, Object> request(String op, int seq) { return request(op, seq, "01234567-89ab-4def-8123-456789abcdef"); }
    static Map<String, Object> request(String op, int seq, String challenge) {
        Map<String, Object> r = new LinkedHashMap<>();
        r.put("protocol_version", 2); r.put("probe_session_id", "01234567-89ab-4def-8123-456789abcdef");
        r.put("device_epoch", 1); r.put("binding", null); r.put("nonce", String.format(Locale.ROOT, "%043d", seq));
        r.put("sequence_number", seq); r.put("issued_at", NOW.toString()); r.put("expires_at", NOW.plusSeconds(30).toString()); r.put("operation", op);
        if (op.endsWith("CHALLENGE") || op.equals("FETCH_OBSERVATIONS")) {
            Map<String, Object> b = new LinkedHashMap<>();
            b.put("scan_id", "01234567-89ab-4def-8123-456789abcdef"); b.put("diagnostic_id", "touch");
            b.put("attempt_id", "01234567-89ab-4def-8123-456789abcdef"); b.put("challenge_id", challenge);
            b.put("collection_not_before", NOW.toString()); r.put("binding", b);
        }
        return r;
    }
    static byte[] wire(Map<String, Object> r) { return new GsonBuilder().serializeNulls().create().toJson(r).getBytes(StandardCharsets.UTF_8); }
    static JsonObject json(byte[] response) { return JsonParser.parseString(new String(response, StandardCharsets.UTF_8)).getAsJsonObject(); }
    static String challenge(int n) { return String.format(Locale.ROOT, "00000000-0000-4000-8000-%012x", n); }
    static final class Handler implements ControlProtocol.Diagnostics {
        final DiagnosticSession session = new DiagnosticSession(); int calls; boolean completeOnStart;
        @Override public List<Map<String, Object>> capabilities() { return Collections.emptyList(); }
        @Override public Map<String, Object> command(String op, Map<String, Object> b) {
            calls++;
            DiagnosticJob j = op.equals("START_CHALLENGE") ? session.start(b, 0) : session.lookup(b);
            if (j == null) return null;
            if (op.equals("START_CHALLENGE") && completeOnStart) j.finish("INCONCLUSIVE", "TELEMETRY_ONLY", 0);
            if (op.equals("CANCEL_CHALLENGE")) j.cancel(false, 100);
            return j.snapshot(100);
        }
        @Override public boolean isExhausted() { return session.isExhausted(); }
    }
    @Test public void v2StartsPollsHeartbeatsAndCancelsWithoutWaitingForUser() throws Exception {
        Handler h = new Handler(); ControlProtocol p = new ControlProtocol(NOW, 0, 26, h);
        String hello = new String(p.respond(wire(request("HELLO", 0)), NOW, 1), StandardCharsets.UTF_8);
        assertTrue(hello.contains("0.2.0"));
        String start = new String(p.respond(wire(request("START_CHALLENGE", 1)), NOW, 2), StandardCharsets.UTF_8);
        assertEquals("RUNNING", JsonParser.parseString(start).getAsJsonObject().getAsJsonObject("diagnostic").get("state").getAsString());
        p.respond(wire(request("HEARTBEAT", 2)), NOW, 3);
        p.respond(wire(request("FETCH_OBSERVATIONS", 3)), NOW, 4);
        String cancelled = new String(p.respond(wire(request("CANCEL_CHALLENGE", 4)), NOW, 5), StandardCharsets.UTF_8);
        assertEquals("CANCELLED", JsonParser.parseString(cancelled).getAsJsonObject().getAsJsonObject("diagnostic").get("state").getAsString());
        assertEquals(3, h.calls);
    }
    @Test public void wrongEpochReplayAndMalformedCommandNeverReachCollector() throws Exception {
        Handler h = new Handler(); ControlProtocol p = new ControlProtocol(NOW, 0, 26, h);
        p.respond(wire(request("HELLO", 0)), NOW, 1);
        final Map<String, Object> wrong = request("START_CHALLENGE", 1); wrong.put("device_epoch", 2);
        assertThrows(IOException.class, () -> p.respond(wire(wrong), NOW, 2)); assertEquals(0, h.calls);
        p.respond(wire(request("START_CHALLENGE", 1)), NOW, 3);
        assertThrows(IOException.class, () -> p.respond(wire(request("START_CHALLENGE", 1)), NOW, 4)); assertEquals(1, h.calls);
        final Map<String, Object> malformed = request("START_CHALLENGE", 2); malformed.put("shell", "forbidden");
        assertThrows(IOException.class, () -> p.respond(wire(malformed), NOW, 5)); assertEquals(1, h.calls);
    }
    @Test public void incompatibleProtocolFailsClosedBothWays() {
        Handler h = new Handler(); ControlProtocol v2 = new ControlProtocol(NOW, 0, 26, h);
        Map<String, Object> v1 = request("HELLO", 0); v1.put("protocol_version", 1);
        assertThrows(IOException.class, () -> v2.respond(wire(v1), NOW, 1));
        assertThrows(IOException.class, () -> new ControlProtocol(NOW, 0, 26).respond(wire(request("HELLO", 0)), NOW, 1));
        assertEquals(0, h.calls);
    }

    /** TG-04: only a START is refused with ERROR once the 256-challenge budget is spent. */
    @Test public void exhaustedBudgetAnswersErrorOnlyToStart() throws Exception {
        Handler h = new Handler(); h.completeOnStart = true;
        ControlProtocol p = new ControlProtocol(NOW, 0, 26, h);
        p.respond(wire(request("HELLO", 0)), NOW, 1);
        int seq = 1;
        for (int i = 0; i < 256; i++) {
            JsonObject start = json(p.respond(wire(request("START_CHALLENGE", seq, challenge(i))), NOW, ++seq));
            assertEquals("start " + i, "OK", start.get("status").getAsString());
        }
        assertTrue(h.isExhausted());
        JsonObject refused = json(p.respond(wire(request("START_CHALLENGE", seq, challenge(256))), NOW, ++seq));
        assertEquals("ERROR", refused.get("status").getAsString());
        assertTrue(refused.get("diagnostic").isJsonNull());
        JsonObject staleFetch = json(p.respond(wire(request("FETCH_OBSERVATIONS", seq, challenge(0))), NOW, ++seq));
        assertEquals("UNAVAILABLE", staleFetch.get("status").getAsString());
        JsonObject staleCancel = json(p.respond(wire(request("CANCEL_CHALLENGE", seq, challenge(3))), NOW, ++seq));
        assertEquals("UNAVAILABLE", staleCancel.get("status").getAsString());
        JsonObject latest = json(p.respond(wire(request("FETCH_OBSERVATIONS", seq, challenge(255))), NOW, ++seq));
        assertEquals("OK", latest.get("status").getAsString());
        assertEquals("TELEMETRY_ONLY", latest.getAsJsonObject("diagnostic").get("reason").getAsString());
    }
    @Test public void unavailableWithoutExhaustionNeverAnswersError() throws Exception {
        Handler h = new Handler(); ControlProtocol p = new ControlProtocol(NOW, 0, 26, h);
        p.respond(wire(request("HELLO", 0)), NOW, 1);
        p.respond(wire(request("START_CHALLENGE", 1, challenge(1))), NOW, 2);
        JsonObject busy = json(p.respond(wire(request("START_CHALLENGE", 2, challenge(2))), NOW, 3));
        assertEquals("UNAVAILABLE", busy.get("status").getAsString());
        JsonObject unknown = json(p.respond(wire(request("FETCH_OBSERVATIONS", 3, challenge(9))), NOW, 4));
        assertEquals("UNAVAILABLE", unknown.get("status").getAsString());
    }

    // Literal cross-language vector, pinned identically in test_phase8c_diagnostics.py: the
    // requests are the production Python session's bytes; the response is ControlProtocol's.
    static final String PINNED_HELLO = "{\"protocol_version\":2,\"probe_session_id\":\"5e55a000-0000-4000-8000-0000000000aa\",\"device_epoch\":3,\"binding\":null,\"nonce\":\"pinned0000000000000000000000000000000000001\",\"sequence_number\":0,\"issued_at\":\"2026-10-09T00:00:00Z\",\"expires_at\":\"2026-10-09T00:00:30Z\",\"operation\":\"HELLO\"}";
    static final String PINNED_START = "{\"protocol_version\":2,\"probe_session_id\":\"5e55a000-0000-4000-8000-0000000000aa\",\"device_epoch\":3,\"binding\":{\"scan_id\":\"5e55a000-0000-4000-8000-0000000000b1\",\"diagnostic_id\":\"storage\",\"attempt_id\":\"5e55a000-0000-4000-8000-0000000000b2\",\"challenge_id\":\"5e55a000-0000-4000-8000-0000000000b3\",\"collection_not_before\":\"2026-10-09T00:00:00Z\"},\"nonce\":\"pinned0000000000000000000000000000000000002\",\"sequence_number\":1,\"issued_at\":\"2026-10-09T00:00:00Z\",\"expires_at\":\"2026-10-09T00:00:30Z\",\"operation\":\"START_CHALLENGE\"}";
    static final String PINNED_START_RESPONSE = "{\"protocol_version\":2,\"probe_session_id\":\"5e55a000-0000-4000-8000-0000000000aa\",\"device_epoch\":3,\"binding\":{\"scan_id\":\"5e55a000-0000-4000-8000-0000000000b1\",\"diagnostic_id\":\"storage\",\"attempt_id\":\"5e55a000-0000-4000-8000-0000000000b2\",\"challenge_id\":\"5e55a000-0000-4000-8000-0000000000b3\",\"collection_not_before\":\"2026-10-09T00:00:00Z\"},\"nonce\":\"pinned0000000000000000000000000000000000002\",\"sequence_number\":1,\"issued_at\":\"2026-10-09T00:00:00Z\",\"expires_at\":\"2026-10-09T00:00:30Z\",\"operation\":\"START_CHALLENGE\",\"status\":\"OK\",\"diagnostic_capabilities\":[],\"diagnostic\":{\"schema_version\":1,\"diagnostic_id\":\"storage\",\"state\":\"RUNNING\",\"outcome\":\"INCONCLUSIVE\",\"reason\":\"COLLECTING\",\"elapsed_ms\":100,\"metrics\":[]},\"probe_build\":null,\"observations\":[],\"capabilities\":[]}";

    static String hex(byte[] bytes) {
        StringBuilder text = new StringBuilder();
        for (byte b : bytes) text.append(String.format(Locale.ROOT, "%02x", b & 0xff));
        return text.toString();
    }

    @Test public void pinnedV2GoldenVectorsHold() throws Exception {
        byte[] key = new byte[32];
        for (int i = 0; i < 32; i++) key[i] = (byte) (i + 1);
        assertEquals("ee14950c059cf98edc6488038d9950b1dc2ebefa347ea2a15a6848da642bc149",
                hex(ProbeServer.mac(key, "request", PINNED_START.getBytes(StandardCharsets.UTF_8))));
        Instant issued = Instant.parse("2026-10-09T00:00:00Z");
        ControlProtocol p = new ControlProtocol(issued, 0, 35, new Handler());
        p.respond(PINNED_HELLO.getBytes(StandardCharsets.UTF_8), issued, 1);
        byte[] response = p.respond(PINNED_START.getBytes(StandardCharsets.UTF_8), issued, 2);
        assertEquals(PINNED_START_RESPONSE, new String(response, StandardCharsets.UTF_8));
        assertEquals("334d004eb33fb9e6be039f4e1d868752d052f795a83d76ef98a5aacaac98e72b", hex(ProbeServer.mac(key, "response", response)));
    }
}
