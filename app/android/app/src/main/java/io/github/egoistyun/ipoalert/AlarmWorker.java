package io.github.egoistyun.ipoalert;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.Log;

import androidx.annotation.NonNull;
import androidx.work.Constraints;
import androidx.work.ExistingPeriodicWorkPolicy;
import androidx.work.ExistingWorkPolicy;
import androidx.work.NetworkType;
import androidx.work.OneTimeWorkRequest;
import androidx.work.PeriodicWorkRequest;
import androidx.work.WorkManager;
import androidx.work.Worker;
import androidx.work.WorkerParameters;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class AlarmWorker extends Worker {
    private static final Object SYNC_LOCK = new Object();
    private static final Constraints ONLINE = new Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED).build();
    private static final String FEED_URL = "https://egoist-yun.github.io/ipo-alert/ipos.json";

    public AlarmWorker(@NonNull Context context, @NonNull WorkerParameters params) {
        super(context, params);
    }

    static void enqueueSync(Context context) {
        WorkManager work = WorkManager.getInstance(context);
        work.enqueueUniquePeriodicWork("ipo-alarms-periodic", ExistingPeriodicWorkPolicy.KEEP,
                new PeriodicWorkRequest.Builder(AlarmWorker.class, 6, TimeUnit.HOURS)
                        .setInitialDelay(6, TimeUnit.HOURS)
                        .setConstraints(ONLINE).build());
        work.enqueueUniqueWork("ipo-alarms-sync", ExistingWorkPolicy.REPLACE,
                new OneTimeWorkRequest.Builder(AlarmWorker.class).setConstraints(ONLINE).build());
    }

    @NonNull
    @Override
    public Result doWork() {
        Context context = getApplicationContext();
        SharedPreferences prefs = AlarmSyncPlugin.preferences(context);
        // Serialize periodic and immediate runs so an older feed response cannot win.
        synchronized (SYNC_LOCK) {
            if (isStopped() || !prefs.contains(AlarmSyncPlugin.STATE)) return Result.success();
            try {
                JSONArray ipos = downloadIpos();
                JSONObject state = new JSONObject(prefs.getString(AlarmSyncPlugin.STATE, "{}"));
                List<AlarmRules.Alarm> wanted = AlarmRules.wanted(ipos,
                        state.getJSONArray("applied"), state.getJSONArray("myBrokers"),
                        System.currentTimeMillis());
                if (isStopped()) return Result.success();
                AlarmScheduler.reconcile(context, prefs, wanted);
                return Result.success();
            } catch (IOException | JSONException | RuntimeException e) {
                Log.w("ipoalert", "Alarm sync will retry", e);
                return Result.retry();
            }
        }
    }

    private static JSONArray downloadIpos() throws IOException, JSONException {
        HttpURLConnection connection = (HttpURLConnection) new URL(FEED_URL).openConnection();
        try {
            connection.setConnectTimeout(10_000);
            connection.setReadTimeout(10_000);
            connection.setUseCaches(false);
            if (connection.getResponseCode() != HttpURLConnection.HTTP_OK) {
                throw new IOException("IPO feed HTTP status " + connection.getResponseCode());
            }
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                    connection.getInputStream(), StandardCharsets.UTF_8))) {
                StringBuilder body = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) body.append(line).append('\n');
                return new JSONObject(body.toString()).getJSONArray("ipos");
            }
        } finally {
            connection.disconnect();
        }
    }
}
