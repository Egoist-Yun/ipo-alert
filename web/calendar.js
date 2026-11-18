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
  if (ipo.inst_competition == null) return { text: '대기 중', tone: 'wait' };
  const flags = ipo.flag_count ?? 0;
  const unknown = ipo.unknown_count ?? 0;
  if (ipo.warning === 'strong') return { text: '강한 하락 경고', tone: 'risk' };
  if (ipo.warning === 'warn') return { text: '하락 경고', tone: 'risk' };
  const p = ipo.prediction || {};
  const warn = p.open_down ? p.open_down.warn : (p.prob && p.prob.warn);
  if (warn) return { text: '하락 경고', tone: 'risk' };
  if (flags > 0) return { text: `⚠ ${flags}`, tone: 'risk' };
  if (unknown >= 2) return { text: `확인 불가 ${unknown}`, tone: 'wait' };
  return { text: unknown ? `신호 없음 · 확인 불가 ${unknown}` : '신호 없음', tone: '' };
}

export function staleHours(updatedAt, nowMs) {
  const t = Date.parse(updatedAt);
  return Number.isNaN(t) ? null : Math.floor((nowMs - t) / 3600000);
}

export function listTitle(year, month, count) {
  return `${month}월 청약 목록 · ${count ? `${count}개` : '없음'}`;
}

const OPEN_KEY = 'ipo.listOpen';

export function readOpen(storage) {
  try {
    return storage?.getItem(OPEN_KEY) !== '0';
  } catch (e) {
    return true;
  }
}

export function saveOpen(storage, open) {
  try {
    storage?.setItem(OPEN_KEY, open ? '1' : '0');
  } catch (e) { /* storage can be blocked; the list still opens and closes */ }
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
