package io.github.egoistyun.ipoalert;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.util.List;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;

public class AlarmRulesTest {
    @Test
    public void matchesSharedFixture() throws Exception {
        JSONObject fixture = fixture();
        List<AlarmRules.Alarm> alarms = wanted(fixture, fixture.getJSONArray("myBrokers"));
        JSONArray expected = fixture.getJSONArray("expected");
        assertEquals(expected.length(), alarms.size());
        for (int i = 0; i < expected.length(); i++) {
            JSONObject row = expected.getJSONObject(i);
            AlarmRules.Alarm alarm = alarms.get(i);
            assertEquals(row.getInt("id"), alarm.id());
            assertEquals(row.getInt("no"), alarm.no());
            assertEquals(millis(row.getString("at")), alarm.at());
            assertEquals(row.getString("title"), AlarmRules.TITLE);
            assertEquals(row.getString("body"), alarm.body());
        }
        assertEquals(alarms.size(), alarms.stream().map(AlarmRules.Alarm::key).distinct().count());
    }

    @Test
    public void emptyBrokerSelectionLeavesListingAlarmsOnly() throws Exception {
        List<AlarmRules.Alarm> alarms = wanted(fixture(), new JSONArray());
        assertEquals(List.of(1, 1000002, Integer.MAX_VALUE),
                alarms.stream().map(AlarmRules.Alarm::id).toList());
    }

    private static List<AlarmRules.Alarm> wanted(JSONObject fixture, JSONArray brokers) throws Exception {
        return AlarmRules.wanted(fixture.getJSONArray("ipos"), fixture.getJSONArray("applied"),
                brokers, millis(fixture.getString("now")));
    }

    private static long millis(String iso) {
        return OffsetDateTime.parse(iso).toInstant().toEpochMilli();
    }

    private static JSONObject fixture() throws Exception {
        try (InputStream input = AlarmRulesTest.class.getResourceAsStream("/alarms_case.json")) {
            assertNotNull("Shared alarms fixture must be on the test classpath", input);
            return new JSONObject(new String(input.readAllBytes(), StandardCharsets.UTF_8));
        }
    }
}
