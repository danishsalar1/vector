package org.vector.probe;

import android.app.Activity;
import android.os.Bundle;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.io.IOException;

/** Visible consent is the only entry to serving. Intents cannot grant consent. */
public final class ProbeActivity extends Activity {
    private ProbeServer server;
    private TextView status;
    private long generation;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        LinearLayout layout = new LinearLayout(this);
        layout.setFitsSystemWindows(true);
        layout.setOrientation(LinearLayout.VERTICAL);
        int padding = (int) (24 * getResources().getDisplayMetrics().density);
        layout.setPadding(padding, padding, padding, padding);
        TextView purpose = new TextView(this);
        purpose.setText(R.string.purpose);
        purpose.setTextSize(18);
        layout.addView(purpose);
        status = new TextView(this);
        status.setAccessibilityLiveRegion(android.view.View.ACCESSIBILITY_LIVE_REGION_POLITE);
        layout.addView(status);
        Button allow = new Button(this);
        allow.setText(R.string.allow);
        allow.setFilterTouchesWhenObscured(true);
        allow.setOnClickListener(view -> allow());
        layout.addView(allow);
        Button deny = new Button(this);
        deny.setText(R.string.deny);
        deny.setOnClickListener(view -> revoke("DENIED", R.string.denied));
        layout.addView(deny);
        setContentView(layout);
        revoke("REQUIRED", R.string.required);
    }

    private void allow() {
        revoke("REQUIRED", R.string.required);
        if (!BuildConfig.DEBUG) { status.setText(R.string.restricted); return; }
        long current = generation;
        server = new ProbeServer(this, resource -> runOnUiThread(() -> {
            if (generation == current) {
                status.setText(resource);
                if (resource == R.string.stopped) {
                    getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                }
            }
        }));
        try {
            server.start();
            getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            status.setText(R.string.listening);
        } catch (IOException error) { revoke("REQUIRED", R.string.stopped); }
    }

    private void revoke(String state, int resource) {
        generation++;
        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        if (server != null) { server.close(); server = null; }
        try { ProbeServer.writeState(this, state); }
        catch (IOException ignored) { deleteFile("vector-probe-session"); }
        if (status != null) status.setText(resource);
    }

    @Override protected void onPause() {
        revoke("REQUIRED", R.string.stopped);
        super.onPause();
    }

    @Override protected void onDestroy() {
        revoke("REQUIRED", R.string.stopped);
        super.onDestroy();
    }
}
