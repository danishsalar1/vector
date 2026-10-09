package org.vector.probe;

import android.content.Context;
import android.net.LocalServerSocket;
import android.net.LocalSocket;
import android.os.SystemClock;
import android.util.AtomicFile;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Arrays;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

/** One foreground consent, one socket connection, one fresh protocol session. */
final class ProbeServer implements AutoCloseable {
    interface Listener { void state(int resource); }
    private final AtomicFile bootstrap;
    private final Listener listener;
    private final DiagnosticController diagnostics;
    private final byte[] key = new byte[32];
    private final String endpoint;
    private final ScheduledExecutorService deadline = Executors.newSingleThreadScheduledExecutor();
    private LocalServerSocket server;
    private LocalSocket client;
    private boolean closed;
    private boolean expired;
    private Thread worker;

    private synchronized void onExpiry() {
        expired = true;
        close();
    }

    ProbeServer(Context context, Listener listener, DiagnosticController diagnostics) {
        bootstrap = new AtomicFile(new File(context.getFilesDir(), "vector-probe-session"));
        this.listener = listener;
        this.diagnostics = diagnostics;
        SecureRandom random = new SecureRandom();
        random.nextBytes(key);
        byte[] name = new byte[16];
        random.nextBytes(name);
        endpoint = "vector_probe_" + hex(name);
    }

    static String hex(byte[] bytes) {
        StringBuilder text = new StringBuilder(bytes.length * 2);
        for (byte value : bytes) text.append(String.format(java.util.Locale.ROOT, "%02x", value & 255));
        return text.toString();
    }

    static void writeState(Context context, String state) throws IOException {
        write(new AtomicFile(new File(context.getFilesDir(), "vector-probe-session")), state);
    }

    private static void write(AtomicFile file, String value) throws IOException {
        FileOutputStream stream = file.startWrite();
        try {
            stream.write(value.getBytes(StandardCharsets.US_ASCII));
            file.finishWrite(stream);
        } catch (IOException error) { file.failWrite(stream); throw error; }
    }

    synchronized void start() throws IOException {
        if (closed || worker != null || !BuildConfig.DEBUG) throw ControlProtocol.rejected();
        server = new LocalServerSocket(endpoint);
        write(bootstrap, hex(key) + "\n" + endpoint);
        // Covers accept, read and write stalls; close shuts down both directions.
        deadline.schedule(this::onExpiry, 900, TimeUnit.SECONDS);
        worker = new Thread(this::serve, "vector-probe-control");
        worker.start();
    }

    /** Direction-separated frame MAC ("request" or "response"); shared with the contract tests. */
    static byte[] mac(byte[] key, String direction, byte[] payload) throws java.security.GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        mac.update((direction + "\0").getBytes(StandardCharsets.US_ASCII));
        return mac.doFinal(payload);
    }

    private void serve() {
        try {
            LocalServerSocket listenerSocket;
            synchronized (this) { listenerSocket = server; }
            if (listenerSocket == null) return;
            LocalSocket accepted = listenerSocket.accept();
            synchronized (this) {
                if (closed) { accepted.close(); return; }
                client = accepted;
            }
            // Normal non-root adbd connects with shell UID. Never accept app UIDs
            // or root; OEM restrictions fail closed and require qualification.
            if (accepted.getPeerCredentials().getUid() != 2000) throw ControlProtocol.rejected();
            accepted.setSoTimeout(12000);
            DataInputStream input = new DataInputStream(accepted.getInputStream());
            DataOutputStream output = new DataOutputStream(accepted.getOutputStream());
            ControlProtocol protocol = new ControlProtocol(Instant.now(), SystemClock.elapsedRealtimeNanos(), android.os.Build.VERSION.SDK_INT, diagnostics);
            boolean first = true;
            while (!isClosed()) {
                // A complete frame must arrive within 12 seconds, even if bytes
                // trickle in fast enough to reset the underlying socket timeout.
                java.util.concurrent.ScheduledFuture<?> watchdog = deadline.schedule(this::close, 12, TimeUnit.SECONDS);
                try {
                    int size = input.readInt();
                    if (size <= 0 || size > ControlProtocol.MAX_BYTES) throw ControlProtocol.rejected();
                    byte[] signature = new byte[32];
                    input.readFully(signature);
                    byte[] payload = new byte[size];
                    input.readFully(payload);
                    if (!MessageDigest.isEqual(signature, mac(key, "request", payload))) throw ControlProtocol.rejected();
                    byte[] response = protocol.respond(payload, Instant.now(), SystemClock.elapsedRealtimeNanos());
                    if (first) {
                        synchronized (this) {
                            if (closed) return;
                            // No second desktop can bootstrap this consent after HELLO.
                            write(bootstrap, "REQUIRED");
                        }
                        listener.state(R.string.connected);
                        first = false;
                    }
                    output.writeInt(response.length);
                    output.write(mac(key, "response", response));
                    output.write(response);
                    output.flush();
                } finally { watchdog.cancel(false); }
            }
        } catch (Exception ignored) {
            // Do not log wire data, keys, package paths or device information.
        } finally { close(); listener.state(R.string.stopped); }
    }

    private synchronized boolean isClosed() { return closed; }

    @Override public synchronized void close() {
        if (closed) return;
        closed = true;
        diagnostics.close();
        if (client != null) {
            try { client.shutdownInput(); } catch (IOException ignored) { }
            try { client.shutdownOutput(); } catch (IOException ignored) { }
            try { client.close(); } catch (IOException ignored) { }
        }
        if (server != null) {
            // shutdown wakes a thread blocked in accept; close alone is not a
            // portable interruption guarantee for an already-blocked syscall.
            try { android.system.Os.shutdown(server.getFileDescriptor(), android.system.OsConstants.SHUT_RDWR); }
            catch (android.system.ErrnoException ignored) { }
            try { server.close(); } catch (IOException ignored) { }
        }
        String finalState = expired ? "EXPIRED" : "REQUIRED";
        try { write(bootstrap, finalState); } catch (IOException ignored) { bootstrap.delete(); }
        Arrays.fill(key, (byte) 0);
        deadline.shutdownNow();
    }
}
