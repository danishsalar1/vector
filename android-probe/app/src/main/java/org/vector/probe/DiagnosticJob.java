package org.vector.probe;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Pure state/evidence model. One immutable binding, bounded metrics, no raw content. */
final class DiagnosticJob {
    final Map<String, Object> binding;
    final String id;
    final long started;
    private String state = "RUNNING";
    private String outcome = "INCONCLUSIVE";
    private String reason = "COLLECTING";
    private boolean stopping;
    private boolean stopTimeout;
    private final Map<String, Map<String, Object>> metrics = new LinkedHashMap<>();
    private long elapsed;

    DiagnosticJob(Map<String, Object> binding, long now) {
        this.binding = new LinkedHashMap<>(binding);
        id = (String) binding.get("diagnostic_id");
        started = now;
    }

    /** Collecting: only now may metrics change or a conclusion be recorded. */
    synchronized boolean running() { return state.equals("RUNNING") && !stopping; }
    synchronized void metric(String name, Number value, String unit) {
        if (!running()) return;
        if (value != null && !Double.isFinite(value.doubleValue())) value = null;
        if (!metrics.containsKey(name) && metrics.size() >= 64) throw new IllegalStateException("Metric bound");
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("name", name); item.put("value", value); item.put("unit", unit);
        metrics.put(name, item);
    }
    synchronized void finish(String result, String why, long now) {
        if (!running()) return;
        state = "COMPLETED"; outcome = result; reason = why;
        elapsed = clamp(now - started);
    }
    /**
     * Cancellation accepted. Evidence freezes and the job reports RUNNING/STOPPING until its
     * owner has released resources and calls {@link #stopped}. False when no longer collecting.
     */
    synchronized boolean stop(boolean timeout) {
        if (!running()) return false;
        stopping = true; stopTimeout = timeout; reason = "STOPPING";
        return true;
    }
    /** Terminal state after a stop: a clean interruption, or a truthful cleanup failure. */
    synchronized void stopped(boolean released, long now) {
        if (stopping && state.equals("RUNNING")) terminate(stopTimeout, released, now);
    }
    /** Immediate interruption when the session closes; nothing can observe the cleanup. */
    synchronized void cancel(boolean timeout, long now) {
        if (state.equals("RUNNING")) terminate(stopping ? stopTimeout : timeout, true, now);
    }
    private void terminate(boolean timeout, boolean released, long now) {
        state = timeout ? "EXPIRED" : "CANCELLED";
        outcome = released ? "INCONCLUSIVE" : "ERROR";
        reason = released ? (timeout ? "TIMEOUT" : "CANCELLED") : "CLEANUP_ERROR";
        elapsed = clamp(now - started);
    }
    private long clamp(long value) { return Math.max(0, Math.min(60000, value)); }
    synchronized Map<String, Object> snapshot(long now) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("schema_version", 1); result.put("diagnostic_id", id);
        result.put("state", state); result.put("outcome", outcome); result.put("reason", reason);
        result.put("elapsed_ms", state.equals("RUNNING") ? clamp(now - started) : elapsed);
        result.put("metrics", new ArrayList<>(metrics.values()));
        return result;
    }

    /**
     * Fixed 4x6 grid covering the full tested rectangle. Only direct in-bounds touch observations
     * count. The window is the app window hosting the grid and the display is the physical display
     * in the current rotation; PASS needs the grid to cover most of the display, not only of the
     * window. Mirrored exactly by the desktop validator (probe_diagnostics._touch_pass_evidence).
     */
    static final class Touch {
        static final int CELLS = 24;
        static final int MIN_TESTED_PIXELS = 200;
        static final int MIN_DISPLAY_AREA_PERCENT = 75;
        private final boolean[] cells = new boolean[CELLS];
        int count;
        int simultaneous;
        int testedWidth;
        int testedHeight;
        int windowWidth;
        int windowHeight;
        int displayWidth;
        int displayHeight;
        int layoutGeneration;

        void reset(int w, int h, int winW, int winH, int dispW, int dispH, int gen) {
            java.util.Arrays.fill(cells, false);
            count = 0;
            simultaneous = 0;
            testedWidth = w;
            testedHeight = h;
            windowWidth = winW;
            windowHeight = winH;
            displayWidth = dispW;
            displayHeight = dispH;
            layoutGeneration = gen;
        }

        void observe(float x, float y, int width, int height, int pointers) {
            if (!Float.isFinite(x) || !Float.isFinite(y) || width <= 0 || height <= 0
                    || x < 0 || y < 0 || x >= width || y >= height || pointers < 1) return;
            // Cells belong to one layout; a size the last reset did not record never counts.
            if (testedWidth > 0 && (width != testedWidth || height != testedHeight)) return;
            testedWidth = width;
            testedHeight = height;
            int cell = ((int) (y * 6 / height)) * 4 + (int) (x * 4 / width);
            if (!cells[cell]) { cells[cell] = true; count++; }
            simultaneous = Math.max(simultaneous, Math.min(32, pointers));
        }
        boolean visited(int index) { return cells[index]; }
        long cellCoveragePercent() { return roundedPercent(count, CELLS); }
        /** Round-half-up area percentage in exact integers, capped to the wire range; null if unknown. */
        static Long areaPercent(int width, int height, int outerWidth, int outerHeight) {
            if (width <= 0 || height <= 0 || outerWidth <= 0 || outerHeight <= 0) return null;
            return Math.min(100L, roundedPercent((long) width * height, (long) outerWidth * outerHeight));
        }
        private static long roundedPercent(long part, long whole) { return (200L * part + whole) / (2L * whole); }
        Long testedWindowAreaPercent() { return areaPercent(testedWidth, testedHeight, windowWidth, windowHeight); }
        Long testedDisplayAreaPercent() { return areaPercent(testedWidth, testedHeight, displayWidth, displayHeight); }
        boolean isValidGeometry() {
            Long displayArea = testedDisplayAreaPercent();
            return testedWidth >= MIN_TESTED_PIXELS && testedHeight >= MIN_TESTED_PIXELS
                    && windowWidth > 0 && windowHeight > 0
                    && testedWidth <= windowWidth && windowWidth <= displayWidth
                    && testedHeight <= windowHeight && windowHeight <= displayHeight
                    && displayArea != null && displayArea >= MIN_DISPLAY_AREA_PERCENT;
        }
        /** PASS predicate: every cell, at least one contact, a measured layout and valid geometry. */
        boolean covered() {
            return count == CELLS && simultaneous >= 1 && layoutGeneration >= 1 && isValidGeometry();
        }
    }

    /** Streaming bounded summaries; never retains sensor/audio samples. */
    static final class Samples {
        /** 2^53: largest magnitude the desktop accepts for a numeric observation. */
        static final double MAX_MAGNITUDE = 9007199254740992.0;
        final double[] min, max, sum;
        int count;
        int rejected;
        Samples(int dimensions) {
            min = new double[dimensions]; max = new double[dimensions]; sum = new double[dimensions];
            java.util.Arrays.fill(min, Double.POSITIVE_INFINITY);
            java.util.Arrays.fill(max, Double.NEGATIVE_INFINITY);
        }
        /** Malformed, non-finite or out-of-contract samples are excluded and counted, never summarized. */
        void add(float[] values) {
            if (count >= 4096) return;
            boolean valid = values != null && values.length >= min.length;
            for (int i = 0; valid && i < min.length; i++) {
                valid = Float.isFinite(values[i]) && Math.abs((double) values[i]) <= MAX_MAGNITUDE;
            }
            if (!valid) { if (rejected < Integer.MAX_VALUE) rejected++; return; }
            for (int i = 0; i < min.length; i++) {
                min[i] = Math.min(min[i], values[i]); max[i] = Math.max(max[i], values[i]); sum[i] += values[i];
            }
            count++;
        }
        void write(DiagnosticJob job, String unit) {
            job.metric("sample_count", count, "count");
            job.metric("rejected_samples", rejected, "count");
            for (int i = 0; i < min.length; i++) {
                job.metric("axis" + i + "_min", count == 0 ? null : min[i], unit);
                job.metric("axis" + i + "_max", count == 0 ? null : max[i], unit);
                job.metric("axis" + i + "_mean", count == 0 ? null : sum[i] / count, unit);
            }
        }
    }
}
