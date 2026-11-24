package io.github.egoistyun.ipoalert;

import android.Manifest;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;

import androidx.core.app.NotificationCompat;
import androidx.core.content.ContextCompat;

public class AlarmReceiver extends BroadcastReceiver {
    // Reuse the local-notifications channel so existing channel settings carry over.
    private static final String CHANNEL = "default";

    @Override
    public void onReceive(Context context, Intent intent) {
        if (Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) {
            if (AlarmSyncPlugin.preferences(context).contains(AlarmSyncPlugin.STATE)) {
                AlarmWorker.enqueueSync(context);
            }
            return;
        }

        int no = intent.getIntExtra(AlarmScheduler.EXTRA_NO, 0);
        int id = intent.getIntExtra(AlarmScheduler.EXTRA_ID, 0);
        String body = intent.getStringExtra(AlarmScheduler.EXTRA_BODY);
        if (no <= 0 || id <= 0 || body == null) return;

        NotificationManager manager = context.getSystemService(NotificationManager.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && manager.getNotificationChannel(CHANNEL) == null) {
            manager.createNotificationChannel(new NotificationChannel(CHANNEL, AlarmRules.TITLE,
                    NotificationManager.IMPORTANCE_DEFAULT));
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
                ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS)
                        != PackageManager.PERMISSION_GRANTED) return;

        Intent openStock = new Intent(context, MainActivity.class).setAction(intent.getAction())
                .putExtra(AlarmScheduler.EXTRA_NO, no);
        PendingIntent tap = PendingIntent.getActivity(context, 0, openStock,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        manager.notify(intent.getAction(), id, new NotificationCompat.Builder(context, CHANNEL)
                .setSmallIcon(R.drawable.ic_stat_ipo)
                .setContentTitle(AlarmRules.TITLE)
                .setContentText(body)
                .setStyle(new NotificationCompat.BigTextStyle().bigText(body))
                .setDefaults(NotificationCompat.DEFAULT_ALL)
                .setAutoCancel(true)
                .setContentIntent(tap)
                .build());
    }
}
