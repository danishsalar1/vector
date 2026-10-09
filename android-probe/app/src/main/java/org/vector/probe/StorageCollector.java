package org.vector.probe;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * One worker maximum; app-private filesystem I/O self-check only, never silicon flash durability.
 * Performs explicit FileDescriptor sync before reading back. Physical cache eviction cannot
 * be guaranteed across all Android devices and kernel configurations.
 */
final class StorageCollector implements AutoCloseable, Runnable {
    private static final AtomicBoolean BUSY = new AtomicBoolean();
    private final DiagnosticController c;
    private final DiagnosticJob job;
    private final File file;
    private volatile boolean cancelled;

    interface StorageIoHook {
        default void onBeforeWrite(File file) throws IOException { }
        void onBeforeRead(File file) throws IOException;
    }
    static volatile StorageIoHook testIoHook = null;

    static boolean cleanAbandoned(File directory) {
        if (BUSY.get()) return true;
        File[] files = directory.listFiles((dir, name) -> name.matches("vector-io-[0-9]+\\.tmp"));
        if (files == null || files.length > 256) return false;
        for (File item : files) {
            if (item.isFile() && !java.nio.file.Files.isSymbolicLink(item.toPath()) && !item.delete()) {
                return false;
            }
        }
        return true;
    }

    private StorageCollector(DiagnosticController c, DiagnosticJob job, File file) {
        this.c = c;
        this.job = job;
        this.file = file;
    }

    static void start(DiagnosticController c, DiagnosticJob job) throws IOException {
        if (!cleanAbandoned(c.activity.getCacheDir())) {
            c.finish(job, "ERROR", "CLEANUP_ERROR");
            return;
        }
        if (!BUSY.compareAndSet(false, true)) {
            c.finish(job, "INCONCLUSIVE", "RESOURCE_BUSY");
            return;
        }
        File file = null;
        try {
            file = File.createTempFile("vector-io-", ".tmp", c.activity.getCacheDir());
            StorageCollector collector = new StorageCollector(c, job, file);
            if (!c.own(job, collector)) {
                BUSY.set(false);
                if (file.exists() && !file.delete()) throw new IOException("Storage cleanup failed");
                return;
            }
            Thread worker = new Thread(collector, "vector-storage-check");
            worker.setDaemon(true);
            worker.start();
        } catch (IOException | RuntimeException error) {
            BUSY.set(false);
            if (file != null && file.exists() && !file.delete()) throw new IOException("Storage cleanup failed");
            throw error;
        }
    }

    @Override
    public void run() {
        byte[] expected = new byte[65536];
        byte[] actual = new byte[65536];
        try {
            new SecureRandom().nextBytes(expected);
            if (cancelled || !c.current(job)) return;

            // Optional test hook for injecting write/read faults or corruption
            StorageIoHook hook = testIoHook;

            // 1. Write block and flush with descriptor sync
            try (FileOutputStream out = new FileOutputStream(file)) {
                if (hook != null) hook.onBeforeWrite(file);
                out.write(expected);
                out.getFD().sync();
            } catch (IOException writeError) {
                if (!cancelled && c.current(job)) c.finish(job, "ERROR", "WRITE_ERROR");
                return;
            }
            job.metric("bytes_written", expected.length, "bytes");

            if (cancelled || !c.current(job)) return;

            if (hook != null) {
                hook.onBeforeRead(file);
            }

            // 2. Reopen via fresh input stream for readback verification
            int offset = 0;
            try (FileInputStream in = new FileInputStream(file)) {
                while (offset < actual.length && !cancelled && c.current(job)) {
                    int read = in.read(actual, offset, actual.length - offset);
                    if (read < 0) break;
                    offset += read;
                }
            } catch (IOException readError) {
                if (!cancelled && c.current(job)) c.finish(job, "ERROR", "READ_ERROR");
                return;
            }

            if (cancelled || !c.current(job)) return;
            job.metric("bytes_read", offset, "bytes");

            boolean equal = offset == expected.length && file.length() == expected.length && Arrays.equals(expected, actual);
            job.metric("readback_match", equal ? 1 : 0, "boolean");
            c.finish(job, equal ? "PASS" : "FAIL", equal ? "READBACK_MATCH" : "READBACK_MISMATCH");
        } catch (IOException error) {
            if (!cancelled && c.current(job)) c.finish(job, "ERROR", "READ_ERROR");
        } finally {
            Arrays.fill(expected, (byte) 0);
            Arrays.fill(actual, (byte) 0);
            // Early best-effort delete; close() (run by the controller before any terminal
            // state is published) is the authoritative check and reports a leftover file.
            cleanupFile();
            BUSY.set(false);
        }
    }

    /** True when no temporary file remains. */
    private synchronized boolean cleanupFile() {
        return !file.exists() || file.delete() || !file.exists();
    }

    @Override
    public void close() throws IOException {
        cancelled = true;
        if (!cleanupFile()) throw new IOException("Storage temporary file could not be deleted.");
    }
}
