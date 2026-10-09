package org.vector.probe;

import java.util.HashSet;
import java.util.Map;
import java.util.Set;

/** JVM-testable ownership gate. No work or callback survives invalidation. */
final class DiagnosticSession {
    private final Set<Object> used = new HashSet<>();
    private DiagnosticJob active;
    private boolean closed;
    synchronized boolean isExhausted() { return used.size() >= 256; }
    synchronized DiagnosticJob start(Map<String, Object> binding, long now) {
        if (closed || (active != null && active.running()) || used.size() >= 256 || !used.add(binding.get("challenge_id"))) return null;
        active = new DiagnosticJob(binding, now); return active;
    }
    synchronized DiagnosticJob lookup(Map<String, Object> binding) {
        return !closed && active != null && active.binding.equals(binding) ? active : null;
    }
    synchronized boolean current(DiagnosticJob job) { return !closed && active == job && job.running(); }
    synchronized void close(long now) { closed = true; if (active != null) active.cancel(false, now); used.clear(); }
}
