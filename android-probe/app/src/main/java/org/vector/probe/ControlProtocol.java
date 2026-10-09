package org.vector.probe;

import com.google.gson.GsonBuilder;
import com.google.gson.Strictness;
import com.google.gson.stream.JsonReader;
import com.google.gson.stream.JsonToken;
import java.io.IOException;
import java.io.StringReader;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** Pure JVM control protocol. No Android diagnostics, arbitrary inputs or verdicts. */
final class ControlProtocol {
    static final int MAX_BYTES = 65536;
    private static Set<String> names(String... values) { return new HashSet<>(Arrays.asList(values)); }
    private static final Set<String> FIELDS = names("protocol_version", "probe_session_id",
        "device_epoch", "binding", "nonce", "sequence_number", "issued_at", "expires_at", "operation");
    private static final Set<String> OPS = names("HELLO", "GET_CAPABILITIES", "HEARTBEAT",
        "START_CHALLENGE", "CANCEL_CHALLENGE", "FETCH_OBSERVATIONS");
    private static final String UUID = "[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}";
    private final long startedNanos;
    private final int apiLevel;
    interface Diagnostics {
        List<Map<String, Object>> capabilities();
        Map<String, Object> command(String operation, Map<String, Object> binding);
        default boolean isExhausted() { return false; }
    }
    private final Diagnostics diagnostics;
    private Instant lastWall;
    private String session;
    private long epoch;
    private long sequence = -1;
    private final Set<String> nonces = new HashSet<>();

    ControlProtocol(Instant now, long nanoTime, int apiLevel) {
        this(now, nanoTime, apiLevel, null);
    }
    ControlProtocol(Instant now, long nanoTime, int apiLevel, Diagnostics diagnostics) {
        lastWall = now;
        startedNanos = nanoTime;
        this.apiLevel = apiLevel;
        this.diagnostics = diagnostics;
    }

    static IOException rejected() { return new IOException("Probe control message rejected."); }

    private static String string(Object value, String pattern) throws IOException {
        if (!(value instanceof String) || !((String) value).matches(pattern)) throw rejected();
        return (String) value;
    }

    private static long integer(Object value) throws IOException {
        if (!(value instanceof Long) || ((Long) value) < 0) throw rejected();
        return (Long) value;
    }

    private static Instant timestamp(Object value) throws IOException {
        try {
            OffsetDateTime time = OffsetDateTime.parse(string(value, ".{1,64}"));
            if (time.getOffset().getTotalSeconds() != 0) throw rejected();
            return time.toInstant();
        } catch (RuntimeException error) { throw rejected(); }
    }

    synchronized byte[] respond(byte[] raw, Instant now, long nanoTime) throws IOException {
        try {
            Map<String, Object> request = parse(raw);
            int version = diagnostics == null ? 1 : 2;
            if (!request.keySet().equals(FIELDS) || integer(request.get("protocol_version")) != version) throw rejected();
            String owner = string(request.get("probe_session_id"), UUID);
            long ownerEpoch = integer(request.get("device_epoch"));
            long next = integer(request.get("sequence_number"));
            String nonce = string(request.get("nonce"), "[A-Za-z0-9_-]{43}");
            String operation = string(request.get("operation"), "[A-Z_]{1,32}");
            Instant issued = timestamp(request.get("issued_at"));
            Instant expires = timestamp(request.get("expires_at"));
            if (!OPS.contains(operation) || !expires.isAfter(issued)
                    || expires.isAfter(issued.plusSeconds(30)) || !expires.isAfter(now)
                    || issued.isAfter(now.plusSeconds(5)) || now.isBefore(lastWall)
                    || nanoTime < startedNanos || nanoTime - startedNanos >= 900_000_000_000L
                    || next <= sequence || next >= 4096 || nonces.contains(nonce)) throw rejected();
            boolean challenge = operation.equals("START_CHALLENGE") || operation.equals("CANCEL_CHALLENGE")
                || operation.equals("FETCH_OBSERVATIONS");
            Object binding = request.get("binding");
            if (challenge) {
                if (!(binding instanceof Map)) throw rejected();
                Map<?, ?> fields = (Map<?, ?>) binding;
                if (!fields.keySet().equals(names("scan_id", "diagnostic_id", "attempt_id", "challenge_id", "collection_not_before"))) throw rejected();
                string(fields.get("scan_id"), UUID);
                string(fields.get("attempt_id"), UUID);
                string(fields.get("challenge_id"), UUID);
                string(fields.get("diagnostic_id"), "[a-z][a-z0-9_]{0,63}");
                if (timestamp(fields.get("collection_not_before")).isAfter(issued)) throw rejected();
            } else if (binding != null) throw rejected();
            if (session == null) {
                if (!operation.equals("HELLO") || next != 0) throw rejected();
            } else if (!session.equals(owner) || epoch != ownerEpoch || operation.equals("HELLO")) throw rejected();
            session = owner;
            epoch = ownerEpoch;
            sequence = next;
            nonces.add(nonce);
            lastWall = now;
            Map<String, Object> response = new LinkedHashMap<>(request);
            // Echo request timestamps: device clock never extends the desktop deadline.
            response.put("status", challenge ? "UNAVAILABLE" : "OK");
            if (diagnostics != null) {
                response.put("diagnostic_capabilities", operation.equals("GET_CAPABILITIES") ? diagnostics.capabilities() : new ArrayList<>());
                Map<String, Object> report = null;
                if (challenge) {
                    Map<String, Object> safeBinding = new LinkedHashMap<>();
                    for (Map.Entry<?, ?> entry : ((Map<?, ?>) binding).entrySet()) safeBinding.put((String) entry.getKey(), entry.getValue());
                    report = diagnostics.command(operation, safeBinding);
                    if (report == null) {
                        // Exhaustion only ever refuses a START; a stale FETCH/CANCEL is merely unavailable.
                        boolean exhausted = operation.equals("START_CHALLENGE") && diagnostics.isExhausted();
                        response.put("status", exhausted ? "ERROR" : "UNAVAILABLE");
                    } else {
                        response.put("status", "OK");
                    }
                }
                response.put("diagnostic", report);
            }
            response.put("probe_build", null);
            if (operation.equals("HELLO")) {
                Map<String, Object> hello = new LinkedHashMap<>();
                hello.put("application_version", version == 1 ? "0.1.0" : BuildConfig.VERSION_NAME);
                hello.put("version_code", version == 1 ? 1 : BuildConfig.VERSION_CODE);
                hello.put("protocol_versions", Arrays.asList(version));
                hello.put("supported_operations", version == 1 ? Arrays.asList("HELLO", "GET_CAPABILITIES", "HEARTBEAT") : Arrays.asList("HELLO", "GET_CAPABILITIES", "HEARTBEAT", "START_CHALLENGE", "CANCEL_CHALLENGE", "FETCH_OBSERVATIONS"));
                hello.put("api_level", apiLevel);
                response.put("hello", hello);
            }
            response.put("observations", new ArrayList<>());
            Map<String, Object> capability = new LinkedHashMap<>();
            capability.put("capability_id", "CONTROL_CHANNEL");
            capability.put("available", true);
            capability.put("operations", Arrays.asList("HELLO", "GET_CAPABILITIES", "HEARTBEAT"));
            response.put("capabilities", operation.equals("GET_CAPABILITIES")
                ? Arrays.asList(capability) : new ArrayList<>());
            byte[] encoded = new GsonBuilder().serializeNulls().create().toJson(response).getBytes(StandardCharsets.UTF_8);
            if (encoded.length > MAX_BYTES) throw rejected();
            return encoded;
        } catch (RuntimeException error) { throw rejected(); }
    }

    static Map<String, Object> parse(byte[] raw) throws IOException {
        if (raw.length == 0 || raw.length > MAX_BYTES) throw rejected();
        String text = StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(raw)).toString();
        try (JsonReader reader = new JsonReader(new StringReader(text))) {
            reader.setStrictness(Strictness.STRICT);
            if (reader.peek() != JsonToken.BEGIN_OBJECT) throw rejected();
            Map<String, Object> result = object(reader, 1);
            if (reader.peek() != JsonToken.END_DOCUMENT) throw rejected();
            return result;
        } catch (RuntimeException error) { throw rejected(); }
    }

    private static String bounded(String value) throws IOException {
        if (value.length() > 4096) throw rejected();
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            if (Character.isHighSurrogate(c)) {
                if (++i == value.length() || !Character.isLowSurrogate(value.charAt(i))) throw rejected();
            } else if (Character.isLowSurrogate(c)) throw rejected();
        }
        return value;
    }

    private static Map<String, Object> object(JsonReader reader, int depth) throws IOException {
        if (depth > 6) throw rejected();
        reader.beginObject();
        Map<String, Object> result = new LinkedHashMap<>();
        while (reader.hasNext()) {
            String name = bounded(reader.nextName());
            if (result.containsKey(name) || result.size() >= 64) throw rejected();
            result.put(name, value(reader, depth));
        }
        reader.endObject();
        return result;
    }

    private static Object value(JsonReader reader, int depth) throws IOException {
        switch (reader.peek()) {
            case BEGIN_OBJECT: return object(reader, depth + 1);
            case BEGIN_ARRAY:
                if (depth >= 6) throw rejected();
                reader.beginArray();
                List<Object> list = new ArrayList<>();
                while (reader.hasNext()) {
                    if (list.size() >= 256) throw rejected();
                    list.add(value(reader, depth + 1));
                }
                reader.endArray();
                return list;
            case STRING: return bounded(reader.nextString());
            case BOOLEAN: return reader.nextBoolean();
            case NULL: reader.nextNull(); return null;
            case NUMBER:
                String number = reader.nextString();
                // Request schema contains integers only, never floats/coercion.
                if (!number.matches("0|[1-9][0-9]{0,18}")) throw rejected();
                try { return Long.parseLong(number); } catch (NumberFormatException error) { throw rejected(); }
            default: throw rejected();
        }
    }
}
