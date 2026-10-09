package org.vector.probe;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.io.IOException;

/** Visible consent is the only entry to serving. Intents cannot grant consent. */
public final class ProbeActivity extends Activity implements DiagnosticController.StatusListener {
    private ProbeServer server;
    private TextView status;
    private long generation;
    private LinearLayout diagnosticHost;
    private LinearLayout permissionPanel;
    private DiagnosticController diagnostics;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        ScrollView scrollView = new ScrollView(this);
        scrollView.setFillViewport(true);
        LinearLayout layout = new LinearLayout(this);
        layout.setFitsSystemWindows(true);
        layout.setOrientation(LinearLayout.VERTICAL);
        int padding = (int) (24 * getResources().getDisplayMetrics().density);
        layout.setPadding(padding, padding, padding, padding);

        TextView purpose = new TextView(this);
        purpose.setText(R.string.purpose);
        purpose.setTextSize(16);
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

        permissionPanel = new LinearLayout(this);
        permissionPanel.setOrientation(LinearLayout.VERTICAL);
        layout.addView(permissionPanel);

        diagnosticHost = new LinearLayout(this);
        diagnosticHost.setOrientation(LinearLayout.VERTICAL);
        layout.addView(diagnosticHost, new LinearLayout.LayoutParams(-1, 0, 1));

        scrollView.addView(layout);
        setContentView(scrollView);
        revoke("REQUIRED", R.string.required);
        refreshPermissions();
    }

    @Override
    protected void onResume() {
        super.onResume();
        refreshPermissions();
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        for (String perm : permissions) {
            PermissionHistory.markRequested(this, perm);
        }
        refreshPermissions();
    }

    private void refreshPermissions() {
        if (permissionPanel == null || server != null) return;
        permissionPanel.removeAllViews();

        TextView title = new TextView(this);
        title.setText(R.string.perm_title);
        title.setTextSize(14);
        title.setPadding(0, 16, 0, 8);
        permissionPanel.addView(title);

        addPermissionRow(Manifest.permission.CAMERA, getString(R.string.perm_camera), 101);
        addPermissionRow(Manifest.permission.RECORD_AUDIO, getString(R.string.perm_mic), 102);
        if (Build.VERSION.SDK_INT >= 29) {
            addPermissionRow(Manifest.permission.ACTIVITY_RECOGNITION, getString(R.string.perm_activity), 103);
        }
    }

    private void addPermissionRow(String permission, String label, int requestCode) {
        boolean granted = checkSelfPermission(permission) == PackageManager.PERMISSION_GRANTED;
        boolean requestedBefore = PermissionHistory.requested(this, permission);
        String statusLabel;
        if (granted) {
            statusLabel = getString(R.string.perm_granted);
        } else if (!requestedBefore) {
            statusLabel = getString(R.string.perm_not_requested);
        } else if (shouldShowRequestPermissionRationale(permission)) {
            statusLabel = getString(R.string.perm_denied_can_retry);
        } else {
            statusLabel = getString(R.string.perm_settings_recommended);
        }
        TextView text = new TextView(this);
        text.setText(getString(R.string.perm_status_format, label, statusLabel));
        permissionPanel.addView(text);

        if (!granted) {
            Button req = new Button(this);
            req.setText(getString(R.string.perm_request_format, getString(R.string.perm_request), label));
            req.setFilterTouchesWhenObscured(true);
            req.setOnClickListener(v -> {
                PermissionHistory.markRequested(this, permission);
                requestPermissions(new String[]{permission}, requestCode);
            });
            permissionPanel.addView(req);

            if (PermissionHistory.settingsRequired(this, permission)) {
                TextView explain = new TextView(this);
                explain.setText(R.string.perm_settings_explanation);
                permissionPanel.addView(explain);

                Button openSettings = new Button(this);
                openSettings.setText(R.string.perm_settings);
                openSettings.setFilterTouchesWhenObscured(true);
                openSettings.setOnClickListener(v -> {
                    Intent intent = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS);
                    intent.setData(Uri.fromParts("package", getPackageName(), null));
                    startActivity(intent);
                });
                permissionPanel.addView(openSettings);
            }
        }
    }

    private void allow() {
        revoke("REQUIRED", R.string.required);
        if (!BuildConfig.DEBUG) { status.setText(R.string.restricted); return; }
        long current = generation;
        if (permissionPanel != null) permissionPanel.removeAllViews();
        diagnostics = new DiagnosticController(this, diagnosticHost, this);
        server = new ProbeServer(this, resource -> runOnUiThread(() -> {
            if (generation == current) {
                status.setText(resource);
                if (resource == R.string.stopped) {
                    getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                }
            }
        }), diagnostics);
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
        if (diagnostics != null) { diagnostics.close(); diagnostics = null; }
        if (diagnosticHost != null) { diagnosticHost.removeAllViews(); }
        try { ProbeServer.writeState(this, state); }
        catch (IOException ignored) { deleteFile("vector-probe-session"); }
        if (status != null) status.setText(resource);
        refreshPermissions();
    }

    @Override
    public void onDiagnosticActive(String id) {
        runOnUiThread(() -> {
            if (status != null && server != null) {
                status.setText(getString(R.string.active, id));
            }
        });
    }

    @Override
    public void onDiagnosticIdle() {
        runOnUiThread(() -> {
            if (status != null && server != null) {
                status.setText(R.string.connected);
            }
        });
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
