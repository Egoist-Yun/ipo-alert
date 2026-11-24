package io.github.egoistyun.ipoalert;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;

import java.io.IOException;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

final class AlarmScheduler {
    private static final String SCHEDULED = "scheduled";
    static final String EXTRA_NO = "ipoAlarmNo";
    static final String EXTRA_ID = "ipoAlarmId";
    static final String EXTRA_BODY = "ipoAlarmBody";

    static void reconcile(Context context, SharedPreferences prefs, List<AlarmRules.Alarm> wanted)
            throws IOException {
        AlarmManager manager = context.getSystemService(AlarmManager.class);
        Set<String> previous = new HashSet<>(prefs.getStringSet(SCHEDULED, Collections.emptySet()));
        Set<String> scheduled = new HashSet<>();
        for (AlarmRules.Alarm alarm : wanted) scheduled.add(alarm.key());
        // Remember both sets until reconciliation finishes, so a retry can clean up partial work.
        Set<String> tracked = new HashSet<>(previous);
        tracked.addAll(scheduled);
        save(prefs, tracked);

        for (String stale : previous) {
            if (scheduled.contains(stale)) continue;
            PendingIntent operation = PendingIntent.getBroadcast(context, 0,
                    alarmIntent(context, stale), PendingIntent.FLAG_NO_CREATE | PendingIntent.FLAG_IMMUTABLE);
            if (operation != null) {
                manager.cancel(operation);
                operation.cancel();
            }
        }
        for (AlarmRules.Alarm alarm : wanted) {
            Intent intent = alarmIntent(context, alarm.key())
                    .putExtra(EXTRA_ID, alarm.id()).putExtra(EXTRA_NO, alarm.no())
                    .putExtra(EXTRA_BODY, alarm.body());
            if (alarm.at() <= System.currentTimeMillis()) continue;
            PendingIntent operation = PendingIntent.getBroadcast(context, 0, intent,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            schedule(manager, alarm.at(), operation);
        }

        save(prefs, scheduled);
    }

    private static void save(SharedPreferences prefs, Set<String> ids) throws IOException {
        if (!prefs.edit().putStringSet(SCHEDULED, ids).commit()) {
            throw new IOException("Could not save scheduled alarm IDs");
        }
    }

    private static Intent alarmIntent(Context context, String key) {
        return new Intent(context, AlarmReceiver.class).setAction(key);
    }

    private static void schedule(AlarmManager manager, long at, PendingIntent operation) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S || manager.canScheduleExactAlarms()) {
            try {
                manager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, operation);
                return;
            } catch (SecurityException ignored) {
                // Permission can be revoked between the capability check and scheduling.
            }
        }
        manager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, operation);
    }
}
