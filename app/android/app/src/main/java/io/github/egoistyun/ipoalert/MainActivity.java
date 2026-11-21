package io.github.egoistyun.ipoalert;

import android.os.Bundle;
import android.util.Log;
import android.webkit.WebView;

import androidx.activity.OnBackPressedCallback;

import com.getcapacitor.BridgeActivity;
import com.google.firebase.messaging.FirebaseMessaging;

public class MainActivity extends BridgeActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
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
}
