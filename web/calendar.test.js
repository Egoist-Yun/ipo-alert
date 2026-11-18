import test from 'node:test';
import assert from 'node:assert/strict';
import { monthGrid, barsForMonth, listForMonth, listTitle, readOpen, saveOpen, needsRefresh } from './calendar.js';

const A = { no: 77, name: 'A', sub_start: '2026-11-27', sub_end: '2026-11-30', flag_count: 2, is_spac: false };

test('bar spans month boundary', () => {
  assert.deepEqual(barsForMonth([A], 2026, 11).map(b => [b.start, b.end]), [['2026-11-27', '2026-11-30']]);
  const dec = [{ ...A, sub_end: '2026-12-01' }];
  assert.deepEqual(barsForMonth(dec, 2026, 11).map(b => [b.start, b.end]), [['2026-11-27', '2026-11-30']]);
  assert.deepEqual(barsForMonth(dec, 2026, 12).map(b => [b.start, b.end]), [['2026-12-01', '2026-12-01']]);
});

test('bar carries display fields', () => {
  const [b] = barsForMonth([A], 2026, 11);
  assert.deepEqual([b.no, b.name, b.flagCount, b.isSpac], [77, 'A', 2, false]);
});

test('monthGrid starts Monday and pads with empty strings', () => {
  const g = monthGrid(2026, 11);
  assert.equal(g[0][6], '2026-11-01');
  assert.deepEqual(g[0].slice(0, 6), ['', '', '', '', '', '']);
  assert.ok(g.every(w => w.length === 7));
  assert.equal(g.flat().filter(Boolean).length, 30);
});

test('ipo without dates is skipped', () => {
  assert.equal(barsForMonth([{ no: 1, name: 'x' }], 2026, 11).length, 0);
  assert.equal(listForMonth([{ no: 1, name: 'x' }], 2026, 11).length, 0);
});

test('ipo outside the month is not shown', () => {
  assert.equal(barsForMonth([A], 2026, 10).length, 0);
});

test('listForMonth sorted by start date', () => {
  const b = { ...A, no: 5, name: 'B', sub_start: '2026-11-02', sub_end: '2026-11-03' };
  assert.deepEqual(listForMonth([A, b], 2026, 11).map(i => i.name), ['B', 'A']);
});

import { badgeInfo, staleHours } from './calendar.js';

const base = { is_spac: false, inst_competition: 800, flag_count: 0, unknown_count: 0 };

test('badgeInfo: no flags, nothing unknown', () => {
  assert.deepEqual(badgeInfo(base), { text: '신호 없음', tone: '' });
});
test('badgeInfo: one unknown is stated next to "no signal"', () => {
  assert.deepEqual(badgeInfo({ ...base, unknown_count: 1 }), { text: '신호 없음 · 확인 불가 1', tone: '' });
});
test('badgeInfo: mostly unknown is grey, never "no signal"', () => {
  assert.deepEqual(badgeInfo({ ...base, unknown_count: 4 }), { text: '확인 불가 4', tone: 'wait' });
});
test('badgeInfo: flags win', () => {
  assert.deepEqual(badgeInfo({ ...base, flag_count: 3, unknown_count: 1 }), { text: '⚠ 3', tone: 'risk' });
});
test('badgeInfo: waiting and spac', () => {
  assert.deepEqual(badgeInfo({ ...base, inst_competition: null }), { text: '대기 중', tone: 'wait' });
  assert.deepEqual(badgeInfo({ ...base, is_spac: true }), { text: '스팩', tone: 'spac' });
});
test('staleHours counts whole hours since update', () => {
  assert.equal(staleHours('2026-11-17T08:00:00+09:00', Date.parse('2026-11-18T00:00:00+09:00')), 16);
  assert.equal(staleHours('garbage', Date.now()), null);
});

test('badgeInfo: model warning shows even when signals are few', () => {
  const warn = { ...base, flag_count: 1, prediction: { prob: { warn: true } } };
  assert.deepEqual(badgeInfo(warn), { text: '하락 경고', tone: 'risk' });
  const openWarn = { ...base, prediction: { prob: { warn: false }, open_down: { warn: true } } };
  assert.deepEqual(badgeInfo(openWarn), { text: '하락 경고', tone: 'risk' });
});

test('badgeInfo: after subscription the open-price judgment replaces the pre-subscription one', () => {
  const calmAfter = { ...base, flag_count: 1, prediction: { prob: { warn: true }, open_down: { warn: false } } };
  assert.deepEqual(badgeInfo(calmAfter), { text: '⚠ 1', tone: 'risk' });
});

test('badgeInfo: warning level from the data wins', () => {
  assert.deepEqual(badgeInfo({ ...base, warning: 'strong' }), { text: '강한 하락 경고', tone: 'risk' });
  assert.deepEqual(badgeInfo({ ...base, warning: 'warn', prediction: { prob: { warn: true } } }), { text: '하락 경고', tone: 'risk' });
});

test('listTitle names the month and counts the stocks', () => {
  assert.equal(listTitle(2026, 11, 13), '11월 청약 목록 · 13개');
  assert.equal(listTitle(2026, 12, 0), '12월 청약 목록 · 없음');
});

test('open state: default open, remembered, and safe when storage is broken', () => {
  const mem = new Map();
  const store = { getItem: k => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, v) };
  assert.equal(readOpen(store), true);
  saveOpen(store, false);
  assert.equal(readOpen(store), false);
  saveOpen(store, true);
  assert.equal(readOpen(store), true);
  const broken = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } };
  assert.equal(readOpen(broken), true);
  assert.doesNotThrow(() => saveOpen(broken, false));
  assert.equal(readOpen(undefined), true);
});

test('needsRefresh: only after the page has been loaded for 30 minutes or more', () => {
  const t0 = Date.parse('2026-11-18T10:00:00+09:00');
  assert.equal(needsRefresh(t0, t0 + 29 * 60 * 1000), false);
  assert.equal(needsRefresh(t0, t0 + 30 * 60 * 1000), true);
  assert.equal(needsRefresh(t0, t0 + 6 * 3600 * 1000), true);
});

test('needsRefresh: unknown load time or a clock that went backwards never loops reloads', () => {
  const now = Date.parse('2026-11-18T10:00:00+09:00');
  assert.equal(needsRefresh(null, now), false);
  assert.equal(needsRefresh(undefined, now), false);
  assert.equal(needsRefresh(now + 5000, now), false);
});

import { warnText } from './calendar.js';

test('warnText states counts when known, percentages for older data', () => {
  assert.equal(warnText({ caught: 10, warned: 16, n_down: 12, precision: 0.62, recall: 0.83 }, false),
    '경고 16개 중 10개 적중 · 하락 12개 중 10개 포착');
  assert.equal(warnText({ strong_caught: 7, strong_warned: 9, caught: 10, n_down: 12 }, true),
    '경고 9개 중 7개 적중 · 하락 12개 중 7개 포착');
  assert.equal(warnText({ precision: 0.62, recall: 0.83 }, false), '적중 62% · 하락의 83% 포착');
  assert.equal(warnText({}, false), null);
});

import { recordRows } from './calendar.js';

const model = (o = {}) => ({ saved: 3, resolved: 2, pending: 1, warned: 2, caught: 1, strong_warned: 1, strong_caught: 1, n_down: 2, early: true, ...o });

test('recordRows: counts only, per model, with a pending row and the too-early note', () => {
  const r = recordRows({ since: '2026-11-18', pre: model(), post: model({ saved: 0, resolved: 0, pending: 0, warned: 0, caught: 0, n_down: 0 }) });
  assert.deepEqual(r.rows, [
    ['청약 전 모델 (종가 기준)', '경고 2개 중 1개 적중 · 하락 2개 중 1개 포착'],
    ['청약 전 모델 강한 경고', '1개 중 1개 적중'],
    ['청약 전 모델 결과 대기', '1개'],
  ]);
  assert.equal(r.early, true);
  assert.ok(r.rows.every(([, v]) => !v.includes('%')));
});

test('recordRows: nothing saved yet, or no ledger at all', () => {
  const none = model({ saved: 0, resolved: 0, pending: 0, warned: 0, caught: 0, strong_warned: 0, strong_caught: 0, n_down: 0 });
  assert.deepEqual(recordRows({ since: '2026-11-18', pre: none, post: none }).rows, []);
  assert.equal(recordRows(null), null);
});

test('recordRows: enough declines drops the too-early note', () => {
  assert.equal(recordRows({ since: 'x', pre: model({ n_down: 10, early: false }), post: model({ saved: 0, early: false }) }).early, false);
});

import { verdictInfo } from './calendar.js';

test('badgeInfo: a listed stock shows its actual first-day return', () => {
  assert.deepEqual(badgeInfo({ ...base, first_close: 6000, final_price: 10000, flag_count: 3 }), { text: '-40%', tone: 'risk' });
  assert.deepEqual(badgeInfo({ ...base, first_close: 16500, final_price: 10000 }), { text: '+65%', tone: '' });
  assert.deepEqual(badgeInfo({ ...base, first_close: 10000, final_price: 10000 }), { text: '+0%', tone: '' });
});

const waiting = { ...base, inst_competition: null };
const counts = { warned: 15, caught: 10, n_down: 18, strong_warned: 10, strong_caught: 7 };

test('verdictInfo: strong warning names the counts behind it', () => {
  const ipo = { ...base, flag_count: 3, warning: 'strong', prediction: { prob: counts } };
  assert.deepEqual(verdictInfo(ipo), { text: '강한 하락 경고 · 경고 10개 중 7개 적중', tone: 'risk' });
});

test('verdictInfo: after the subscription the open-price judgment supplies the counts', () => {
  const ipo = { ...base, warning: 'warn', prediction: { prob: counts, open_down: { warned: 16, caught: 10, n_down: 12 } } };
  assert.deepEqual(verdictInfo(ipo), { text: '하락 경고 · 경고 16개 중 10개 적중', tone: 'risk' });
});

test('verdictInfo: a warning without counts (older data) is still stated', () => {
  assert.deepEqual(verdictInfo({ ...base, warning: 'warn', prediction: { prob: {} } }), { text: '하락 경고', tone: 'risk' });
});

test('verdictInfo: no warning says so and keeps unknowns visible', () => {
  assert.deepEqual(verdictInfo({ ...base, flag_count: 1 }), { text: '하락 경고 없음', tone: '' });
  assert.deepEqual(verdictInfo({ ...base, unknown_count: 2 }), { text: '하락 경고 없음 · 확인 불가 2개', tone: '' });
});

test('verdictInfo: waiting, spac and listed stocks have no verdict line', () => {
  assert.deepEqual(verdictInfo(waiting), { text: '기관 수요예측 결과가 아직 없어요.', tone: 'wait' });
  assert.equal(verdictInfo({ ...base, is_spac: true }), null);
  assert.equal(verdictInfo({ ...base, first_close: 9000, final_price: 10000 }), null);
});
