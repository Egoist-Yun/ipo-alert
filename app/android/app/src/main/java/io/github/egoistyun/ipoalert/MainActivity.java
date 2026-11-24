package io.github.egoistyun.ipoalert;

import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.util.Log;
import android.webkit.WebView;

import androidx.activity.OnBackPressedCallback;

import com.getcapacitor.BridgeActivity;
import com.getcapacitor.WebViewListener;
import com.google.firebase.messaging.FirebaseMessaging;

public class MainActivity extends BridgeActivity {
    private int pendingAlarmNo;
    private boolean activityCreated;
    private boolean webPageLoaded;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        registerPlugin(AlarmSyncPlugin.class);
        bridgeBuilder.addWebViewListener(new WebViewListener() {
            @Override
            public void onPageStarted(WebView webView) {
                webPageLoaded = false;
            }

            @Override
            public void onPageLoaded(WebView webView) {
                webPageLoaded = true;
                openAlarmStock(webView);
            }
        });
        super.onCreate(savedInstanceState);
        activityCreated = true;
        if (savedInstanceState == null) handleAlarmIntent(getIntent());

        // Server alerts go to the FCM topic "ipo-alerts": every install subscribes (repeating it on each start is harmless).
        // The try/catch only guards a build without google-services.json, where FirebaseMessaging is not initialised.
        try {
            FirebaseMessaging.getInstance().subscribeToTopic("ipo-alerts").addOnCompleteListener(task -> {
                if (!task.isSuccessful()) Log.w("ipoalert", "topic subscribe failed", task.getException());
            });
        } catch (Exception e) {
            Log.w("ipoalert", "topic subscribe skipped", e);
        }
        // The calendar moves between list / detail / record screens with history entries: the back key must step back
        // through them (detail -> list) and only leave the app from the list.
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                WebView web = getBridge().getWebView();
                if (web != null && web.canGoBack()) {
                    web.goBack();
                } else {
                    setEnabled(false);
                    getOnBackPressedDispatcher().onBackPressed();
                }
            }
        });
    }

    @Override
    public void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        // Capacitor forwards the launch intent here during super.onCreate().
        if (activityCreated) handleAlarmIntent(intent);
    }

    private void handleAlarmIntent(Intent intent) {
        if (intent == null || getBridge() == null) return;
        int no = intent.getIntExtra(AlarmScheduler.EXTRA_NO, 0);
        if (no <= 0) return;
        intent.removeExtra(AlarmScheduler.EXTRA_NO);
        pendingAlarmNo = no;
        openAlarmStock(getBridge().getWebView());
    }

    private void openAlarmStock(WebView webView) {
        if (pendingAlarmNo == 0 || !webPageLoaded || webView.getUrl() == null || getBridge() == null) return;
        Uri page = Uri.parse(webView.getUrl()).buildUpon().fragment(null).build();
        if (!page.equals(Uri.parse(getBridge().getAppUrl()))) return;

        webView.evaluateJavascript("location.hash = '" + pendingAlarmNo + "';", null);
        pendingAlarmNo = 0;
    }
}
