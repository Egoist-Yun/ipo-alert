package io.github.egoistyun.ipoalert;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.text.NumberFormat;
import java.text.ParsePosition;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Date;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.StringJoiner;
import java.util.TimeZone;

final class AlarmRules {
    static final String TITLE = "공모주 달력";
    private static final int DEADLINE_ID_OFFSET = 1_000_000;

    record Alarm(int id, int no, long at, String body, boolean deadline) {
        // Different alarm types can share a numeric ID for large stock numbers.
        String key() {
            return (deadline ? "deadline:" : "listing:") + id;
        }
    }

    static List<Alarm> wanted(JSONArray ipos, JSONArray applied, JSONArray myBrokers, long now)
            throws JSONException {
        Set<Integer> marked = new HashSet<>();
        for (int i = 0; i < applied.length(); i++) marked.add(stockNumber(applied.opt(i)));
        Set<String> mine = new HashSet<>();
        for (int i = 0; i < myBrokers.length(); i++) {
            String broker = normalizeBroker(myBrokers.optString(i, ""));
            if (!broker.isEmpty()) mine.add(broker);
        }

        SimpleDateFormat clock = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.ROOT);
        clock.setTimeZone(TimeZone.getTimeZone("GMT+09:00"));
        clock.setLenient(false);
        List<Alarm> alarms = new ArrayList<>();
        for (int i = 0; i < ipos.length(); i++) {
            JSONObject ipo = ipos.getJSONObject(i);
            int no = stockNumber(ipo.opt("no"));
            if (no == 0 || ipo.optBoolean("withdrawn")) continue;

            String name = ipo.optString("name");
            String warning = switch (ipo.optString("warning")) {
                case "strong" -> " · 강한 하락 경고";
                case "warn" -> " · 하락 경고";
                default -> "";
            };

            if (marked.contains(no)) {
                long at = alarmTime(clock, ipo.optString("listing_date"), "08:30");
                if (at <= now) continue;
                String body = "오늘 " + name + " 상장";
                double price = ipo.optDouble("final_price", 0);
                if (price != 0) body += " · 공모가 " + NumberFormat.getNumberInstance(Locale.KOREA).format(price) + "원";
                alarms.add(new Alarm(no, no, at, body + warning, false));
            } else if (!mine.isEmpty() && ipo.isNull("first_close") && no <= Integer.MAX_VALUE - DEADLINE_ID_OFFSET) {
                long at = alarmTime(clock, ipo.optString("sub_end"), "14:00");
                if (at <= now) continue;
                Set<String> matches = matchingBrokers(ipo.optJSONArray("underwriters"), mine);
                if (matches.isEmpty()) continue;
                StringJoiner brokers = new StringJoiner(", ");
                for (String broker : matches) brokers.add(broker);
                String body = "오늘 청약 마감 · " + name + " · " + brokers;
                alarms.add(new Alarm(DEADLINE_ID_OFFSET + no, no, at, body + warning, true));
            }
        }
        alarms.sort(Comparator.comparingLong(Alarm::at).thenComparingInt(Alarm::id));
        return alarms;
    }

    private static int stockNumber(Object value) {
        if (!(value instanceof Number number)) return 0;
        double no = number.doubleValue();
        return no > 0 && no <= Integer.MAX_VALUE && no == Math.floor(no) ? (int) no : 0;
    }

    private static long alarmTime(SimpleDateFormat clock, String date, String time) {
        if (!date.matches("[0-9]{4}-[0-9]{2}-[0-9]{2}")) return Long.MIN_VALUE;
        Date parsed = clock.parse(date + "T" + time + ":00", new ParsePosition(0));
        return parsed == null ? Long.MIN_VALUE : parsed.getTime();
    }

    private static Set<String> matchingBrokers(JSONArray underwriters, Set<String> mine) {
        Set<String> matches = new LinkedHashSet<>();
        if (underwriters == null) return matches;
        for (int i = 0; i < underwriters.length(); i++) {
            String broker = normalizeBroker(underwriters.optString(i, ""));
            if (mine.contains(broker)) matches.add(broker);
        }
        return matches;
    }

    private static String normalizeBroker(String name) {
        // Same aliases and whitespace as web/brokers.js.
        return name.replaceAll("\\(주\\)|㈜|[\\s\\p{Z}\\uFEFF]+", "")
                .replaceFirst("^케이비", "KB")
                .replaceFirst("^엔에이치", "NH")
                .replaceFirst("^아이비케이", "IBK")
                .replaceFirst("^유진증권$", "유진투자증권")
                .replaceFirst("^미래에셋대우$", "미래에셋증권");
    }
}
