package org.vector.probe;

import static org.junit.Assert.*;
import com.google.gson.Gson;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import org.junit.Test;

public final class ControlProtocolTest {
    private static final Instant NOW = Instant.parse("2026-10-07T12:00:00Z");
    private static Map<String, Object> request(String op, int sequence) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("protocol_version", 1);
        value.put("probe_session_id", "01234567-89ab-4def-8123-456789abcdef");
        value.put("device_epoch", 3);
        value.put("binding", null);
        value.put("nonce", String.format(java.util.Locale.ROOT, "%043d", sequence));
        value.put("sequence_number", sequence);
        value.put("issued_at", NOW.toString());
        value.put("expires_at", NOW.plusSeconds(30).toString());
        value.put("operation", op);
        return value;
    }
    private static byte[] wire(Map<String, Object> value) {
        return new com.google.gson.GsonBuilder().serializeNulls().create().toJson(value).getBytes(StandardCharsets.UTF_8);
    }
    private static ControlProtocol protocol() { return new ControlProtocol(NOW, 1000, 26); }

    @Test public void helloCapabilitiesHeartbeat() throws Exception {
        ControlProtocol protocol = protocol();
        Map<String, Object> hello = ControlProtocol.parse(protocol.respond(wire(request("HELLO", 0)), NOW, 1001));
        assertEquals("OK", hello.get("status"));
        assertNotNull(hello.get("hello"));
        Map<String, Object> caps = ControlProtocol.parse(protocol.respond(wire(request("GET_CAPABILITIES", 1)), NOW, 1002));
        assertTrue(new Gson().toJson(caps.get("capabilities")).contains("CONTROL_CHANNEL"));
        String beat = new String(protocol.respond(wire(request("HEARTBEAT", 2)), NOW, 1003), StandardCharsets.UTF_8);
        assertFalse(beat.contains("PASS"));
        assertFalse(beat.contains("trust_score"));
    }

    @Test public void ownershipReplayAndRestart() throws Exception {
        for (String field : new String[]{"probe_session_id", "device_epoch", "nonce", "sequence_number"}) {
            ControlProtocol protocol = protocol();
            protocol.respond(wire(request("HELLO", 0)), NOW, 1001);
            Map<String, Object> next = request("HEARTBEAT", 1);
            switch (field) {
                case "probe_session_id": next.put(field, "01234567-89ab-4def-8123-456789abcdee"); break;
                case "device_epoch": next.put(field, 4); break;
                case "nonce": next.put(field, request("HELLO", 0).get("nonce")); break;
                default: next.put(field, 0);
            }
            assertThrows(IOException.class, () -> protocol.respond(wire(next), NOW, 1002));
        }
        assertThrows(IOException.class, () -> protocol().respond(wire(request("HEARTBEAT", 1)), NOW, 1001));
    }

    @Test public void badSchemasAndVersions() {
        for (Object version : new Object[]{0, 2, true, "1", 1.0}) {
            Map<String, Object> value = request("HELLO", 0);
            value.put("protocol_version", version);
            assertThrows(IOException.class, () -> protocol().respond(wire(value), NOW, 1001));
        }
        Map<String, Object> value = request("SHELL", 0);
        assertThrows(IOException.class, () -> protocol().respond(wire(value), NOW, 1001));
        value.put("operation", "HELLO");
        value.put("path", "/private");
        assertThrows(IOException.class, () -> protocol().respond(wire(value), NOW, 1001));
    }

    @Test public void hostileJson() {
        for (String raw : new String[]{"{\"x\":null,\"x\":1}", "{\"x\":NaN}", "{\"x\":1e999}",
            "{\"x\":\"\\ud800\"}", "{\"x\":[[[[[[]]]]]]}", "{}{}", "{x:1}", "{\"x\":01}"}) {
            assertThrows(IOException.class, () -> ControlProtocol.parse(raw.getBytes(StandardCharsets.UTF_8)));
        }
        assertThrows(IOException.class, () -> ControlProtocol.parse(new byte[65537]));
        assertThrows(IOException.class, () -> ControlProtocol.parse(new byte[]{(byte) 255}));
    }

    @Test public void timeAndSessionExpiry() {
        assertThrows(IOException.class, () -> protocol().respond(wire(request("HELLO", 0)), NOW.plusSeconds(30), 1001));
        assertThrows(IOException.class, () -> protocol().respond(wire(request("HELLO", 0)), NOW.minusSeconds(1), 1001));
        assertThrows(IOException.class, () -> protocol().respond(wire(request("HELLO", 0)), NOW, 999));
        assertThrows(IOException.class, () -> protocol().respond(wire(request("HELLO", 0)), NOW, 900_000_001_000L));
    }

    private static String hex(byte[] bytes) {
        StringBuilder sb = new StringBuilder();
        for (byte b : bytes) sb.append(String.format(java.util.Locale.ROOT, "%02x", b & 0xff));
        return sb.toString();
    }
    private static byte[] hmac(byte[] key, String prefix, byte[] payload) throws Exception {
        javax.crypto.Mac mac = javax.crypto.Mac.getInstance("HmacSHA256");
        mac.init(new javax.crypto.spec.SecretKeySpec(key, "HmacSHA256"));
        mac.update((prefix + "\0").getBytes(StandardCharsets.US_ASCII));
        return mac.doFinal(payload);
    }

    @Test public void literalGoldenVectorAndHmac() throws Exception {
        String literalRequestJson = "{\"protocol_version\":1,\"probe_session_id\":\"01234567-89ab-4def-8123-456789abcdef\",\"device_epoch\":3,\"binding\":null,\"nonce\":\"0123456789012345678901234567890123456789012\",\"sequence_number\":0,\"issued_at\":\"2026-10-07T12:00:00Z\",\"expires_at\":\"2026-10-07T12:00:30Z\",\"operation\":\"HELLO\"}";
        byte[] key = new byte[32];
        for (int i = 0; i < 32; i++) key[i] = (byte) (i + 1);
        byte[] reqMac = hmac(key, "request", literalRequestJson.getBytes(StandardCharsets.UTF_8));
        assertEquals("c5b088693199230918954638aa46a91283b63f1bcdc9bf55e6e05272847af5c4", hex(reqMac));

        ControlProtocol protocol = protocol();
        byte[] resBytes = protocol.respond(literalRequestJson.getBytes(StandardCharsets.UTF_8), NOW, 1001);
        String literalResponseJson = "{\"protocol_version\":1,\"probe_session_id\":\"01234567-89ab-4def-8123-456789abcdef\",\"device_epoch\":3,\"binding\":null,\"nonce\":\"0123456789012345678901234567890123456789012\",\"sequence_number\":0,\"issued_at\":\"2026-10-07T12:00:00Z\",\"expires_at\":\"2026-10-07T12:00:30Z\",\"operation\":\"HELLO\",\"status\":\"OK\",\"probe_build\":null,\"hello\":{\"application_version\":\"0.1.0\",\"version_code\":1,\"protocol_versions\":[1],\"supported_operations\":[\"HELLO\",\"GET_CAPABILITIES\",\"HEARTBEAT\"],\"api_level\":26},\"observations\":[],\"capabilities\":[]}";
        assertEquals(literalResponseJson, new String(resBytes, StandardCharsets.UTF_8));

        Map<String, Object> res = ControlProtocol.parse(resBytes);
        assertEquals("OK", res.get("status"));
        assertNull(res.get("probe_build"));
        assertNotNull(res.get("hello"));

        byte[] resMac = hmac(key, "response", resBytes);
        assertEquals("0257b677dd2f7cb049206292c0b4688e3e92d55d1b06003a10045a82f20a79a5", hex(resMac));
    }
}
