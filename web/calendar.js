const pad = n => String(n).padStart(2, '0');

function bounds(year, month) {
  const last = new Date(Date.UTC(year, month, 0)).getUTCDate();
  return [`${year}-${pad(month)}-01`, `${year}-${pad(month)}-${pad(last)}`];
}

export function monthGrid(year, month) {
  const [first, last] = bounds(year, month);
  const lastDay = Number(last.slice(8));
  const offset = (new Date(Date.UTC(year, month - 1, 1)).getUTCDay() + 6) % 7; // Monday = 0
  const cells = [...Array(offset).fill('')];
  for (let d = 1; d <= lastDay; d++) cells.push(`${year}-${pad(month)}-${pad(d)}`);
  while (cells.length % 7) cells.push('');
  const weeks = [];
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));
  return weeks;
}

function overlapping(ipos, year, month) {
  const [first, last] = bounds(year, month);
  return ipos.filter(i => i.sub_start && i.sub_end && i.sub_start <= last && i.sub_end >= first);
}

export function barsForMonth(ipos, year, month) {
  const [first, last] = bounds(year, month);
  return overlapping(ipos, year, month).map(i => ({
    no: i.no,
    name: i.name,
    start: i.sub_start < first ? first : i.sub_start,
    end: i.sub_end > last ? last : i.sub_end,
    flagCount: i.flag_count ?? 0,
    isSpac: !!i.is_spac,
    hasResult: i.inst_competition != null,
  }));
}

export function listForMonth(ipos, year, month) {
  return overlapping(ipos, year, month).sort((a, b) => a.sub_start.localeCompare(b.sub_start) || a.no - b.no);
}

export function badgeInfo(ipo) {
  if (ipo.is_spac) return { text: '스팩', tone: 'spac' };
  if (ipo.first_close != null && ipo.final_price) {  // already listed: what actually happened beats any signal
    const r = ipo.first_close / ipo.final_price - 1;
    return { text: `${r >= 0 ? '+' : ''}${(r * 100).toFixed(0)}%`, tone: 'done' };  // a result, not a warning: grey either way
  }
  if (ipo.inst_competition == null) return { text: '대기 중', tone: 'wait' };
  const flags = ipo.flag_count ?? 0;
  const unknown = ipo.unknown_count ?? 0;
  if (ipo.warning === 'strong') return { text: '강한 하락 경고', tone: 'risk' };
  if (ipo.warning === 'warn') return { text: '하락 경고', tone: 'risk' };
  const p = ipo.prediction || {};
  const warn = p.open_down ? p.open_down.warn : (p.prob && p.prob.warn);
  if (warn) return { text: '하락 경고', tone: 'risk' };
  if (flags > 0) return { text: `신호 ${flags}개`, tone: 'wait' };  // signals without a warning: neutral (red/⚠ are for warnings only)
  if (unknown >= 2) return { text: `확인 불가 ${unknown}`, tone: 'wait' };
  return { text: unknown ? `신호 없음 · 확인 불가 ${unknown}` : '신호 없음', tone: '' };
}

export function staleHours(updatedAt, nowMs) {
  const t = Date.parse(updatedAt);
  return Number.isNaN(t) ? null : Math.floor((nowMs - t) / 3600000);
}

export const REFRESH_AFTER_MS = 30 * 60 * 1000;

export function needsRefresh(loadedAtMs, nowMs, afterMs = REFRESH_AFTER_MS) {
  if (typeof loadedAtMs !== 'number' || nowMs < loadedAtMs) return false;
  return nowMs - loadedAtMs >= afterMs;
}

// "경고 16개 중 10개 적중 · 하락 12개 중 10개 포착": the validation counts behind a warning (percentages for older data).
export function warnText(w, strong) {
  const caught = strong ? w.strong_caught : w.caught;
  const warned = strong ? w.strong_warned : w.warned;
  if (caught != null && warned != null && w.n_down != null) {
    return `경고 ${warned}개 중 ${caught}개 적중 · 하락 ${w.n_down}개 중 ${caught}개 포착`;
  }
  const sp = strong ? w.strong_precision : w.precision;
  const sr = strong ? w.strong_recall : w.recall;
  return sp != null && sr != null ? `적중 ${(sp * 100).toFixed(0)}% · 하락의 ${(sr * 100).toFixed(0)}% 포착` : null;
}

// Live record: predictions saved before listing, scored afterwards. Counts only (no percentages): the sample is small.
const RECORD_LABELS = { pre: '청약 전 모델 (종가 기준)', post: '청약 마감 후 모델 (시초가 기준)' };

export function recordRows(ledger) {
  if (!ledger) return null;
  const rows = [];
  let early = false;
  for (const key of ['pre', 'post']) {
    const m = ledger[key];
    if (!m || !m.saved) continue;
    const label = RECORD_LABELS[key];
    rows.push([label, `경고 ${m.warned}개 중 ${m.caught}개 적중 · 하락 ${m.n_down}개 중 ${m.caught}개 포착`]);
    if (m.strong_warned) rows.push([`${label.split(' (')[0]} 강한 경고`, `${m.strong_warned}개 중 ${m.strong_caught}개 적중`]);
    if (m.pending) rows.push([`${label.split(' (')[0]} 결과 대기`, `${m.pending}개`]);
    if (m.early) early = true;
  }
  return { rows, early };
}

// The one-line conclusion at the top of the detail panel. Listed stocks and spacs have none (they show the result / nothing).
export function verdictInfo(ipo) {
  if (ipo.is_spac || ipo.first_close != null) return null;
  if (ipo.inst_competition == null) return { text: '기관 수요예측 결과가 아직 없어요.', tone: 'wait' };
  const warn = ipo.warning;
  if (warn) {
    const strong = warn === 'strong';
    return { text: strong ? '강한 하락 경고' : '하락 경고', tone: 'risk' };  // the hit counts live in the "과거 검증" row only
  }
  const unknown = ipo.unknown_count ?? 0;
  return { text: unknown ? `하락 경고 없음 · 확인 불가 ${unknown}개` : '하락 경고 없음', tone: '' };
}

// Which screen a location hash asks for: the list (default), one stock's detail (#<no>) or the live record (#record).
export function parseRoute(hash, ipos) {
  const h = typeof hash === 'string' && hash.startsWith('#') ? hash.slice(1) : '';
  if (h === 'record') return { view: 'record', no: null };
  if (/^\d+$/.test(h)) {
    const no = Number(h);
    if ((ipos || []).some(i => i.no === no)) return { view: 'detail', no };
  }
  return { view: 'list', no: null };
}

// The list screen's groups. `applied` (the user marked a subscription and the stock has not listed yet) ignores the shown month.
// `upcoming` = shown month, not applied, subscription not over; `done` = shown month, subscription over or already listed.
// The data has no closing time, so on the deadline day itself (sub_end === today) a stock still counts as running.
export function groupForList(ipos, year, month, todayIso, applied) {
  const waiting = i => applied.has(i.no) && i.first_close == null;
  const running = i => i.first_close == null && i.sub_end >= todayIso;
  const mine = ipos.filter(waiting)
    .sort((a, b) => (a.listing_date || '9999').localeCompare(b.listing_date || '9999') || a.no - b.no);
  const rest = listForMonth(ipos, year, month).filter(i => !waiting(i));
  return {
    applied: mine,
    upcoming: rest.filter(running),
    done: rest.filter(i => !running(i)).sort((a, b) => b.sub_end.localeCompare(a.sub_end) || b.no - a.no),
  };
}

export function listingLabel(ipo) {
  return ipo.listing_date ? `${Number(ipo.listing_date.slice(5, 7))}/${Number(ipo.listing_date.slice(8, 10))} 상장` : '상장일 미정';
}

// Which subscriptions the user applied for: kept only on this device (never sent anywhere: the repository is public).
const APPLIED_KEY = 'ipo-applied';

export function readApplied(storage) {
  try {
    const list = JSON.parse(storage.getItem(APPLIED_KEY));
    return new Set(Array.isArray(list) ? list.filter(Number.isInteger) : []);
  } catch (e) {
    return new Set();
  }
}

export function saveApplied(storage, set) {
  try { storage.setItem(APPLIED_KEY, JSON.stringify([...set].sort((a, b) => a - b))); } catch (e) { /* storage blocked: marking is off */ }
}

export function appliedAvailable(storage) {
  try {
    storage.setItem('ipo-storage-check', '1');
    storage.removeItem('ipo-storage-check');
    return true;
  } catch (e) {
    return false;
  }
}

export function toggleApplied(set, no) {
  const next = new Set(set);
  if (!next.delete(no)) next.add(no);
  return next;
}

// Local alarm for each stock the user marked as applied: 08:30 KST on its listing day (pre-market orders open then).
// Pure: the app schedules exactly this list and cancels anything else it had scheduled.
export function listingAlarms(ipos, applied, nowIso) {
  const now = Date.parse(nowIso);
  if (Number.isNaN(now)) return [];
  return ipos
    .filter(i => applied.has(i.no) && /^\d{4}-\d{2}-\d{2}$/.test(i.listing_date || ''))
    .map(i => ({ ipo: i, at: `${i.listing_date}T08:30:00+09:00` }))
    .filter(x => Date.parse(x.at) > now)
    .sort((a, b) => a.at.localeCompare(b.at) || a.ipo.no - b.ipo.no)
    .map(({ ipo, at }) => {
      const price = ipo.final_price ? ` 공모가 ${Number(ipo.final_price).toLocaleString('ko-KR')}원` : '';
      const warn = ipo.warning === 'strong' ? '\n강한 하락 경고가 있어요.' : ipo.warning === 'warn' ? '\n하락 경고가 있어요.' : '';
      return { id: ipo.no, at, title: `오늘 ${ipo.name} 상장`, body: `시초가 매도 준비.${price}${warn}`, no: ipo.no };
    });
}

// Text of a calendar bar: the name, "⚠ " in front for a risk stock, "✓ " in front of that when marked as applied.
// State words (대기 중, 스팩, 경고, 결과 %, 신호 개수) stay out of the bar: the colour and the list below already say them.
// A continuation piece that is one day wide (the bar began in an earlier week) is too narrow for text: colour only.
export function barLabel({ name, risk, applied, continuationOneDay }) {
  if (continuationOneDay) return '';
  return `${applied ? '✓ ' : ''}${risk ? '⚠ ' : ''}${name}`;
}

// The toast shown when a stock is marked as applied. Alarms exist only in the Android app, so a browser says so; the app
// confirms the alarm, reports switched-off notifications, or promises one for a stock whose listing date is not known yet
// (the app schedules it the next time it opens after the date appears). A listing date already in the past: nothing to say.
export function markToast({ native, alarmOff, hasAlarm, hasListingDate }) {
  if (!native) return '알림은 안드로이드 앱에서만 받을 수 있어요';
  if (hasAlarm) return alarmOff ? '알림이 꺼져 있어요' : '상장일 08:30에 알림으로 알려드릴게요, 몇 분 늦을 수 있어요';
  return hasListingDate ? null : '상장일이 정해지면 08:30에 알림을 예약할게요';
}

// A "today / tomorrow" note for a stock, by KST date strings (YYYY-MM-DD). Priority: listing today, listing tomorrow,
// last subscription day, first subscription day. Anything else (and already listed stocks): null.
export function dayStatus(ipo, todayIso) {
  if (ipo.first_close != null) return null;
  const t = Date.parse(`${todayIso}T00:00:00Z`);
  if (Number.isNaN(t)) return null;
  const tomorrow = new Date(t + 86400000).toISOString().slice(0, 10);
  if (ipo.listing_date === todayIso) return '오늘 상장';
  if (ipo.listing_date === tomorrow) return '내일 상장';
  if (ipo.sub_end === todayIso && ipo.sub_start && ipo.sub_start <= todayIso) return '오늘 마감';
  if (ipo.sub_start === todayIso) return '오늘 청약 시작';
  return null;
}

// The listing days (sell days) of the stocks the user applied for, inside one month: shown on the subscription calendar
// as one-day "상장" marks. Sorted by date, then stock number.
export function listingMarks(ipos, applied, year, month) {
  const [first, last] = bounds(year, month);
  return ipos
    .filter(i => applied.has(i.no) && i.listing_date && i.listing_date >= first && i.listing_date <= last)
    .map(i => ({ no: i.no, name: i.name, date: i.listing_date, listed: i.first_close != null }))
    .sort((a, b) => a.date.localeCompare(b.date) || a.no - b.no);
}
