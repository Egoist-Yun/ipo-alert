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
    withdrawn: !!i.withdrawn,
  }));
}

export function listForMonth(ipos, year, month) {
  return overlapping(ipos, year, month).sort((a, b) => a.sub_start.localeCompare(b.sub_start) || a.no - b.no);
}

export function badgeInfo(ipo) {
  if (ipo.withdrawn) return { text: '철회', tone: 'done' };  // the offering was called off: grey, nothing else applies
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
  const running = i => i.first_close == null && i.sub_end >= todayIso && !i.withdrawn;  // a withdrawn offering is never "running"
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

// Whether the detail screen offers the apply/unapply button: not for a listed stock; a withdrawn stock only to take the mark off.
export function showApplyButton(ipo, applied) {
  if (ipo.first_close != null) return false;
  return !ipo.withdrawn || applied.has(ipo.no);
}

// Local alarm for each stock the user marked as applied: 08:30 KST on its listing day (pre-market orders open then).
// Pure: the app schedules exactly this list and cancels anything else it had scheduled.
export function listingAlarms(ipos, applied, nowIso) {
  const now = Date.parse(nowIso);
  if (Number.isNaN(now)) return [];
  return ipos
    .filter(i => applied.has(i.no) && !i.withdrawn && /^\d{4}-\d{2}-\d{2}$/.test(i.listing_date || ''))
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
// A one-day continuation piece (the bar began in an earlier week) carries the name too: the bar's ellipsis cuts what does not fit.
export function barLabel({ name, risk, applied }) {  // a withdrawn stock is shown by tone (grey) and strikethrough, not by words
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
  if (ipo.first_close != null || ipo.withdrawn) return null;
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
    .filter(i => applied.has(i.no) && !i.withdrawn && i.listing_date && i.listing_date >= first && i.listing_date <= last)
    .map(i => ({ no: i.no, name: i.name, date: i.listing_date, listed: i.first_close != null,
      risk: i.first_close == null && badgeInfo(i).tone === 'risk' }))  // a decline warning must stay visible on the day of selling
    .sort((a, b) => a.date.localeCompare(b.date) || a.no - b.no);
}

// The colour class of a calendar bar: colour only for what is still ahead. A subscription that is over (sub_end before
// today, KST date strings) or a stock that has listed is "done" (grey: past). A stock still to come is red when it has a
// decline warning (the deadline day itself still counts as coming) and blue (empty class) otherwise.
export function barTone(ipo, todayIso) {
  if (ipo.withdrawn || ipo.first_close != null || (ipo.sub_end && ipo.sub_end < todayIso)) return 'done';
  return badgeInfo(ipo).tone === 'risk' ? 'risk' : '';
}

// ---- Basic offering information for the detail screen ----
const fmtN = n => Number(n).toLocaleString('ko-KR');
const monthDay = iso => `${Number(iso.slice(5, 7))}/${Number(iso.slice(8, 10))}`;
// The data is in million KRW: 100 million = 1억. Under 1억 one decimal is kept; nothing prints as "-0".
const eok = mil => {
  const v = mil / 100;
  if (Math.abs(v) < 1) {
    const r = Number(v.toFixed(1));
    return r === 0 ? '0억 원' : `${r}억 원`;
  }
  return `${fmtN(Math.round(v))}억 원`;
};
const UNKNOWN = '확인 불가';

// The three facts needed to subscribe: price (with the band), the minimum amount, the refund day. Values that are not known
// say 확인 불가 and are never guessed (no assumed deposit rate). The minimum assumes 10 shares: the page does not show it.
// A text cut at " · " so each piece can be kept whole on one line (the screen wraps only at the dots).
export function splitSegments(text) {
  return String(text == null ? '' : text).split(' · ');
}

// The folded "공모 정보" rows: only what is known (a missing value leaves its row out). Amounts in 억 원, no colour for a loss.
export function offerInfoRows(ipo) {
  const rows = [];
  if (ipo.offer_amount_mil != null) rows.push({ k: '공모금액', v: eok(ipo.offer_amount_mil) });
  if (ipo.total_shares != null) {
    let retail = '';
    if (ipo.retail_shares != null && ipo.retail_shares_high != null) retail = ` · 일반 ${fmtN(ipo.retail_shares)}~${fmtN(ipo.retail_shares_high)}주`;  // still a range: no percentage
    else if (ipo.retail_shares != null) retail = ` · 일반 ${fmtN(ipo.retail_shares)}주 (${Number((ipo.retail_shares / ipo.total_shares * 100).toFixed(1))}%)`;
    rows.push({ k: '공모주식', v: `총 ${fmtN(ipo.total_shares)}주${retail}` });
  }
  for (const b of ipo.brokers || []) {
    if (b.shares == null) continue;
    const nums = String(b.limit_text || '').match(/\d[\d,]*/g) || [];
    const limits = nums.map(n => Number(n.replace(/,/g, '')));
    const limit = limits.length >= 2 ? `${fmtN(Math.min(...limits))}~${fmtN(Math.max(...limits))}`
      : limits.length === 1 ? fmtN(limits[0]) : (b.limit_max != null ? fmtN(b.limit_max) : null);
    rows.push({ k: b.name, v: `${fmtN(b.shares)}주${limit ? ` · 한도 ${limit}주` : ''}` });
  }
  if (ipo.industry) rows.push({ k: '업종', v: ipo.industry });
  if (ipo.revenue_mil != null) rows.push({ k: '매출액', v: eok(ipo.revenue_mil) });
  if (ipo.net_income_mil != null) rows.push({ k: '순이익', v: eok(ipo.net_income_mil) });
  if (ipo.demand_start && ipo.demand_end) rows.push({ k: '수요예측', v: `${monthDay(ipo.demand_start)}~${monthDay(ipo.demand_end)}` });
  if (ipo.inst_count != null) rows.push({ k: '참여 기관', v: `${fmtN(ipo.inst_count)}곳` });
  if (ipo.retail_competition != null) rows.push({ k: '일반청약 경쟁률', v: `${fmtN(Number(ipo.retail_competition.toFixed(2)))}:1` });
  return rows;
}

// Lays out one week of the subscription calendar: bars (multi-day) and the one-day listing marks of the stocks I applied for.
// Every lane keeps a 7-cell occupancy row. Bars go first, in start-day order, into the topmost lane where all their cells are
// free (the same result as the older "last column per lane" rule). Then each mark takes the topmost lane whose day cell is free
// (a new lane if none), then runs right over the free cells of that lane, up to the day before the next mark's day.
export function layoutWeek(barSegs, markSegs) {
  const lanes = [];
  const newLane = () => { lanes.push(Array(7).fill(false)); return lanes.length - 1; };
  const free = (lane, c0, c1) => { for (let c = c0; c <= c1; c++) if (lane[c]) return false; return true; };
  const items = [];
  for (const seg of [...barSegs].sort((a, b) => a.c0 - b.c0 || a.c1 - b.c1)) {
    let li = lanes.findIndex(l => free(l, seg.c0, seg.c1));
    if (li < 0) li = newLane();
    for (let c = seg.c0; c <= seg.c1; c++) lanes[li][c] = true;
    items.push({ seg, lane: li, c0: seg.c0, c1: seg.c1 });
  }
  // A listing mark starts in its own day cell and runs right over the free cells of its lane (the name needs the room), but
  // never past the next mark's day (so two marks in one week can share a lane) and never past the last column.
  const marks = [...markSegs].sort((a, b) => a.c0 - b.c0);
  marks.forEach((seg, k) => {
    let li = lanes.findIndex(l => !l[seg.c0]);
    if (li < 0) li = newLane();
    const next = marks.slice(k + 1).find(m => m.c0 > seg.c0);
    const limit = next ? next.c0 - 1 : 6;
    let c1 = seg.c0;
    while (c1 < limit && !lanes[li][c1 + 1]) c1++;
    for (let c = seg.c0; c <= c1; c++) lanes[li][c] = true;
    items.push({ seg, lane: li, c0: seg.c0, c1 });
  });
  return { items, lanes: lanes.length };
}

// ---- Detail screen: verdict header, signal table, fact grid ----

const moodDenominator = rule => { const m = /\/(\d+)/.exec(rule || ''); return m ? Number(m[1]) : null; };
const oneDecimal = v => Number(Number(v).toFixed(1));

function signalText(s) {
  const v = s.value;
  if (v == null) return UNKNOWN;
  if (s.key === 'price_position') return s.flag === true ? '하단 확정' : `${fmtN(v)}원`;
  if (s.key === 'inst_competition') return `${Math.round(v)}대 1`;
  if (s.key === 'mood') {
    const n = moodDenominator(s.rule);
    return n ? `${Math.round(v * n)}/${n} 하락` : `${Math.round(v * 100)}%`;
  }
  return `${v}%`;
}

// The signal table rows: risk first (largest severity first), then unknown, then normal. The rule column comes from the data
// (ipo/signals.py is its only source); data written before the rule existed says 확인 불가 there.
export function signalRows(ipo) {
  const rows = (ipo.signals || []).map((s, i) => ({
    key: s.key, label: s.label, text: signalText(s), rule: s.rule || UNKNOWN, severity: s.severity ?? null, i,
    tone: s.flag === true ? 'risk' : s.flag == null ? 'unknown' : 'ok',
  }));
  const order = { risk: 0, unknown: 1, ok: 2 };
  rows.sort((a, b) => order[a.tone] - order[b.tone] || (a.tone === 'risk' ? (b.severity ?? -1) - (a.severity ?? -1) : 0) || a.i - b.i);
  return rows.map(({ i, ...r }) => r);
}

const EVIDENCE = {
  below_band: s => `기관 주문 ${Math.round(s.value)}%⁠가 희망가 하단 아래`,  // ⁠ (word joiner): the line may not break between the % and the particle
  lockup: s => `의무보유확약 ${oneDecimal(s.value)}%`,
  inst_competition: s => `기관 경쟁률 ${Math.round(s.value)}대 1`,
  price_position: () => '공모가가 희망 하단에 확정',
  float: s => `유통가능물량 ${Math.round(s.value)}%`,
  mood: s => { const n = moodDenominator(s.rule); return n ? `최근 공모주 ${n}개 중 ${Math.round(s.value * n)}개 하락` : '최근 공모주 시장 분위기가 나빠요'; },
};

// One line saying why: the two most severe risk signals.
export function evidenceLine(ipo) {
  const flagged = new Map((ipo.signals || []).map(s => [s.key, s]));
  return signalRows(ipo).filter(r => r.tone === 'risk').slice(0, 2)
    .map(r => EVIDENCE[r.key] ? EVIDENCE[r.key](flagged.get(r.key)) : r.label).join(', ');
}

// How often this kind of warning was right in the past, as a sentence.
export function trustText(w, strong) {
  const caught = strong ? w.strong_caught : w.caught;
  const warned = strong ? w.strong_warned : w.warned;
  if (caught != null && warned != null) return `과거 이 경고 ${warned}번 중 ${caught}번이 실제로 하락했어요`;
  const p = strong ? w.strong_precision : w.precision;
  return p != null ? `과거 이 경고의 ${Math.round(p * 100)}%가 실제로 하락했어요` : null;
}

const LEVEL_TEXT = { strong: '강한 하락 경고', warn: '하락 경고' };
const levelWas = level => (level ? `${LEVEL_TEXT[level]}였어요` : '경고 없음이었어요');

// After the subscription closes the judgment follows the open-price model and can differ from the pre-subscription one:
// two lines say so (shown only when both are known and differ; data from before warning_pre existed shows nothing).
function judgmentShift(ipo) {
  const od = (ipo.prediction || {}).open_down;
  if (!od || ipo.warning_pre === undefined) return null;
  if ((ipo.warning || null) === (ipo.warning_pre || null)) return null;
  const retail = ipo.retail_competition != null ? `일반청약 경쟁률 ${Math.round(ipo.retail_competition)}대 1이` : '일반청약 경쟁률이';
  return [`시초가 하락 확률 ${Math.round(od.p_down * 100)}%, 경고 기준 ${Math.round(od.threshold * 100)}%`,
    `청약 전 판정은 ${levelWas(ipo.warning_pre)}. ${retail} 반영돼 바뀌었어요`];
}

// The verdict header: kind 'warn' (red box), 'ok' (plain line), 'wait' (no demand forecast yet); null for listed stocks and spacs.
export function verdictHeader(ipo) {
  if (ipo.withdrawn) return { kind: 'wait', title: '청약이 철회됐어요', why: '', trust: null, conflict: false, shift: null };
  if (ipo.is_spac || ipo.first_close != null) return null;
  const conflict = !ipo.warning && !!(ipo.prediction || {}).conflict;
  if (ipo.inst_competition == null) return { kind: 'wait', title: '기관 수요예측 결과가 아직 없어요', why: '', trust: null, conflict: false, shift: null };
  const shift = judgmentShift(ipo);
  if (ipo.warning) {
    const p = ipo.prediction || {};
    return { kind: 'warn', title: ipo.warning === 'strong' ? '강한 하락 경고' : '하락 경고', why: evidenceLine(ipo),
      trust: trustText(p.open_down || p.prob || {}, ipo.warning === 'strong'), conflict: false, shift };
  }
  // no warning: the risk signals are not the reason for anything here, only counted
  const risks = signalRows(ipo).filter(r => r.tone === 'risk').length;
  const why = shift || !risks ? '' : `위험 신호 ${risks}개, 모델 기준으로는 경고 아님`;
  return { kind: 'ok', title: '하락 경고 없음', why, trust: null, conflict, shift };
}

// The four numbers needed to subscribe (stocks not yet listed). today: true marks the sub text for the "today" colour.
export function factGrid(ipo, todayIso) {
  const band = ipo.band_low && ipo.band_high
    ? (ipo.band_low === ipo.band_high ? `${fmtN(ipo.band_low)}원` : `${fmtN(ipo.band_low)}~${fmtN(ipo.band_high)}원`) : null;
  const price = ipo.final_price
    ? { k: '공모가', v: `${fmtN(ipo.final_price)}원`, s: band ? `희망 ${band}` : '', unknown: false, today: false }
    : band ? { k: '공모가', v: band, s: '확정 전', unknown: false, today: false }
      : { k: '공모가', v: UNKNOWN, s: '', unknown: true, today: false };

  const unit = ipo.final_price || ipo.band_high;
  const deposit = unit && ipo.retail_deposit_pct != null
    ? { k: '최소 증거금', v: `${fmtN(Math.round(10 * unit * ipo.retail_deposit_pct / 100))}원`,
        s: `10주 기준, 증거금 ${ipo.retail_deposit_pct}%${ipo.final_price ? '' : ', 희망 상단 기준'}`, unknown: false, today: false }
    : { k: '최소 증거금', v: UNKNOWN, s: '', unknown: true, today: false };

  const ds = dayStatus(ipo, todayIso);
  let sub = '예정';
  if (ipo.withdrawn) sub = '철회됨';
  else if (ds) sub = ds;
  else if (ipo.sub_end && ipo.sub_end < todayIso) sub = '마감됨';
  else if (ipo.sub_start && ipo.sub_start <= todayIso) sub = '청약 중';
  const period = ipo.sub_start && ipo.sub_end ? `${monthDay(ipo.sub_start)}~${monthDay(ipo.sub_end)}` : null;
  const subscription = { k: '청약', v: period || UNKNOWN, s: period ? sub : '', unknown: !period, today: !!ds };

  const listing = { k: '상장 · 환불', v: ipo.listing_date ? monthDay(ipo.listing_date) : '미정',
    s: ipo.refund_date ? `환불 ${monthDay(ipo.refund_date)}` : '환불일 확인 불가', unknown: false, today: false };
  return [price, deposit, subscription, listing];
}

// A listed stock: the result instead of the verdict (price, open, first close with their changes, listing day).
export function resultGrid(ipo) {
  const base = ipo.final_price;
  const change = p => `${p >= base ? '+' : ''}${((p / base - 1) * 100).toFixed(0)}%`;
  const cells = [{ k: '공모가', v: `${fmtN(base)}원`, s: '' }];
  if (ipo.open_price != null) cells.push({ k: '시초가', v: `${fmtN(ipo.open_price)}원`, s: change(ipo.open_price) });
  cells.push({ k: '첫날 종가', v: `${fmtN(ipo.first_close)}원`, s: change(ipo.first_close) });
  if (ipo.listing_date) cells.push({ k: '상장일', v: monthDay(ipo.listing_date), s: '' });
  return cells;
}


// ---- Today strip, folded past weeks ----
const addDays = (iso, n) => new Date(Date.parse(`${iso}T00:00:00Z`) + n * 86400000).toISOString().slice(0, 10);

// The rows under the title: what is on today, the next subscriptions, my next listing day. Independent of the month shown.
// A row is {k, v, sub, risk, more, no, muted} (`risk`: the sub text is a warning, drawn red): `no` is the stock the row opens (null: not a button). Withdrawn stocks are left out.
export function todayStrip(ipos, applied, todayIso) {
  const live = ipos.filter(i => !i.withdrawn);
  const rows = [];

  const todayRank = i => {
    if (i.first_close != null) return 0;
    if (i.listing_date === todayIso) return 3;
    if (i.sub_end === todayIso && i.sub_start && i.sub_start <= todayIso) return 2;
    if (i.sub_start === todayIso) return 1;
    return 0;
  };
  const SUB = { 3: '오늘 상장', 2: '오늘 마감', 1: '오늘 청약 시작' };
  const todays = live.filter(i => todayRank(i) > 0)
    .sort((a, b) => todayRank(b) - todayRank(a) || a.no - b.no);
  if (todays.length) {
    rows.push({ k: '오늘', v: todays[0].name, sub: SUB[todayRank(todays[0])], risk: false, more: todays.length > 1 ? `외 ${todays.length - 1}건` : '', no: todays[0].no, muted: false });
  }

  const upcoming = live.filter(i => i.sub_start && i.sub_start > todayIso)
    .sort((a, b) => a.sub_start.localeCompare(b.sub_start) || a.no - b.no);
  if (upcoming.length) {
    const first = upcoming[0];
    const group = upcoming.filter(i => i.sub_start <= addDays(first.sub_start, 7));
    const lastEnd = group.map(i => i.sub_end || i.sub_start).sort().pop();
    rows.push({ k: '다음 청약', v: `${monthDay(first.sub_start)} ${first.name}`, sub: '',
      more: group.length > 1 ? `외 ${group.length - 1}건, ${monthDay(lastEnd)}까지` : '', no: first.no, muted: false });
  }

  const waiting = live.filter(i => applied.has(i.no) && i.first_close == null);
  const dated = waiting.filter(i => i.listing_date && i.listing_date >= todayIso)
    .sort((a, b) => a.listing_date.localeCompare(b.listing_date) || a.no - b.no);
  if (!waiting.length) rows.push({ k: '내 상장일', v: '신청 표시한 종목이 없어요', sub: '', risk: false, more: '', no: null, muted: true });
  else if (!dated.length) rows.push({ k: '내 상장일', v: '상장일 미정', sub: '', risk: false, more: '', no: waiting[0].no, muted: true });
  else {
    const risky = dated.filter(i => badgeInfo(i).tone === 'risk').length;   // a decline warning must stay visible on the day of selling
    rows.push({ k: '내 상장일', v: `${monthDay(dated[0].listing_date)} ${dated[0].name}`, sub: risky ? `⚠ 하락 경고 ${risky}건` : '', risk: risky > 0,
      more: dated.length > 1 ? `외 ${dated.length - 1}건` : '', no: dated[0].no, muted: false });
  }
  return rows;
}

// The weeks of the shown month that are over (their last real day is before today): folded into one line. Only for the month
// that contains today. Returns how many weeks and the date range they cover.
export function pastWeeks(weeks, todayIso, year, month) {
  const none = { count: 0, from: null, to: null };
  if (todayIso.slice(0, 7) !== `${year}-${pad(month)}`) return none;
  const over = [];
  for (const week of weeks) {
    const real = week.filter(Boolean);
    if (!real.length || real[real.length - 1] >= todayIso) break;
    over.push(real);
  }
  if (!over.length) return none;
  return { count: over.length, from: over[0][0], to: over[over.length - 1].slice(-1)[0] };
}

// How many different calendar bars touch a date range (for the "지난 청약 N건" line).
export function countBarsIn(bars, from, to) {
  return bars.filter(b => b.start <= to && b.end >= from).length;
}

// ---- App push notifications (FCM topic) ----
// The panel on the record screen: only the notification permission matters (the app subscribes to the topic by itself).
// perm: the plugin's `receive` permission ('granted', 'denied', 'prompt' ...) or null while not known yet (no panel).
export function pushPanelState(perm) {
  if (perm == null) return null;
  if (perm !== 'granted') return { status: 'off', text: '알림 권한이 꺼져 있어요. 휴대폰 설정에서 공모주 달력 알림을 켜 주세요' };
  return { status: 'on', text: '공모주 알림을 받고 있어요' };
}

// The stock a push opens: the push carries the site link ".../#<no>" in data.url. Anything else: null.
export function pushTargetNo(url) {
  const m = /#(\d+)$/.exec(String(url || '').trim());
  return m ? Number(m[1]) : null;
}

// How many of my listing marks (see listingMarks) fall in a date range: shown on the folded past-weeks line.
export function countMarksIn(marks, from, to) {
  return marks.filter(m => m.date >= from && m.date <= to).length;
}
