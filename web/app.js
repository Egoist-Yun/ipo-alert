import { monthGrid, barsForMonth, badgeInfo, staleHours, needsRefresh, recordRows, parseRoute, groupForList, listingLabel, readApplied, saveApplied, appliedAvailable, toggleApplied, listingAlarms, barLabel, markToast, dayStatus, listingMarks, barTone, offerInfoRows, layoutWeek, splitSegments, signalRows, verdictHeader, factGrid, resultGrid, todayStrip, pastWeeks, countBarsIn, showApplyButton } from './calendar.js';
import { brokerLinks, showBrokerButtons, isAndroid, brokerAction, isNativeApp } from './brokers.js';

const $ = id => document.getElementById(id);
const loadedAt = Date.now();
const state = { ipos: [], accuracyNote: null, year: 0, month: 0, selected: null, ledger: null, routed: false, applied: new Set(), canApply: false, alarmOff: false, doneOpen: false, pastOpen: false, pastKey: '' };

function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

const md = iso => `${Number(iso.slice(5, 7))}/${Number(iso.slice(8, 10))}`;
const won = n => `${Number(n).toLocaleString('ko-KR')}원`;
const pct = (r, digits = 0) => `${r >= 0 ? '+' : ''}${(r * 100).toFixed(digits)}%`;

function kstToday() {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(new Date());
  return parts; // YYYY-MM-DD
}

const tone = ipo => badgeInfo(ipo).tone;
const badgeText = ipo => badgeInfo(ipo).text;

// Screens are chosen by the URL hash (#<no> detail, #record, none = list). Moves made inside the app push a history
// entry marked {app: true}, so "← 달력" and the phone's back key return to the list exactly as it was left.
function go(hash) {
  history.pushState({ app: true }, '', hash ? `#${hash}` : location.pathname + location.search);
  route();
}

function select(no) { go(String(no)); }

function goBack() {
  if (history.state && history.state.app) { history.back(); return; }
  history.replaceState(null, '', location.pathname + location.search);  // opened by a link: no list entry before it
  route();
}

function renderCalendar() {
  const { year, month } = state;
  $('month').textContent = `${year}년 ${month}월`;
  const bars = barsForMonth(state.ipos, year, month);
  const marks = listingMarks(state.ipos, state.applied, year, month);  // listing days of the stocks I applied for
  const today = kstToday();
  const weeks = $('weeks');
  weeks.replaceChildren();
  const grid = monthGrid(year, month);
  // The weeks of the shown month that are already over fold into one line (only in the month that contains today).
  if (state.pastKey !== `${year}-${month}`) { state.pastKey = `${year}-${month}`; state.pastOpen = false; }
  const past = pastWeeks(grid, today, year, month);
  if (past.count) {
    const n = countBarsIn(bars, past.from, past.to);
    const fold = h('button', { class: `past${state.pastOpen ? ' open' : ''}`, type: 'button', 'aria-expanded': state.pastOpen ? 'true' : 'false',
      onclick: () => { state.pastOpen = !state.pastOpen; renderCalendar(); $('weeks').querySelector('.past')?.focus(); } },
      h('span', {}, `${md(past.from)}~${md(past.to)} 지난 청약 `, h('b', {}, `${n}건`)));
    weeks.append(fold);
  }
  for (const [wi, week] of grid.entries()) {
    if (wi < past.count && !state.pastOpen) continue;
    const real = week.filter(Boolean);
    const lo = real[0], hi = real[real.length - 1];
    const barSegs = bars
      .map(b => ({ b, s: b.start < lo ? lo : b.start, e: b.end > hi ? hi : b.end }))
      .filter(x => x.s <= x.e)
      .map(x => ({ ...x, c0: week.indexOf(x.s), c1: week.indexOf(x.e) }));
    // A listing mark is "dot + name": it starts in its own listing-day cell and runs right over the free cells (layoutWeek), placed after the bars.
    const markSegs = marks.filter(m => week.includes(m.date)).map(m => ({ mark: m, c0: week.indexOf(m.date) }));
    const { items } = layoutWeek(barSegs, markSegs);
    const el = h('div', { class: 'week' },
      week.map(d => h('div', { class: `day${d === today ? ' today' : ''}${d ? '' : ' empty'}` }, d ? Number(d.slice(8)) : '0')));
    for (const { seg, lane, c0, c1 } of items) {
      const place = `grid-column:${c0 + 1} / ${c1 + 2};grid-row:${lane + 2}`;
      if (seg.mark) {
        const m = seg.mark;
        const mipo = state.ipos.find(i => i.no === m.no);
        const now = dayStatus(mipo, today) === '오늘 상장';
        el.append(h('button', {
          class: `bar mark${m.listed ? ' done' : ''}${now ? ' now' : ''}${state.selected === m.no ? ' selected' : ''}`,
          type: 'button',
          style: place,
          'aria-label': `${m.name} 상장일 ${md(m.date)}, 청약 신청함`,
          onclick: () => select(m.no),
        }, m.name));  // too long for the free cells: the bar's ellipsis cuts it
        continue;
      }
      const ipo = state.ipos.find(i => i.no === seg.b.no);
      // A one-day piece of a bar that began in an earlier week has no room for text: colour only.
      const continuationOneDay = seg.s > seg.b.start && seg.c0 === seg.c1;
      const bt = barTone(ipo, today);  // a subscription that is over is "done" (and carries no warning mark)
      const label = barLabel({ name: seg.b.name, risk: bt === 'risk', applied: state.applied.has(ipo.no), continuationOneDay });
      // A bar that crosses a week edge is cut square on that side and runs to the cell edge: it reads as "continues".
      const contL = seg.s > seg.b.start ? ' cont-l' : '';
      const contR = seg.e < seg.b.end ? ' cont-r' : '';
      el.append(h('button', {
        class: `bar ${bt}${seg.b.withdrawn ? ' withdrawn' : ''}${contL}${contR}${state.selected === seg.b.no ? ' selected' : ''}`,
        type: 'button',
        style: place,
        'aria-label': `${state.applied.has(ipo.no) ? '청약 신청함, ' : ''}${seg.b.withdrawn ? '청약 철회, ' : ''}${seg.b.name}, ${badgeText(ipo)}, 청약 ${md(ipo.sub_start)}~${md(ipo.sub_end)}`,
        onclick: () => select(seg.b.no),
      }, label));
    }
    weeks.append(el);
  }
}

function localStore() {
  try { return window.localStorage; } catch (e) { return undefined; }
}

function listRow(ipo, { big, applied } = {}) {
  const sub = `청약 ${md(ipo.sub_start)}~${md(ipo.sub_end)}`;
  const listed = ipo.first_close != null;
  // Applied rows: the stock name leads, the sell day (listing date) is the second line; the subscription period is left out.
  // A today/tomorrow note (오늘 마감, 내일 상장 ...) comes first; for applied rows a listing note takes the place of the date.
  const ds = dayStatus(ipo, kstToday());
  const rest = ipo.withdrawn && big ? '청약 철회 · 상장 취소'
    : big ? `${ds && ds.endsWith('상장') ? '' : `${listingLabel(ipo)} · `}시초가 매도`
    : (listed || !ipo.listing_date ? sub : `${sub} · ${listingLabel(ipo)}`);
  const title = `${applied ? '✓ ' : ''}${ipo.name}`;
  return h('button', { class: 'row', type: 'button', onclick: () => select(ipo.no) },
    h('span', {}, h('span', { class: `name${big ? ' big' : ''}` }, title),
      h('span', { class: 'meta' }, ds && h('span', { class: 'today' }, ds), ds && ' · ', segs(rest))),
    h('span', { class: `badge ${tone(ipo)}` }, badgeText(ipo)));
}

function renderList() {
  const g = groupForList(state.ipos, state.year, state.month, kstToday(), state.applied);
  const parts = [];
  // The applied group is the first of the list (just below the calendar), whatever month is shown.
  if (g.applied.length) {
    parts.push(h('section', { class: 'group' }, h('h4', {}, `신청한 청약 · ${g.applied.length}개`), g.applied.map(i => listRow(i, { big: true }))));
  }
  if (g.upcoming.length) {
    parts.push(h('section', { class: 'group' }, h('h4', {}, `청약 예정·진행 중 · ${g.upcoming.length}개`), g.upcoming.map(i => listRow(i))));
  }
  if (g.done.length) {
    // Closed on every app start; opening it keeps it open only while the app stays open (month changes, back from a detail).
    const box = h('details', { class: 'drop', open: state.doneOpen },
      h('summary', {}, h('span', {}, `청약 끝 · ${g.done.length}개`)),
      g.done.map(i => listRow(i, { applied: state.applied.has(i.no) })));
    box.addEventListener('toggle', () => { state.doneOpen = box.open; });
    parts.push(box);
  }
  if (!g.upcoming.length && !g.done.length) parts.push(h('p', { class: 'msg' }, `${state.month}월에는 청약이 없어요.`));
  $('list').replaceChildren(...parts);
}

// A short message that fades in at the bottom and goes away by itself (extension: TDS lists a Toast but gives no spec here).
let toastTimer = 0;
function showToast(text) {
  let el = document.getElementById('toast');
  if (!el) {
    el = h('div', { id: 'toast', class: 'toast', role: 'status', 'aria-live': 'polite' });
    document.body.append(el);
  }
  el.textContent = text;
  void el.offsetWidth;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 3000);
}

// Listing-day alarm (Android app only; the notification plugin exists only in the native shell). Everything stays on the device.
const notifier = () => (isNativeApp(window) ? window.Capacitor?.Plugins?.LocalNotifications : undefined);

async function ensureAlarmPermission() {
  const LN = notifier();
  if (!LN) return true;
  try {
    let perm = await LN.checkPermissions();
    if (perm.display !== 'granted' && perm.display !== 'denied') perm = await LN.requestPermissions();
    state.alarmOff = perm.display !== 'granted';
  } catch (e) { console.error(e); }
  return !state.alarmOff;
}

// Schedule exactly the alarms listingAlarms() wants and cancel any other one this app had scheduled.
async function syncListingAlarms() {
  const LN = notifier();
  if (!LN) return;
  try {
    const wanted = listingAlarms(state.ipos, state.applied, new Date().toISOString());
    const pending = (await LN.getPending()).notifications || [];
    const stale = pending.filter(n => !wanted.some(w => w.id === n.id));
    if (stale.length) await LN.cancel({ notifications: stale.map(n => ({ id: n.id })) });
    if (!wanted.length) return;
    const perm = await LN.checkPermissions();
    state.alarmOff = perm.display !== 'granted';
    if (state.alarmOff) return;
    // allowWhileIdle, not an exact alarm (isExactNotification defaults to true in the plugin, which would open the system
    // "alarms & reminders" settings): it may arrive a few minutes late, but needs no special permission.
    await LN.schedule({ notifications: wanted.map(w => ({ id: w.id, title: w.title, body: w.body, extra: { no: w.no }, isExactNotification: false, schedule: { at: new Date(w.at), allowWhileIdle: true } })) });
  } catch (e) { console.error(e); }
}

function alarmNodes(ipo) {
  if (!notifier() || !state.applied.has(ipo.no) || !ipo.listing_date || ipo.first_close != null) return [];
  return state.alarmOff ? [h('p', { class: 'p' }, '알림이 꺼져 있어요')] : [];
}

function appliedNodes(ipo) {
  if (!state.canApply || !showApplyButton(ipo, state.applied)) return [];
  const on = state.applied.has(ipo.no);
  return [h('button', {
    class: 'btn-large', type: 'button', 'aria-pressed': on ? 'true' : 'false',
    onclick: async () => {
      state.applied = toggleApplied(state.applied, ipo.no);
      saveApplied(localStore(), state.applied);
      renderDetail();
      if (state.applied.has(ipo.no)) await ensureAlarmPermission();  // asked the first time a stock is marked
      await syncListingAlarms();
      renderDetail();
      // Tell what marking did: confirmed alarm, off, not available in a browser, or promised for a stock without a listing date.
      if (state.applied.has(ipo.no)) {
        const hasAlarm = listingAlarms(state.ipos, state.applied, new Date().toISOString()).some(x => x.no === ipo.no);
        const text = markToast({ native: !!notifier(), alarmOff: state.alarmOff, hasAlarm, hasListingDate: !!ipo.listing_date });
        if (text) showToast(text);
      }
    },
  }, on ? '신청 표시 취소' : '청약 신청했어요')];
}

function brokerNodes(ipo) {
  if (ipo.withdrawn || !showBrokerButtons(ipo, kstToday())) return [];
  if (!isAndroid(navigator.userAgent)) {
    return [];
  }
  const links = brokerLinks(ipo.underwriters);
  if (!links.length) return [];
  return [h('div', { class: 'brokers' }, links.map(l => brokerButton(l)))];
}

async function launchBroker(action) {
  const launcher = window.Capacitor?.Plugins?.AppLauncher;
  try {
    const res = await launcher.openUrl({ url: action.url });
    if (res && res.completed) return;
  } catch (e) { /* fall through to the Play Store */ }
  window.location.href = action.fallback;
}

const brokerLabel = link => [h('span', { class: 'nm' }, link.name), h('span', { class: 'sub' }, '앱 열기')];

function brokerButton(link) {
  const action = brokerAction(link, isNativeApp(window));
  if (action.type === 'launch') {
    return h('a', { class: 'broker', href: action.fallback, onclick: ev => { ev.preventDefault(); launchBroker(action); } }, brokerLabel(link));
  }
  return h('a', { class: 'broker', href: action.href }, brokerLabel(link));
}

// A text whose "·" pieces each stay on one line: the line may break only at a dot. Without a dot it is plain text.
function segs(text) {
  const parts = splitSegments(text);
  if (parts.length < 2) return text;
  return parts.flatMap((p, i) => [i ? ' · ' : '', h('span', { class: 'seg' }, p)]);
}

function kv(k, v, cls) {
  return h('div', { class: 'kv' }, h('span', { class: 'k' }, k), h('span', { class: `v ${cls || ''}` }, segs(v)));
}

function renderDetail() {
  const box = $('detail');
  const ipo = state.ipos.find(i => i.no === state.selected);
  if (!ipo) { box.replaceChildren(); return; }

  const listed = ipo.first_close != null;
  const chips = [ipo.market, ...(ipo.underwriters || [])].filter(Boolean);
  const nodes = [h('h1', { class: 'name' }, ipo.name),
    h('div', { class: 'chips' }, chips.map(c => h('span', { class: 'badge' }, c)))];
  // conclusion -> action -> numbers -> evidence
  nodes.push(...(listed ? factNodes(resultGrid(ipo), 'result') : verdictNodes(ipo)));
  nodes.push(...appliedNodes(ipo), ...alarmNodes(ipo), ...brokerNodes(ipo));
  if (!listed) nodes.push(...factNodes(factGrid(ipo, kstToday()), 'subscribe'));
  // The rest of the offering information is folded (closed by default); rows without a value are not shown.
  const offerRows = offerInfoRows(ipo);
  if (offerRows.length) nodes.push(h('details', { class: 'drop' }, h('summary', {}, h('span', {}, '공모 정보')), offerRows.map(r => kv(r.k, r.v))));

  if (!ipo.is_spac && !ipo.withdrawn && ipo.inst_competition != null) {
    nodes.push(...signalNodes(ipo));
    nodes.push(...patternNodes(ipo));
    if (!listed) nodes.push(...modelNodes(ipo));
  }
  if (ipo.url) nodes.push(h('a', { class: 'btn-medium', href: ipo.url, target: '_blank', rel: 'noopener' }, '원문 보기'));
  box.replaceChildren(h('div', { class: 'panel' }, nodes));
}

// The conclusion comes first: a red box for a warning, a plain line otherwise.
function verdictNodes(ipo) {
  const v = verdictHeader(ipo);
  if (!v) return [];
  const box = h('div', { class: `verdict ${v.kind}` }, h('h2', {}, v.title),
    v.why && h('p', { class: 'why' }, v.why), v.trust && h('p', { class: 'trust' }, v.trust),
    v.shift && v.shift.map((t, i) => h('p', { class: i ? 'shift-note' : 'shift' }, t)));
  // no warning, but the signals and the price prediction disagree
  return [box, v.conflict && h('p', { class: 'p' }, '신호와 예측이 엇갈려요. 두 가지를 함께 보세요.')].filter(Boolean);
}

// A range like 18,000~25,000원 has no spaces: let it break after the "~" (never inside a number) when the cell is too narrow.
function breakAtTilde(text) {
  const parts = String(text).split('~');
  return parts.flatMap((p, i) => (i < parts.length - 1 ? [`${p}~`, h('wbr')] : [p]));
}

// A 2-column grid of big numbers (no cards): name, value, small note.
function factNodes(cells, kind) {
  return [h('section', { class: `facts ${kind}` }, cells.map(c => h('div', { class: 'fact' },
    h('p', { class: 'k' }, c.k),
    h('p', { class: `v${c.unknown ? ' unknown' : ''}` }, breakAtTilde(c.v)),
    c.s && h('p', { class: `s${c.today ? ' today' : ''}` }, c.s))))];
}

// The risk signals as a 3-column table: signal | this stock | the rule that makes it a risk.
function signalNodes(ipo) {
  const rows = signalRows(ipo);
  if (!rows.length) return [];
  const table = h('table', { class: 'sig' },
    h('thead', {}, h('tr', {}, h('th', {}, '신호'), h('th', {}, '이 종목'), h('th', {}, '위험 기준'))),
    h('tbody', {}, rows.map(r => h('tr', {}, h('td', {}, r.label),
      h('td', { class: r.tone === 'risk' ? 'hit' : r.tone === 'unknown' ? 'unk' : '' }, r.text),
      h('td', { class: 'rule' }, r.rule)))));
  return [h('section', { class: 'sec' }, h('h3', {}, '위험 신호 ', h('span', {}, `${rows.length}개 중 ${ipo.flag_count || 0}개`)), table)];
}

function patternNodes(ipo) {
  const list = ipo.patterns || [];
  if (!list.length) return [];
  const inner = [];
  const risks = list.filter(p => p.kind === 'risk');
  const safes = list.filter(p => p.kind === 'safe');
  for (const p of risks) {
    const rate = p.close_down != null ? `${(p.close_down * 100).toFixed(0)}%` : '-';
    const open = p.phase === 'post' && p.open_down != null ? ` · 시초가 ${(p.open_down * 100).toFixed(0)}%` : '';
    inner.push(kv(p.label, `하락 ${rate}${open} · ${p.n}개`, 'flag'));
  }
  for (const p of safes) {
    inner.push(kv(p.label, `하락 ${(p.close_down * 100).toFixed(0)}% · ${p.n}개`));
  }
  const worst = Math.max(0, ...risks.map(p => p.close_down || 0));
  const title = `과거 패턴 ${list.length}개${risks.length ? ` · 최대 하락 ${(worst * 100).toFixed(0)}%` : ''}`;
  return [h('details', { class: 'drop' }, h('summary', {}, h('span', {}, title)), inner)];
}

function probabilityNodes(ipo) {
  const p = ipo.prediction;
  if (!p || (!p.knn && !p.open && !p.close && !p.prob && !p.open_down)) {
    const why = p && p.accuracy
      ? '과거 기록으로 검증했을 때 기준보다 정확하지 않아서 보여주지 않아요.'
      : '비교할 과거 기록이 아직 부족해요.';
    return [h('p', { class: 'p' }, `예측을 만들지 못했어요. ${why}`)];
  }
  const nodes = [];
  if (p.prob) {
    nodes.push(h('h4', {}, '청약 전 모델: 공모가 아래로 끝날 확률'));
    nodes.push(kv('첫날 종가 기준', `${(p.prob.p_down * 100).toFixed(0)}%`, p.prob.warn ? 'flag' : ''));
  }
  if (p.open_down) {
    nodes.push(h('h4', {}, '청약 마감 후 참고: 시초가가 공모가 아래일 확률'));
    nodes.push(kv('일반청약 경쟁률 반영', `${(p.open_down.p_down * 100).toFixed(0)}%`, p.open_down.warn ? 'flag' : ''));
  }
  return nodes;
}

function referenceNodes(ipo) {
  const p = ipo.prediction;
  if (!p || (!p.open && !p.close && !p.knn)) return [];
  const inner = [];
  for (const [key, label] of [['open', '시초가 예상'], ['close', '첫날 종가 예상']]) {
    const e = p[key];
    if (!e) continue;
    inner.push(kv(`${label}${e.uses_retail ? ' · 일반청약 반영' : ''} (±${(e.mae * 100).toFixed(0)}%p)`, `${won(e.price)} (${pct(e.return)})`, e.return < 0 ? 'flag' : ''));
    if (e.price_low != null) inner.push(kv(`범위 · 과거 ${(e.range_coverage * 100).toFixed(0)}% 적중`, `${won(e.price_low)} ~ ${won(e.price_high)}`));
  }
  if (p.knn) {
    const k = p.knn;
    inner.push(h('p', { class: 'p' }, `비슷했던 과거 공모주 ${k.n}개 중 ${k.down_count}개가 첫날 공모가 아래로 마감했어요.`));
    inner.push(kv('비슷한 종목의 가운데 절반 범위', `${won(k.price_low)} ~ ${won(k.price_high)}`));
    inner.push(kv('가운데 값', pct(k.median)));
    for (const it of k.items) inner.push(kv(it.name, pct(it.return)));
  }
  const e = p.open || p.close;
  const title = e ? `참고: 가격 예측 (오차 ±${(e.mae * 100).toFixed(0)}%p)` : '참고: 비슷했던 과거 공모주';
  return [h('h4', {}, title), ...inner];
}

// Both model sections in one folded block.
function modelNodes(ipo) {
  const inner = [...probabilityNodes(ipo), ...referenceNodes(ipo)];
  return inner.length ? [h('details', { class: 'drop' }, h('summary', {}, h('span', {}, '모델 · 가격 예측 참고')), inner)] : [];
}

function renderRecord() {
  const ledger = state.ledger;
  const r = recordRows(ledger);
  if (!r) { $('record').replaceChildren(h('div', { class: 'panel' }, h('h4', {}, '실전 성적'), h('p', { class: 'p' }, '아직 기록이 없어요.'))); return; }
  const nodes = [h('h4', {}, `실전 성적 (${ledger.since.slice(5).replace('-', '/')} 이후 상장 전에 저장한 예측)`)];
  if (!r.rows.length) nodes.push(h('p', { class: 'p' }, '아직 저장된 예측이 없어요.'));
  for (const [label, value] of r.rows) nodes.push(kv(label, value));
  if (r.early) nodes.push(h('p', { class: 'p' }, '아직 판단하기 일러요.'));
  $('record').replaceChildren(h('div', { class: 'panel' }, nodes));
}

// The rows under the title: today, the next subscriptions, my next listing day (see todayStrip). Hidden when there is nothing.
function renderStrip() {
  const rows = todayStrip(state.ipos, state.applied, kstToday());
  const box = $('today-strip');
  box.hidden = !rows.length;
  box.replaceChildren(...rows.map(r => {
    const value = h('span', { class: `v${r.muted ? ' muted' : ''}` }, r.v,
      (r.sub || r.more) && h('small', {}, [r.sub && h('span', { class: 'now' }, r.sub), r.sub && r.more && ' · ', r.more]));
    const inner = [h('span', { class: 'k' }, r.k), value];
    return r.no == null ? h('div', { class: 'trow' }, inner)
      : h('button', { class: 'trow', type: 'button', onclick: () => select(r.no) }, inner);
  }));
}

function render() {
  renderStrip();
  renderCalendar();
  renderList();
}

// Detail / record open as a layer that slides in from the right over the list (push navigation) and slides back out.
// The list stays rendered and scrolled where it was underneath, so going back needs no scroll bookkeeping.
const reduceMotion = () => window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
let subToken = 0;

function openSub(animate) {
  const sub = $('v-sub');
  subToken++;
  sub.classList.remove('sub-in', 'sub-out');
  $('v-list').classList.remove('list-away', 'list-back');
  sub.hidden = false;
  sub.scrollTop = 0;
  $('v-list').inert = true;
  if (animate && !reduceMotion()) {
    void sub.offsetWidth;  // restart the animation when the layer was already animating
    sub.classList.add('sub-in');
    $('v-list').classList.add('list-away');  // parallax: the list slides left a little while the layer comes in
  }
}

function closeSub() {
  const sub = $('v-sub');
  if (sub.hidden) return;
  const token = ++subToken;
  $('v-list').inert = false;
  if (reduceMotion()) { sub.hidden = true; return; }
  sub.classList.remove('sub-in');
  sub.classList.add('sub-out');
  $('v-list').classList.remove('list-away');
  void sub.offsetWidth;
  $('v-list').classList.add('list-back');  // ...and slides back from the left while the layer leaves
  setTimeout(() => {
    if (token !== subToken) return;  // opened again meanwhile
    sub.hidden = true;
    sub.classList.remove('sub-out');
    $('v-list').classList.remove('list-back');
  }, 290);
}

function route() {
  const r = parseRoute(location.hash, state.ipos);
  const wasOpen = state.view && state.view !== 'list';
  state.view = r.view;
  state.selected = r.view === 'detail' ? r.no : null;
  $('detail').hidden = r.view !== 'detail';
  $('record').hidden = r.view !== 'record';
  const ipo = state.ipos.find(i => i.no === r.no);
  if (ipo && ipo.sub_start) {  // the list comes back on this stock's month
    state.year = Number(ipo.sub_start.slice(0, 4));
    state.month = Number(ipo.sub_start.slice(5, 7));
  }
  render();  // keep the list current underneath (applied marks may have changed)
  if (r.view === 'list') {
    closeSub();
  } else {
    $('topbar-title').textContent = r.view === 'record' ? '실전 성적' : '공모주 상세정보';
    if (r.view === 'detail') renderDetail(); else renderRecord();
    openSub(state.routed && !wasOpen);
  }
  state.routed = true;
}

function shift(delta) {
  let m = state.month + delta, y = state.year;
  if (m < 1) { m = 12; y--; } else if (m > 12) { m = 1; y++; }
  state.year = y; state.month = m;
  render();
}

// A kept-alive app (or a tab left in the background) would keep showing old data: reload when it comes back after 30+ minutes.
function reloadWhenStale() {
  if (document.visibilityState === 'visible' && needsRefresh(loadedAt, Date.now())) location.reload();
}
document.addEventListener('visibilitychange', reloadWhenStale);
window.addEventListener('pageshow', reloadWhenStale);

async function init() {
  $('prev').addEventListener('click', () => shift(-1));
  $('next').addEventListener('click', () => shift(1));
  const LN = notifier();
  if (LN) LN.addListener('localNotificationActionPerformed', ev => {
    const no = ev.notification && ev.notification.extra && ev.notification.extra.no;
    if (no) location.hash = String(no);
  });
  state.canApply = appliedAvailable(localStore());
  state.applied = state.canApply ? readApplied(localStore()) : new Set();
  $('back').addEventListener('click', goBack);
  $('record-link').addEventListener('click', ev => { ev.preventDefault(); go('record'); });
  const today = kstToday();
  state.year = Number(today.slice(0, 4));
  state.month = Number(today.slice(5, 7));
  try {
    const res = await fetch('ipos.json', { cache: 'no-cache' });
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();
    state.ipos = data.ipos || [];
    state.ledger = data.ledger || null;
    $('record-link').hidden = !state.ledger;
    const t = new Date(data.updated_at);
    $('updated').textContent = Number.isNaN(t.getTime()) ? '' : `마지막 갱신 ${t.toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`;
    $('disclaimer').textContent = data.disclaimer || '';
    const hrs = staleHours(data.updated_at, Date.now());
    if (hrs != null && hrs >= 14) $('stale').textContent = `데이터가 ${hrs}시간 전 기준이에요. 최신이 아닐 수 있어요.`;
  } catch (e) {
    $('weeks').replaceChildren(h('p', { class: 'msg' }, '데이터를 불러오지 못했어요. 잠시 뒤 다시 열어주세요.'));
    return;
  }
  window.addEventListener('hashchange', route);
  window.addEventListener('popstate', route);
  route();
  syncListingAlarms();
}

init();
