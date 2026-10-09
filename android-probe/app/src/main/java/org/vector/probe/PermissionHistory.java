package org.vector.probe;

import android.app.Activity;
import android.content.Context;
import android.content.pm.PackageManager;

/**
 * Remembers whether a runtime permission was ever requested, because Android reports "no
 * rationale" both before the first request and after a permanent denial. Stores one boolean
 * per permission name in app-private preferences (excluded from backup); no personal data.
 */
final class PermissionHistory {
    private static final String PREFS = "probe_permissions";
    private static final String PREFIX = "requested_";

    private PermissionHistory() { }

    static boolean requested(Context context, String permission) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getBoolean(PREFIX + permission, false);
    }

    static void markRequested(Context context, String permission) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putBoolean(PREFIX + permission, true).apply();
    }

    /** App Settings is the only recovery once a requested permission is denied without rationale. */
    static boolean settingsRequired(Activity activity, String permission) {
        return activity.checkSelfPermission(permission) != PackageManager.PERMISSION_GRANTED
                && requested(activity, permission)
                && !activity.shouldShowRequestPermissionRationale(permission);
    }
}
