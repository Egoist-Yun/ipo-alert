package io.github.egoistyun.ipoalert;

import android.content.Context;
import android.content.SharedPreferences;

import com.getcapacitor.JSArray;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import org.json.JSONException;
import org.json.JSONObject;

@CapacitorPlugin(name = "AlarmSync")
public class AlarmSyncPlugin extends Plugin {
    static final String STATE = "state";

    static SharedPreferences preferences(Context context) {
        return context.getSharedPreferences("ipo-alarms", Context.MODE_PRIVATE);
    }

    @PluginMethod
    public void setState(PluginCall call) {
        JSArray applied = call.getArray("applied");
        JSArray myBrokers = call.getArray("myBrokers");
        if (applied == null || myBrokers == null) {
            call.reject("applied and myBrokers must be arrays");
            return;
        }

        try {
            JSONObject state = new JSONObject().put("applied", applied).put("myBrokers", myBrokers);
            if (!preferences(getContext()).edit().putString(STATE, state.toString()).commit()) {
                call.reject("Could not save alarm preferences");
                return;
            }
        } catch (JSONException e) {
            call.reject("Could not read alarm preferences", e);
            return;
        }

        syncNow(call);
    }

    @PluginMethod
    public void syncNow(PluginCall call) {
        AlarmWorker.enqueueSync(getContext());
        call.resolve();
    }
}
