package org.vector.probe;

import static org.junit.Assert.*;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.Test;

public final class DiagnosticJobTest {
    static Map<String, Object> binding(String challenge) {
        Map<String, Object> b = new LinkedHashMap<>();
        b.put("diagnostic_id", "touch"); b.put("challenge_id", challenge); b.put("attempt_id", "attempt");
        b.put("scan_id", "scan"); b.put("collection_not_before", "2026-10-08T00:00:00Z"); return b;
    }
    static Object metric(DiagnosticJob job, String name) {
        for (Object item : (List<?>) job.snapshot(0).get("metrics")) {
            Map<?, ?> map = (Map<?, ?>) item;
            if (name.equals(map.get("name"))) return map.get("value");
        }
        throw new AssertionError("metric " + name + " missing");
    }
    @Test public void partialGridAndSequentialTouchesCannotClaimMultitouch() {
        DiagnosticJob.Touch touch = new DiagnosticJob.Touch();
        touch.observe(5, 5, 400, 600, 1); touch.observe(5, 5, 400, 600, 1);
        touch.observe(105, 5, 400, 600, 1);
        assertEquals(2, touch.count); assertEquals(1, touch.simultaneous);
        for (int y = 0; y < 6; y++) for (int x = 0; x < 4; x++) touch.observe(x * 100 + 50, y * 100 + 50, 400, 600, 1);
        assertEquals(24, touch.count); assertEquals(1, touch.simultaneous);
        touch.observe(50, 50, 400, 600, 2); assertEquals(2, touch.simultaneous);
    }
    @Test public void malformedOrOutsideTouchesDoNotCount() {
        DiagnosticJob.Touch t = new DiagnosticJob.Touch();
        for (float x : new float[]{-1, 400, Float.NaN, Float.POSITIVE_INFINITY}) t.observe(x, 1, 400, 600, 2);
        t.observe(1, 600, 400, 600, 2); t.observe(1, 1, 0, 600, 2); t.observe(1, 1, 400, 600, 0);
        assertEquals(0, t.count); assertEquals(0, t.simultaneous);
    }
    @Test public void constantSamplesAreObservationsAndInvalidSamplesAreDiscarded() {
        DiagnosticJob.Samples samples = new DiagnosticJob.Samples(3);
        samples.add(new float[]{1, 2, 3}); samples.add(new float[]{1, 2, 3});
        samples.add(new float[]{Float.NaN, 2, 3}); samples.add(new float[]{1});
        assertEquals(2, samples.count); assertEquals(2, samples.rejected);
        assertArrayEquals(new double[]{1, 2, 3}, samples.min, 0);
        assertArrayEquals(samples.min, samples.max, 0);
        DiagnosticJob j = new DiagnosticJob(binding("a"), 0); samples.write(j, "m_s2");
        assertEquals("INCONCLUSIVE", j.snapshot(100).get("outcome"));
        assertEquals(2, metric(j, "rejected_samples"));
        for (int i = 0; i < 5000; i++) samples.add(new float[]{2, 3, 4}); assertEquals(4096, samples.count);
    }
    @Test public void samplesOutsideTheDesktopNumericContractAreExcludedAndCounted() {
        DiagnosticJob.Samples samples = new DiagnosticJob.Samples(3);
        samples.add(new float[]{1e20f, 0, 0});
        samples.add(new float[]{0, -Float.MAX_VALUE, 0});
        samples.add(new float[]{9007199254740992f, 1, 1}); // exactly 2^53 is inside the contract
        samples.add(null);
        assertEquals(1, samples.count); assertEquals(3, samples.rejected);
        DiagnosticJob j = new DiagnosticJob(binding("a"), 0); samples.write(j, "m_s2");
        assertEquals(9007199254740992.0, ((Number) metric(j, "axis0_max")).doubleValue(), 0);
        assertEquals(3, metric(j, "rejected_samples"));
    }
    @Test public void zeroSamplesRetainNullInsteadOfFabricatingZero() {
        DiagnosticJob j = new DiagnosticJob(binding("a"), 0);
        new DiagnosticJob.Samples(1).write(j, "lux");
        assertEquals(0, metric(j, "sample_count"));
        assertEquals(0, metric(j, "rejected_samples"));
        assertNull(metric(j, "axis0_min")); assertNull(metric(j, "axis0_mean"));
    }
    @Test public void cancellationMakesLatePassAndMetricsIneffective() {
        DiagnosticJob j = new DiagnosticJob(binding("a"), 100);
        j.metric("touch_cells", 10, "count"); j.cancel(false, 200);
        Map<String, Object> cancelled = j.snapshot(1000);
        j.metric("touch_cells", 24, "count"); j.finish("PASS", "TOUCH_COVERED", 300);
        assertEquals(cancelled, j.snapshot(2000)); assertEquals("CANCELLED", cancelled.get("state"));
        assertEquals("INCONCLUSIVE", cancelled.get("outcome")); assertEquals(100L, cancelled.get("elapsed_ms"));
    }
    @Test public void expiryNeverBecomesFailureOrPass() {
        DiagnosticJob j = new DiagnosticJob(binding("a"), 0); j.cancel(true, 70000);
        assertEquals("EXPIRED", j.snapshot(90000).get("state"));
        assertEquals("INCONCLUSIVE", j.snapshot(90000).get("outcome")); assertEquals(60000L, j.snapshot(90000).get("elapsed_ms"));
    }
    @Test public void stopFreezesEvidenceAndReportsStoppingUntilReleased() {
        DiagnosticJob j = new DiagnosticJob(binding("a"), 100);
        j.metric("touch_cells", 10, "count");
        assertTrue(j.stop(false)); assertFalse(j.running()); assertFalse(j.stop(true));
        Map<String, Object> stopping = j.snapshot(400);
        assertEquals("RUNNING", stopping.get("state")); assertEquals("INCONCLUSIVE", stopping.get("outcome"));
        assertEquals("STOPPING", stopping.get("reason")); assertEquals(300L, stopping.get("elapsed_ms"));
        j.metric("touch_cells", 24, "count"); j.finish("PASS", "TOUCH_COVERED", 500);
        assertEquals("STOPPING", j.snapshot(600).get("reason")); assertEquals(10, metric(j, "touch_cells"));
        j.stopped(true, 700);
        Map<String, Object> done = j.snapshot(900);
        assertEquals("CANCELLED", done.get("state")); assertEquals("INCONCLUSIVE", done.get("outcome"));
        assertEquals("CANCELLED", done.get("reason")); assertEquals(600L, done.get("elapsed_ms"));
        assertEquals(stopping.get("metrics"), done.get("metrics"));
    }
    @Test public void cleanupFailureAfterStopIsReportedNotDropped() {
        DiagnosticJob cancelled = new DiagnosticJob(binding("a"), 0);
        cancelled.stop(false); cancelled.stopped(false, 50);
        Map<String, Object> c = cancelled.snapshot(100);
        assertEquals("CANCELLED", c.get("state")); assertEquals("ERROR", c.get("outcome")); assertEquals("CLEANUP_ERROR", c.get("reason"));
        DiagnosticJob expired = new DiagnosticJob(binding("b"), 0);
        expired.stop(true); expired.stopped(false, 60000);
        Map<String, Object> e = expired.snapshot(70000);
        assertEquals("EXPIRED", e.get("state")); assertEquals("ERROR", e.get("outcome")); assertEquals("CLEANUP_ERROR", e.get("reason"));
        expired.stopped(true, 70000); // terminal: a second report cannot rewrite history
        assertEquals(e, expired.snapshot(80000));
    }
    @Test public void completedResultIsImmutableAcrossLaterStopAndCleanup() {
        DiagnosticJob j = new DiagnosticJob(binding("a"), 0);
        j.finish("PASS", "TOUCH_COVERED", 100);
        Map<String, Object> done = j.snapshot(200);
        assertFalse(j.stop(false)); j.stopped(false, 300); j.cancel(true, 400);
        assertEquals(done, j.snapshot(500));
        assertEquals("COMPLETED", done.get("state")); assertEquals("PASS", done.get("outcome"));
    }
    @Test public void sessionCloseDuringStopKeepsTheStopKind() {
        DiagnosticJob j = new DiagnosticJob(binding("a"), 0);
        j.stop(true); j.cancel(false, 10);
        assertEquals("EXPIRED", j.snapshot(20).get("state")); assertEquals("TIMEOUT", j.snapshot(20).get("reason"));
    }
    @Test public void repeatedStartStaleBindingAndClosedSessionAreRejected() {
        DiagnosticSession session = new DiagnosticSession();
        DiagnosticJob a = session.start(binding("a"), 0);
        assertNull(session.start(binding("b"), 1)); assertNull(session.lookup(binding("b")));
        a.finish("INCONCLUSIVE", "PARTIAL", 2);
        assertNull(session.start(binding("a"), 3));
        DiagnosticJob b = session.start(binding("b"), 4);
        assertFalse(session.current(a)); assertNull(session.lookup(binding("a"))); assertTrue(session.current(b));
        session.close(5); assertFalse(session.current(b)); assertNull(session.lookup(binding("b"))); assertNull(session.start(binding("c"), 6));
    }
    @Test public void allBindingFieldsAreOwned() {
        DiagnosticSession session = new DiagnosticSession(); session.start(binding("a"), 0);
        for (String key : binding("a").keySet()) {
            Map<String, Object> other = binding("a"); other.put(key, "different"); assertNull(session.lookup(other));
        }
    }
    @Test public void independentSessionsAndBoundedHistory() {
        DiagnosticSession a = new DiagnosticSession(), b = new DiagnosticSession();
        DiagnosticJob other = b.start(binding("other"), 0);
        for (int i = 0; i < 256; i++) {
            DiagnosticJob job = a.start(binding(Integer.toString(i)), i); assertNotNull(job); job.cancel(false, i);
        }
        assertNull(a.start(binding("overflow"), 257)); assertTrue(a.isExhausted());
        assertTrue(b.current(other)); a.close(300); assertTrue(b.current(other));
    }
    @Test public void missingTelemetryAndMetricBoundsArePreserved() {
        DiagnosticJob j = new DiagnosticJob(binding("a"), 0);
        j.metric("battery_voltage", null, "mV"); j.metric("battery_temperature", Double.NaN, "deci_celsius");
        List<?> metrics = (List<?>) j.snapshot(1).get("metrics");
        assertNull(((Map<?, ?>) metrics.get(0)).get("value")); assertNull(((Map<?, ?>) metrics.get(1)).get("value"));
        for (int i = 2; i < 64; i++) j.metric("bounded" + i, i, "count");
        assertThrows(IllegalStateException.class, () -> j.metric("overflow", 1, "count"));
    }
    @Test public void touchCoverageGeometryCalculations() {
        DiagnosticJob.Touch touch = new DiagnosticJob.Touch();
        touch.observe(50, 50, 400, 600, 1);
        assertEquals(400, touch.testedWidth);
        assertEquals(600, touch.testedHeight);
        assertEquals(1, touch.count);
        assertEquals(4L, touch.cellCoveragePercent()); // round(1 * 100 / 24) = 4
        for (int y = 0; y < 6; y++) for (int x = 0; x < 4; x++) touch.observe(x * 100 + 50, y * 100 + 50, 400, 600, 1);
        assertEquals(24, touch.count);
        assertEquals(100L, touch.cellCoveragePercent());
    }

    // ---- TG-01: geometry rules, each isolated (mirrors the desktop validator literals) ----

    static DiagnosticJob.Touch grid(int tw, int th, int ww, int wh, int dw, int dh, int cells, int contacts, int gen) {
        DiagnosticJob.Touch touch = new DiagnosticJob.Touch();
        touch.reset(tw, th, ww, wh, dw, dh, gen);
        for (int cell = 0; cell < cells; cell++) {
            touch.observe(tw * (2 * (cell % 4) + 1) / 8f, th * (2 * (cell / 4) + 1) / 12f, tw, th, 1);
        }
        if (contacts > 1) touch.observe(1, 1, tw, th, contacts);
        if (contacts == 0) touch.simultaneous = 0;
        return touch;
    }
    @Test public void areaPercentRoundsHalfUpInExactIntegersLikeTheDesktop() {
        assertEquals(Long.valueOf(94), DiagnosticJob.Touch.areaPercent(1080, 2200, 1080, 2340));
        assertEquals(Long.valueOf(92), DiagnosticJob.Touch.areaPercent(1080, 2200, 1080, 2400));
        assertEquals(Long.valueOf(38), DiagnosticJob.Touch.areaPercent(1, 3, 2, 4));
        assertEquals(Long.valueOf(50), DiagnosticJob.Touch.areaPercent(1, 1, 2, 1));
        assertEquals(Long.valueOf(2), DiagnosticJob.Touch.areaPercent(200, 200, 1080, 2400));
        assertEquals(Long.valueOf(100), DiagnosticJob.Touch.areaPercent(2000, 2000, 1000, 1000));
        assertNull(DiagnosticJob.Touch.areaPercent(1080, 2200, 0, 2400));
    }
    @Test public void fullCoverageOfAConsistentFullScreenGridIsCovered() {
        DiagnosticJob.Touch touch = grid(1080, 2200, 1080, 2340, 1080, 2400, 24, 2, 1);
        assertTrue(touch.isValidGeometry()); assertTrue(touch.covered());
        assertEquals(Long.valueOf(94), touch.testedWindowAreaPercent());
        assertEquals(Long.valueOf(92), touch.testedDisplayAreaPercent());
    }
    @Test public void eachGeometryRuleAloneBlocksCoverage() {
        int[][] cases = {
            {199, 2400, 199, 2400, 199, 2400},   // below the 200 px minimum width, 100% of display
            {1080, 199, 1080, 199, 1080, 199},   // below the 200 px minimum height
            {1080, 2200, 0, 0, 1080, 2400},      // app window unknown
            {1080, 2200, 1080, 2340, 0, 0},      // display unknown
            {1100, 2000, 1080, 2340, 1100, 2400},// grid wider than its window (83% of display)
            {1000, 2000, 1100, 2340, 1080, 2400},// window wider than the display (77% of display)
            {1080, 1150, 1080, 1170, 1080, 2400} // split screen: 98% of window, 48% of display
        };
        for (int[] c : cases) {
            DiagnosticJob.Touch touch = grid(c[0], c[1], c[2], c[3], c[4], c[5], 24, 2, 1);
            assertEquals("all cells observed for " + java.util.Arrays.toString(c), 24, touch.count);
            assertFalse("geometry must be rejected: " + java.util.Arrays.toString(c), touch.isValidGeometry());
            assertFalse(touch.covered());
        }
    }
    @Test public void incompleteCoverageNoContactOrNoLayoutBlocksCoverage() {
        assertFalse(grid(1080, 2200, 1080, 2340, 1080, 2400, 23, 1, 1).covered());
        assertFalse(grid(1080, 2200, 1080, 2340, 1080, 2400, 24, 0, 1).covered());
        assertFalse(grid(1080, 2200, 1080, 2340, 1080, 2400, 24, 1, 0).covered());
        assertTrue(grid(1080, 2200, 1080, 2340, 1080, 2400, 24, 1, 1).covered());
    }
    @Test public void touchesFromADifferentLayoutSizeNeverCount() {
        DiagnosticJob.Touch touch = new DiagnosticJob.Touch();
        touch.reset(400, 600, 400, 600, 400, 600, 1);
        touch.observe(50, 50, 800, 1200, 1);
        assertEquals(0, touch.count); assertEquals(400, touch.testedWidth);
        touch.observe(50, 50, 400, 600, 1);
        assertEquals(1, touch.count);
    }
}
