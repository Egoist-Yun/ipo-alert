import { monthGrid, barsForMonth, listForMonth, badgeInfo, staleHours, listTitle, readOpen, saveOpen } from './calendar.js';
import { brokerLinks, showBrokerButtons, isAndroid, brokerAction, isNativeApp } from './brokers.js';

const $ = id => document.getElementById(id);
const state = { ipos: [], accuracyNote: null, year: 0, month: 0, selected: null };

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

function valueText(sig) {
  const v = sig.value;
  if (v == null) return '확인 불가';
  if (sig.key === 'price_position') return won(v);
  if (sig.key === 'inst_competition') return `${Number(v).toFixed(0)}대 1`;
  if (sig.key === 'mood') return `${(v * 100).toFixed(0)}%`;
  return `${v}%`;
}

const tone = ipo => badgeInfo(ipo).tone;
const badgeText = ipo => badgeInfo(ipo).text;

function select(no) {
  state.selected = no;
  history.replaceState(null, '', no == null ? location.pathname : `#${no}`);
  render();
  if (no != null) $('detail').scrollIntoView({ block: 'start' });
}

function renderCalendar() {
  const { year, month } = state;
  $('month').textContent = `${year}년 ${month}월`;
  const bars = barsForMonth(state.ipos, year, month);
  const today = kstToday();
  const weeks = $('weeks');
  weeks.replaceChildren();
  for (const week of monthGrid(year, month)) {
    const real = week.filter(Boolean);
    const lo = real[0], hi = real[real.length - 1];
    const segs = bars
      .map(b => ({ b, s: b.start < lo ? lo : b.start, e: b.end > hi ? hi : b.end }))
      .filter(x => x.s <= x.e)
      .map(x => ({ ...x, c0: week.indexOf(x.s), c1: week.indexOf(x.e) }))
      .sort((a, b) => a.c0 - b.c0 || a.c1 - b.c1);
    const laneEnd = [];
    const el = h('div', { class: 'week' },
      week.map(d => h('div', { class: `day${d === today ? ' today' : ''}${d ? '' : ' empty'}` }, d ? Number(d.slice(8)) : '0')));
    for (const seg of segs) {
      let lane = laneEnd.findIndex(end => end < seg.c0);
      if (lane < 0) { lane = laneEnd.length; laneEnd.push(-1); }
      laneEnd[lane] = seg.c1;
      const ipo = state.ipos.find(i => i.no === seg.b.no);
      const label = `${seg.b.name} ${badgeText(ipo)}`;
      const bar = h('button', {
        class: `bar ${tone(ipo)}${state.selected === seg.b.no ? ' selected' : ''}`,
        type: 'button',
        style: `grid-column:${seg.c0 + 1} / ${seg.c1 + 2};grid-row:${lane + 2}`,
        'aria-label': `${seg.b.name}, ${badgeText(ipo)}, 청약 ${md(ipo.sub_start)}~${md(ipo.sub_end)}`,
        onclick: () => select(seg.b.no),
      }, label);
      el.append(bar);
    }
    weeks.append(el);
  }
}

function localStore() {
  try { return window.localStorage; } catch (e) { return undefined; }
}

function renderList() {
  const items = listForMonth(state.ipos, state.year, state.month);
  const rows = items.map(ipo => {
    const cls = tone(ipo);
    return h('button', { class: 'row', type: 'button', onclick: () => select(ipo.no) },
      h('span', {},
        h('span', { class: 'name' }, ipo.name),
        h('span', { class: 'meta' }, `청약 ${md(ipo.sub_start)}~${md(ipo.sub_end)}`)),
      h('span', { class: `badge ${cls}` }, badgeText(ipo)));
  });
  const box = h('details', { class: 'drop', open: readOpen(localStore()) },
    h('summary', {}, h('span', {}, listTitle(state.year, state.month, items.length))),
    rows);
  box.addEventListener('toggle', () => saveOpen(localStore(), box.open));
  $('list').replaceChildren(box);
}

function brokerNodes(ipo) {
  if (!showBrokerButtons(ipo, kstToday())) return [];
  if (!isAndroid(navigator.userAgent)) {
    return [];
  }
  const links = brokerLinks(ipo.underwriters);
  if (!links.length) return [];
  return [h('div', { class: 'broker-buttons' },
    links.map(l => brokerButton(l)))];
}

async function launchBroker(action) {
  const launcher = window.Capacitor?.Plugins?.AppLauncher;
  try {
    const res = await launcher.openUrl({ url: action.url });
    if (res && res.completed) return;
  } catch (e) { /* fall through to the Play Store */ }
  window.location.href = action.fallback;
}

function brokerButton(link) {
  const action = brokerAction(link, isNativeApp(window));
  if (action.type === 'launch') {
    return h('a', { class: 'btn-medium', href: action.fallback, onclick: ev => { ev.preventDefault(); launchBroker(action); } },
      `${link.name} 앱 열기`);
  }
  return h('a', { class: 'btn-medium', href: action.href }, `${link.name} 앱 열기`);
}

function kv(k, v, cls) {
  return h('div', { class: 'kv' }, h('span', { class: 'k' }, k), h('span', { class: `v ${cls || ''}` }, v));
}

function renderDetail() {
  const box = $('detail');
  const ipo = state.ipos.find(i => i.no === state.selected);
  if (!ipo) { box.replaceChildren(); return; }

  const nodes = [h('h3', {}, ipo.name)];
  const chips = [ipo.market, ...(ipo.underwriters || [])].filter(Boolean);
  nodes.push(h('div', { class: 'chips' }, chips.map(c => h('span', { class: 'badge' }, c))));
  nodes.push(kv('청약', `${md(ipo.sub_start)}~${md(ipo.sub_end)}`));
  nodes.push(...brokerNodes(ipo));
  if (ipo.listing_date) nodes.push(kv('상장', md(ipo.listing_date)));

  if (ipo.is_spac) {
  } else if (ipo.inst_competition == null) {
    nodes.push(h('p', { class: 'summary' }, '기관 수요예측 결과가 아직 없어요.'));
  } else {
    const unknown = ipo.unknown_count ? ` · 확인 불가 ${ipo.unknown_count}개` : '';
    nodes.push(h('p', { class: 'summary' }, (ipo.flag_count ? `위험 신호 ${ipo.flag_count}개` : '위험 신호 없음') + unknown));
    nodes.push(h('h4', {}, '위험 신호'));
    for (const s of ipo.signals) {
      nodes.push(kv(s.label, (s.flag ? '⚠ ' : '') + valueText(s), s.flag === true ? 'flag' : s.flag === null ? 'unknown' : ''));
    }
    nodes.push(...patternNodes(ipo));
    nodes.push(...(ipo.first_close != null ? resultNodes(ipo) : predictionNodes(ipo)));
  }
  if (ipo.url) nodes.push(h('a', { class: 'btn-medium', href: ipo.url, target: '_blank', rel: 'noopener' }, '원문 보기'));
  box.replaceChildren(h('div', { class: 'panel' }, nodes));
}

function patternNodes(ipo) {
  const list = ipo.patterns || [];
  if (!list.length) return [];
  const nodes = [h('h4', {}, '과거 패턴')];
  const risks = list.filter(p => p.kind === 'risk');
  const safes = list.filter(p => p.kind === 'safe');
  for (const p of risks) {
    const rate = p.close_down != null ? `${(p.close_down * 100).toFixed(0)}%` : '-';
    const open = p.phase === 'post' && p.open_down != null ? ` · 시초가 ${(p.open_down * 100).toFixed(0)}%` : '';
    nodes.push(kv(p.label, `하락 ${rate}${open} · ${p.n}개`, 'flag'));
  }
  for (const p of safes) {
    nodes.push(kv(p.label, `하락 ${(p.close_down * 100).toFixed(0)}% · ${p.n}개`));
  }
  return nodes;
}

function resultNodes(ipo) {
  const base = ipo.final_price;
  const nodes = [h('h4', {}, '상장 결과'), kv('공모가', won(base))];
  if (ipo.open_price != null) nodes.push(kv('시초가', `${won(ipo.open_price)} (${pct(ipo.open_price / base - 1)})`));
  nodes.push(kv('첫날 종가', `${won(ipo.first_close)} (${pct(ipo.first_close / base - 1)})`));
  return nodes;
}

function predictionNodes(ipo) {
  const p = ipo.prediction;
  if (!p || (!p.knn && !p.open && !p.close && !p.prob && !p.open_down)) {
    const why = p && p.accuracy
      ? '과거 기록으로 검증했을 때 기준보다 정확하지 않아서 보여주지 않아요.'
      : '비교할 과거 기록이 아직 부족해요.';
    return [h('h4', {}, '첫날 가격 예측'), h('p', { class: 'p' }, `예측을 만들지 못했어요. ${why}`)];
  }
  const nodes = [];
  const acc = p.accuracy || {};
  if (ipo.warning) {
    const w = p.open_down || p.prob || {};
    const strong = ipo.warning === 'strong';
    nodes.push(h('p', { class: 'summary warn' }, strong ? '강한 하락 경고' : '하락 경고'));
    const sp = strong ? w.strong_precision : w.precision;
    const sr = strong ? w.strong_recall : w.recall;
    if (sp != null) nodes.push(kv('과거 경고 적중', `${(sp * 100).toFixed(0)}% · 하락의 ${(sr * 100).toFixed(0)}% 포착`));
  }
  if (p.conflict) {
    nodes.push(h('p', { class: 'summary' }, ipo.warning ? '가격 예측은 상승이지만, 하락을 미리 잡는 데는 과거에 경고가 가격 예측보다 정확했어요.' : '신호와 예측이 엇갈려요. 두 가지를 함께 보세요.'));
  }
  if (p.open || p.close) {
    nodes.push(h('h4', {}, '가격 예측'));
    for (const [key, label] of [['open', '시초가 예상'], ['close', '첫날 종가 예상']]) {
      const e = p[key];
      if (!e) continue;
      nodes.push(kv(`${label}${e.uses_retail ? ' · 일반청약 반영' : ''} (±${(e.mae * 100).toFixed(0)}%p)`, `${won(e.price)} (${pct(e.return)})`, e.return < 0 ? 'flag' : ''));
    }
  }
  if (p.open_down) {
    const o = p.open_down;
    nodes.push(h('h4', {}, '청약 후: 시초가가 공모가 아래일 확률'));
    nodes.push(kv('일반청약 경쟁률 반영', `${(o.p_down * 100).toFixed(0)}%`, o.warn ? 'flag' : ''));
  }
  if (p.prob) {
    const q = p.prob;
    nodes.push(h('h4', {}, '공모가 아래로 끝날 확률'));
    nodes.push(kv('첫날 종가 기준', `${(q.p_down * 100).toFixed(0)}%`, q.warn ? 'flag' : ''));
  }
  if (p.knn) {
    const k = p.knn;
    nodes.push(h('h4', {}, '비슷했던 과거 공모주'));
    nodes.push(h('p', { class: 'p' }, `${k.n}개 중 ${k.down_count}개가 첫날 공모가 아래로 마감했어요.`));
    nodes.push(kv('비슷한 종목의 가운데 절반 범위', `${won(k.price_low)} ~ ${won(k.price_high)}`));
    nodes.push(kv('가운데 값', pct(k.median)));
    for (const it of k.items) nodes.push(kv(it.name, pct(it.return)));
  }
  return nodes;
}

function render() {
  renderCalendar();
  renderList();
  renderDetail();
}

function shift(delta) {
  let m = state.month + delta, y = state.year;
  if (m < 1) { m = 12; y--; } else if (m > 12) { m = 1; y++; }
  state.year = y; state.month = m;
  render();
}

async function init() {
  $('prev').addEventListener('click', () => shift(-1));
  $('next').addEventListener('click', () => shift(1));
  const today = kstToday();
  state.year = Number(today.slice(0, 4));
  state.month = Number(today.slice(5, 7));
  try {
    const res = await fetch('ipos.json', { cache: 'no-cache' });
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();
    state.ipos = data.ipos || [];
    const t = new Date(data.updated_at);
    $('updated').textContent = Number.isNaN(t.getTime()) ? '' : `마지막 갱신 ${t.toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`;
    $('disclaimer').textContent = data.disclaimer || '';
    const hrs = staleHours(data.updated_at, Date.now());
    if (hrs != null && hrs >= 14) $('stale').textContent = `데이터가 ${hrs}시간 전 기준이에요. 최신이 아닐 수 있어요.`;
  } catch (e) {
    $('weeks').replaceChildren(h('p', { class: 'msg' }, '데이터를 불러오지 못했어요. 잠시 뒤 다시 열어주세요.'));
    return;
  }
  const fromHash = Number(location.hash.slice(1));
  const hit = state.ipos.find(i => i.no === fromHash);
  if (hit && hit.sub_start) {
    state.selected = hit.no;
    state.year = Number(hit.sub_start.slice(0, 4));
    state.month = Number(hit.sub_start.slice(5, 7));
  }
  render();
}

init();
