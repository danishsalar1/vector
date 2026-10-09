package org.vector.probe;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

/** Foreground evidence input. Desktop cannot submit a human confirmation. */
final class DiagnosticUi {
    final DiagnosticController controller;
    private final LinearLayout host;
    final TextView status;
    android.app.Dialog colorsDialog;
    android.app.Dialog touchDialog;
    TouchView touchView;
    private int shownLevel = -1;

    DiagnosticUi(DiagnosticController controller, LinearLayout host) {
        this.controller = controller; this.host = host;
        status = new TextView(controller.activity);
        status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
    }

    private Button button(int label, Runnable action) {
        Button button = new Button(controller.activity); button.setText(label);
        button.setFilterTouchesWhenObscured(true); button.setOnClickListener(v -> action.run());
        host.addView(button); return button;
    }

    void progress(DiagnosticJob job) {
        host.removeAllViews(); host.addView(status);
        shownLevel = -1;
        status.setText(controller.activity.getString(R.string.diag_running, job.id));
        button(R.string.diag_cancel, () -> controller.cancel(job, false));
    }

    void complete(DiagnosticJob job) {
        host.removeAllViews(); host.addView(status);
        status.setText(controller.activity.getString(R.string.diag_complete, job.id,
                job.snapshot(DiagnosticController.now()).get("reason")));
    }

    void permission(String permission) {
        status.setText(R.string.diag_permission_explanation);
        button(R.string.diag_permission, () -> {
            PermissionHistory.markRequested(controller.activity, permission);
            controller.activity.requestPermissions(new String[]{permission}, 8);
        });
        // Before the first request Android also reports "no rationale"; only a requested,
        // still-denied permission without rationale needs App Settings.
        if (PermissionHistory.settingsRequired(controller.activity, permission)) {
            button(R.string.diag_settings_open, () -> {
                Intent intent = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS);
                intent.setData(Uri.fromParts("package", controller.activity.getPackageName(), null));
                controller.activity.startActivity(intent);
            });
        }
    }

    /** Measured microphone input level, driven by collected samples; shown in 10% steps. */
    void inputLevel(DiagnosticJob job, int percent) {
        int step = Math.max(0, Math.min(100, percent)) / 10 * 10;
        if (!controller.current(job) || step == shownLevel) return;
        shownLevel = step;
        status.setText(controller.activity.getString(R.string.diag_mic_level, step));
    }

    /**
     * Uniform polarity for every confirmation: user_report 1 means the person observed the
     * expected behaviour, 0 means they observed a problem; "Unsure" records no report.
     */
    void confirm(DiagnosticJob job) {
        if (!controller.current(job)) return;
        int prompt = R.string.diag_confirmation_default, yes = R.string.diag_yes, no = R.string.diag_no;
        switch (job.id) {
            case "speaker": prompt = R.string.diag_confirmation_speaker; yes = R.string.diag_speaker_yes; no = R.string.diag_speaker_no; break;
            case "microphone": prompt = R.string.diag_confirmation_mic; yes = R.string.diag_mic_yes; no = R.string.diag_mic_no; break;
            case "vibration": prompt = R.string.diag_confirmation_vibrate; yes = R.string.diag_vibrate_yes; no = R.string.diag_vibrate_no; break;
            case "pixels": prompt = R.string.diag_confirmation_pixels; yes = R.string.diag_pixels_yes; no = R.string.diag_pixels_no; break;
            default: break;
        }
        status.setText(prompt);
        button(yes, () -> report(job, 1));
        button(no, () -> report(job, 0));
        button(R.string.diag_unsure, () -> controller.finish(job, "INCONCLUSIVE", "USER_UNCERTAIN"));
    }

    private void report(DiagnosticJob job, int value) {
        if (!controller.current(job)) return;
        job.metric("user_report", value, "boolean");
        controller.finish(job, "INCONCLUSIVE", "USER_REPORTED");
    }

    void clearInteraction() {
        if (colorsDialog != null) { colorsDialog.dismiss(); colorsDialog = null; }
        if (touchDialog != null) { touchDialog.dismiss(); touchDialog = null; }
        touchView = null;
    }

    /** Physical display size in the current rotation (not the possibly smaller app window). */
    @SuppressWarnings("deprecation")
    static int[] displaySize(Activity activity) {
        if (Build.VERSION.SDK_INT >= 30) {
            android.graphics.Rect bounds = activity.getWindowManager().getMaximumWindowMetrics().getBounds();
            return new int[]{bounds.width(), bounds.height()};
        }
        android.graphics.Point size = new android.graphics.Point();
        activity.getWindowManager().getDefaultDisplay().getRealSize(size);
        return new int[]{size.x, size.y};
    }

    void interactive(DiagnosticJob job) {
        if (job.id.equals("touch")) {
            status.setText(R.string.diag_touch);
            touchDialog = new android.app.Dialog(controller.activity, android.R.style.Theme_Material_Light_NoActionBar_Fullscreen);
            FrameLayout root = new FrameLayout(controller.activity);
            touchView = new TouchView(job);
            root.addView(touchView, new FrameLayout.LayoutParams(-1, -1));

            LinearLayout bar = new LinearLayout(controller.activity);
            bar.setOrientation(LinearLayout.HORIZONTAL);
            bar.setGravity(Gravity.CENTER_HORIZONTAL);
            FrameLayout.LayoutParams barLayout = new FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM);
            barLayout.setMargins(16, 16, 16, 16);
            root.addView(bar, barLayout);

            Button cancel = new Button(controller.activity);
            cancel.setText(R.string.diag_cancel);
            cancel.setFilterTouchesWhenObscured(true);
            cancel.setOnClickListener(v -> controller.cancel(job, false));
            bar.addView(cancel);

            Button done = new Button(controller.activity);
            done.setText(R.string.diag_done);
            done.setFilterTouchesWhenObscured(true);
            done.setOnClickListener(v -> finishTouch(job));
            bar.addView(done);

            touchDialog.setContentView(root);
            touchDialog.setOnCancelListener(dialog -> controller.cancel(job, false));
            touchDialog.show();
            Window window = touchDialog.getWindow();
            if (window != null) {
                window.addFlags(WindowManager.LayoutParams.FLAG_SECURE | WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                window.setLayout(-1, -1);
            }
        } else {
            status.setText(R.string.diag_pixels);
            colorsDialog = new android.app.Dialog(controller.activity, android.R.style.Theme_Material_Light_NoActionBar_Fullscreen);
            FrameLayout pattern = new FrameLayout(controller.activity);
            pattern.setBackgroundColor(Color.BLACK);
            LinearLayout controls = new LinearLayout(controller.activity);
            controls.setOrientation(LinearLayout.VERTICAL);
            FrameLayout.LayoutParams controlsLayout = new FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM);
            pattern.addView(controls, controlsLayout);
            colorsDialog.setContentView(pattern);
            colorsDialog.setOnCancelListener(dialog -> controller.cancel(job, false));
            colorsDialog.show();
            Window window = colorsDialog.getWindow();
            if (window != null) {
                window.addFlags(WindowManager.LayoutParams.FLAG_SECURE | WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                window.setLayout(-1, -1);
            }
            final int[] colors = {Color.BLACK, Color.WHITE, Color.RED, Color.GREEN, Color.BLUE};
            final int[] index = {0};
            job.metric("patterns_viewed", 1, "count");
            Button next = new Button(controller.activity); next.setText(R.string.diag_next_color);
            next.setFilterTouchesWhenObscured(true); controls.addView(next);
            next.setOnClickListener(v -> {
                if (!controller.current(job)) return;
                index[0]++;
                if (index[0] == colors.length) { clearInteraction(); confirm(job); return; }
                pattern.setBackgroundColor(colors[index[0]]);
                job.metric("patterns_viewed", index[0] + 1, "count");
            });
            Button brightness = new Button(controller.activity); brightness.setText(R.string.diag_brightness);
            brightness.setFilterTouchesWhenObscured(true); controls.addView(brightness);
            brightness.setOnClickListener(v -> {
                if (!controller.current(job) || window == null) return;
                WindowManager.LayoutParams attrs = window.getAttributes();
                attrs.screenBrightness = attrs.screenBrightness == 1f ? 0.25f : 1f;
                window.setAttributes(attrs);
            });
            Button cancel = new Button(controller.activity); cancel.setText(R.string.diag_cancel);
            cancel.setFilterTouchesWhenObscured(true); controls.addView(cancel);
            cancel.setOnClickListener(v -> controller.cancel(job, false));
        }
    }

    void finishTouch(DiagnosticJob job) {
        if (!controller.current(job) || touchView == null) return;
        boolean full = touchView.touch.covered();
        controller.finish(job, full ? "PASS" : "INCONCLUSIVE", full ? "TOUCH_COVERED" : "PARTIAL");
    }

    final class TouchView extends View {
        DiagnosticJob.Touch touch = new DiagnosticJob.Touch();
        final Paint paint = new Paint();
        final DiagnosticJob job;
        private int layoutGen;

        TouchView(DiagnosticJob job) {
            super(controller.activity);
            this.job = job;
            setFilterTouchesWhenObscured(true);
            setContentDescription(getContext().getString(R.string.diag_touch));
        }

        @Override protected void onSizeChanged(int w, int h, int oldw, int oldh) {
            super.onSizeChanged(w, h, oldw, oldh);
            if (controller.current(job)) {
                layoutGen++;
                // The app window hosting the grid; unknown stays 0 and can never support PASS.
                int winW = 0;
                int winH = 0;
                if (touchDialog != null && touchDialog.getWindow() != null) {
                    View decor = touchDialog.getWindow().getDecorView();
                    if (decor != null && decor.getWidth() > 0 && decor.getHeight() > 0) {
                        winW = decor.getWidth();
                        winH = decor.getHeight();
                    }
                }
                int[] display = displaySize(controller.activity);
                touch.reset(w, h, winW, winH, display[0], display[1], layoutGen);
                writeMetrics();
                status.setText(getContext().getString(R.string.diag_touch_progress, 0, 0, 0));
            }
        }

        private Integer positive(int value) { return value > 0 ? value : null; }

        private void writeMetrics() {
            job.metric("touch_cells", touch.count, "count");
            job.metric("cell_coverage_percent", touch.cellCoveragePercent(), "percent");
            job.metric("max_contacts", touch.simultaneous, "count");
            job.metric("tested_width", positive(touch.testedWidth), "pixels");
            job.metric("tested_height", positive(touch.testedHeight), "pixels");
            job.metric("window_width", positive(touch.windowWidth), "pixels");
            job.metric("window_height", positive(touch.windowHeight), "pixels");
            job.metric("display_width", positive(touch.displayWidth), "pixels");
            job.metric("display_height", positive(touch.displayHeight), "pixels");
            job.metric("tested_window_area_percent", touch.testedWindowAreaPercent(), "percent");
            job.metric("tested_display_area_percent", touch.testedDisplayAreaPercent(), "percent");
            job.metric("layout_generation", touch.layoutGeneration, "count");
        }

        @Override protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            for (int i = 0; i < 24; i++) {
                paint.setColor(touch.visited(i) ? Color.rgb(0, 110, 80) : Color.DKGRAY);
                canvas.drawRect(i % 4 * getWidth() / 4f + 2, i / 4 * getHeight() / 6f + 2,
                        (i % 4 + 1) * getWidth() / 4f - 2, (i / 4 + 1) * getHeight() / 6f - 2, paint);
            }
        }

        @Override public boolean onTouchEvent(MotionEvent event) {
            if (!controller.current(job) || (event.getFlags() & (MotionEvent.FLAG_WINDOW_IS_OBSCURED | 2)) != 0) return false;
            int action = event.getActionMasked();
            if (action == MotionEvent.ACTION_DOWN || action == MotionEvent.ACTION_MOVE || action == MotionEvent.ACTION_POINTER_DOWN) {
                for (int i = 0; i < event.getPointerCount(); i++) {
                    touch.observe(event.getX(i), event.getY(i), getWidth(), getHeight(), event.getPointerCount());
                }
                writeMetrics();
                status.setText(getContext().getString(R.string.diag_touch_progress, touch.count, (int) touch.cellCoveragePercent(), touch.simultaneous));
                invalidate();
            }
            if (action == MotionEvent.ACTION_UP) performClick();
            return true;
        }

        @Override public boolean performClick() { super.performClick(); return true; }
    }
}
