import test from 'node:test';
import assert from 'node:assert/strict';
import { monthGrid, barsForMonth, listForMonth, needsRefresh } from './calendar.js';

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
  assert.deepEqual(badgeInfo({ ...base, flag_count: 3, unknown_count: 1 }), { text: '신호 3개', tone: 'wait' });
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
  assert.deepEqual(badgeInfo(calmAfter), { text: '신호 1개', tone: 'wait' });
});

test('badgeInfo: warning level from the data wins', () => {
  assert.deepEqual(badgeInfo({ ...base, warning: 'strong' }), { text: '강한 하락 경고', tone: 'risk' });
  assert.deepEqual(badgeInfo({ ...base, warning: 'warn', prediction: { prob: { warn: true } } }), { text: '하락 경고', tone: 'risk' });
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
  assert.deepEqual(badgeInfo({ ...base, first_close: 6000, final_price: 10000, flag_count: 3 }), { text: '-40%', tone: 'done' });
  assert.deepEqual(badgeInfo({ ...base, first_close: 16500, final_price: 10000 }), { text: '+65%', tone: 'done' });
  assert.deepEqual(badgeInfo({ ...base, first_close: 10000, final_price: 10000 }), { text: '+0%', tone: 'done' });
});

const waiting = { ...base, inst_competition: null };
const counts = { warned: 15, caught: 10, n_down: 18, strong_warned: 10, strong_caught: 7 };

test('verdictInfo: strong warning is the headline only', () => {
  const ipo = { ...base, flag_count: 3, warning: 'strong', prediction: { prob: counts } };
  assert.deepEqual(verdictInfo(ipo), { text: '강한 하락 경고', tone: 'risk' });
});

test('verdictInfo: after the subscription the warning level still comes from the data', () => {
  const ipo = { ...base, warning: 'warn', prediction: { prob: counts, open_down: { warned: 16, caught: 10, n_down: 12 } } };
  assert.deepEqual(verdictInfo(ipo), { text: '하락 경고', tone: 'risk' });
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

import { parseRoute } from './calendar.js';

const stocks = [{ no: 2352 }, { no: 2336 }];

test('parseRoute: no hash is the list view', () => {
  assert.deepEqual(parseRoute('', stocks), { view: 'list', no: null });
  assert.deepEqual(parseRoute('#', stocks), { view: 'list', no: null });
});

test('parseRoute: a known stock number opens its detail', () => {
  assert.deepEqual(parseRoute('#2352', stocks), { view: 'detail', no: 2352 });
});

test('parseRoute: an unknown stock number falls back to the list', () => {
  assert.deepEqual(parseRoute('#9999', stocks), { view: 'list', no: null });
  assert.deepEqual(parseRoute('#2352', []), { view: 'list', no: null });
});

test('parseRoute: #record opens the live record', () => {
  assert.deepEqual(parseRoute('#record', stocks), { view: 'record', no: null });
  assert.deepEqual(parseRoute('#record', []), { view: 'record', no: null });
});

test('parseRoute: malformed values never open a detail', () => {
  for (const bad of ['#abc', '#2352abc', '#-5', '#1.5', '#0x10', '#2352/x', '#RECORD', 'record', '#%E0%A4%A']) {
    assert.deepEqual(parseRoute(bad, stocks), { view: 'list', no: null }, bad);
  }
  assert.deepEqual(parseRoute(undefined, stocks), { view: 'list', no: null });
  assert.deepEqual(parseRoute(null, null), { view: 'list', no: null });
});

import { groupForList, readApplied, saveApplied, appliedAvailable, toggleApplied, listingLabel } from './calendar.js';

const TODAY = '2026-11-18';
const mk = (no, sub_start, sub_end, extra = {}) => ({ no, name: `S${no}`, sub_start, sub_end, listing_date: null, ...extra });
const SET = [
  mk(1, '2026-11-16', '2026-11-17', { listing_date: '2026-11-26' }),                         // applied, not listed
  mk(2, '2026-11-02', '2026-11-03', { listing_date: '2026-11-10', first_close: 12000, final_price: 10000 }), // applied, listed
  mk(3, '2026-11-16', '2026-11-17', { listing_date: '2026-11-26' }),                         // not applied, closed, not listed
  mk(4, '2026-11-18', '2026-11-19'),                                                          // deadline is today
  mk(5, '2026-11-25', '2026-11-26'),
  mk(6, '2026-11-27', '2026-11-30', { is_spac: true }),
  mk(7, '2026-11-30', '2026-12-02'),                                                          // spans two months
  mk(8, '2026-11-25', '2026-11-26', { listing_date: '2026-12-03' }),                         // applied, still open
];
const nos = list => list.map(i => i.no);
const APPLIED = new Set([1, 2, 8]);

test('groupForList: applied and not yet listed come first, whatever month is shown, by listing date', () => {
  assert.deepEqual(nos(groupForList(SET, 2026, 11, TODAY, APPLIED).applied), [1, 8]);
  assert.deepEqual(nos(groupForList(SET, 2026, 12, TODAY, APPLIED).applied), [1, 8]);
  assert.deepEqual(nos(groupForList(SET, 2027, 3, TODAY, APPLIED).applied), [1, 8]);
});

test('groupForList: an applied stock that already listed belongs to the finished group', () => {
  const g = groupForList(SET, 2026, 11, TODAY, APPLIED);
  assert.ok(nos(g.done).includes(2) && !nos(g.applied).includes(2));
});

test('groupForList: a closed, unlisted stock that was not applied for is finished; the deadline day is still upcoming', () => {
  const g = groupForList(SET, 2026, 11, TODAY, APPLIED);
  assert.ok(nos(g.done).includes(3));
  assert.ok(nos(g.upcoming).includes(4));  // sub_end === today: no closing time in the data, so it counts as running
});

test('groupForList: upcoming is sorted by subscription start, spacs included, applied stocks excluded', () => {
  assert.deepEqual(nos(groupForList(SET, 2026, 11, TODAY, APPLIED).upcoming), [4, 5, 6, 7]);
});

test('groupForList: finished is most recent first', () => {
  assert.deepEqual(nos(groupForList(SET, 2026, 11, TODAY, APPLIED).done), [3, 2]);
});

test('groupForList: a stock spanning two months shows in both months', () => {
  assert.ok(nos(groupForList(SET, 2026, 12, TODAY, APPLIED).upcoming).includes(7));
  assert.deepEqual(nos(groupForList(SET, 2026, 12, TODAY, APPLIED).done), []);
});

test('groupForList: empty groups are empty arrays; applied without a listing date goes last', () => {
  assert.deepEqual(groupForList([], 2026, 11, TODAY, new Set()), { applied: [], upcoming: [], done: [] });
  const g = groupForList([mk(9, '2026-11-16', '2026-11-17'), mk(1, '2026-11-16', '2026-11-17', { listing_date: '2026-11-26' })], 2026, 11, TODAY, new Set([9, 1]));
  assert.deepEqual(nos(g.applied), [1, 9]);
  assert.deepEqual(groupForList([{ no: 1, name: 'x' }], 2026, 11, TODAY, new Set()).upcoming, []);
});

function memStore() {
  const mem = new Map();
  return { getItem: k => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, String(v)), removeItem: k => mem.delete(k) };
}
const broken = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); }, removeItem() { throw new Error('blocked'); } };

test('applied storage: empty by default, round trip, junk and blocked storage are safe', () => {
  const s = memStore();
  assert.deepEqual([...readApplied(s)], []);
  saveApplied(s, new Set([5, 3]));
  assert.deepEqual([...readApplied(s)].sort(), [3, 5]);
  s.setItem('ipo-applied', '{not json');
  assert.deepEqual([...readApplied(s)], []);
  s.setItem('ipo-applied', '{"a":1}');
  assert.deepEqual([...readApplied(s)], []);
  s.setItem('ipo-applied', '[1,"x",null,2.5,7]');
  assert.deepEqual([...readApplied(s)], [1, 7]);
  assert.deepEqual([...readApplied(broken)], []);
  assert.deepEqual([...readApplied(undefined)], []);
  assert.doesNotThrow(() => saveApplied(broken, new Set([1])));
});

test('appliedAvailable: only when the storage really works', () => {
  assert.equal(appliedAvailable(memStore()), true);
  assert.equal(appliedAvailable(broken), false);
  assert.equal(appliedAvailable(undefined), false);
});

test('toggleApplied adds and removes without touching the original', () => {
  const a = new Set([1]);
  const b = toggleApplied(a, 2);
  assert.deepEqual([...a], [1]);
  assert.deepEqual([...b].sort(), [1, 2]);
  assert.deepEqual([...toggleApplied(b, 1)], [2]);
});

test('listingLabel: the sell day, or unknown', () => {
  assert.equal(listingLabel({ listing_date: '2026-11-26' }), '11/26 상장');
  assert.equal(listingLabel({ listing_date: '2026-12-03' }), '12/3 상장');
  assert.equal(listingLabel({}), '상장일 미정');
});

import { listingAlarms } from './calendar.js';

const L = (no, listing_date, extra = {}) => ({ no, name: `S${no}`, listing_date, final_price: 19000, ...extra });
const NOV30 = '2026-11-30';

test('listingAlarms: a marked stock is alarmed at 08:30 KST on its listing day', () => {
  const [a] = listingAlarms([L(7, NOV30)], new Set([7]), '2026-11-18T17:35:00+09:00');
  assert.deepEqual(a, {
    id: 7, no: 7, at: '2026-11-30T08:30:00+09:00',
    title: '오늘 S7 상장', body: '시초가 매도 준비. 공모가 19,000원',
  });
});

test('listingAlarms: the listing-day boundary is 08:30 sharp (an alarm in the past is dropped)', () => {
  const run = now => listingAlarms([L(7, NOV30)], new Set([7]), now).length;
  assert.equal(run('2026-11-30T08:29:59+09:00'), 1);
  assert.equal(run('2026-11-30T08:30:00+09:00'), 0);
  assert.equal(run('2026-11-30T09:10:00+09:00'), 0);
  assert.equal(run('2026-12-01T00:00:00+09:00'), 0);
  assert.equal(run('2026-11-29T23:29:00Z'), 1);  // UTC input is compared as an instant: 23:29Z = 08:29 KST
  assert.equal(run('2026-11-29T23:31:00Z'), 0);  // 23:31Z = 08:31 KST
});

test('listingAlarms: not marked, marked off, or no listing date means no alarm', () => {
  const now = '2026-11-18T10:00:00+09:00';
  assert.deepEqual(listingAlarms([L(7, NOV30)], new Set(), now), []);
  assert.deepEqual(listingAlarms([L(7, NOV30)], new Set([8]), now), []);
  assert.deepEqual(listingAlarms([L(7, null)], new Set([7]), now), []);
  assert.deepEqual(listingAlarms([{ no: 7, name: 'x' }], new Set([7]), now), []);
  assert.deepEqual(listingAlarms([L(7, '11/30')], new Set([7]), now), []);
});

test('listingAlarms: spacs that were marked get an alarm too; ids are the stock numbers; sorted by time', () => {
  const got = listingAlarms([L(9, '2026-12-03'), L(5, NOV30, { is_spac: true })], new Set([5, 9]), '2026-11-18T10:00:00+09:00');
  assert.deepEqual(got.map(a => [a.id, a.at]), [[5, '2026-11-30T08:30:00+09:00'], [9, '2026-12-03T08:30:00+09:00']]);
});

test('listingAlarms: the body drops the price when unknown and adds the warning line', () => {
  const now = '2026-11-18T10:00:00+09:00';
  assert.equal(listingAlarms([L(7, NOV30, { final_price: null })], new Set([7]), now)[0].body, '시초가 매도 준비.');
  assert.equal(listingAlarms([L(7, NOV30, { warning: 'warn' })], new Set([7]), now)[0].body, '시초가 매도 준비. 공모가 19,000원\n하락 경고가 있어요.');
  assert.equal(listingAlarms([L(7, NOV30, { warning: 'strong' })], new Set([7]), now)[0].body, '시초가 매도 준비. 공모가 19,000원\n강한 하락 경고가 있어요.');
});

test('listingAlarms: a bad clock value yields nothing instead of throwing', () => {
  assert.deepEqual(listingAlarms([L(7, NOV30)], new Set([7]), 'garbage'), []);
  assert.deepEqual(listingAlarms([], new Set([7]), '2026-11-18T10:00:00+09:00'), []);
});

import { barLabel } from './calendar.js';

test('barLabel: a normal stock shows just its name', () => {
  assert.equal(barLabel({ name: '유캐스트', risk: false, applied: false, continuationOneDay: false }), '유캐스트');
});

test('barLabel: risk adds a warning mark, applied adds a check mark in front of it', () => {
  assert.equal(barLabel({ name: '유캐스트', risk: true, applied: false, continuationOneDay: false }), '⚠ 유캐스트');
  assert.equal(barLabel({ name: '유캐스트', risk: true, applied: true, continuationOneDay: false }), '✓ ⚠ 유캐스트');
  assert.equal(barLabel({ name: '유캐스트', risk: false, applied: true, continuationOneDay: false }), '✓ 유캐스트');
});

test('barLabel: a one-day continuation piece (the bar began in an earlier week) has no text', () => {
  assert.equal(barLabel({ name: '유캐스트', risk: true, applied: true, continuationOneDay: true }), '');
});

test('barLabel: a spac (not risk) is just its name, no state words', () => {
  assert.equal(barLabel({ name: '신영스팩12호', risk: false, applied: false, continuationOneDay: false }), '신영스팩12호');
});

import { markToast } from './calendar.js';

test('markToast: in a browser the alarm is not available, and the toast says so', () => {
  assert.equal(markToast({ native: false, alarmOff: false, hasAlarm: false, hasListingDate: true }), '알림은 안드로이드 앱에서만 받을 수 있어요');
  assert.equal(markToast({ native: false, alarmOff: false, hasAlarm: false, hasListingDate: false }), '알림은 안드로이드 앱에서만 받을 수 있어요');
});

test('markToast: in the app, a scheduled alarm is confirmed', () => {
  assert.equal(markToast({ native: true, alarmOff: false, hasAlarm: true, hasListingDate: true }), '상장일 08:30에 알림으로 알려드릴게요, 몇 분 늦을 수 있어요');
});

test('markToast: in the app with notifications switched off it says so', () => {
  assert.equal(markToast({ native: true, alarmOff: true, hasAlarm: true, hasListingDate: true }), '알림이 꺼져 있어요');
});

test('markToast: in the app, a stock without a listing date gets a promise instead of silence', () => {
  assert.equal(markToast({ native: true, alarmOff: false, hasAlarm: false, hasListingDate: false }), '상장일이 정해지면 08:30에 알림을 예약할게요');
  assert.equal(markToast({ native: true, alarmOff: true, hasAlarm: false, hasListingDate: false }), '상장일이 정해지면 08:30에 알림을 예약할게요');
});

test('markToast: in the app, a listing date that is already past gets no toast', () => {
  assert.equal(markToast({ native: true, alarmOff: false, hasAlarm: false, hasListingDate: true }), null);
});

test('badgeInfo: "risk" means a pre-listing decline warning only (strong, warn, or the model warning)', () => {
  assert.equal(badgeInfo({ ...base, warning: 'strong' }).tone, 'risk');
  assert.equal(badgeInfo({ ...base, warning: 'warn' }).tone, 'risk');
  assert.equal(badgeInfo({ ...base, prediction: { prob: { warn: true } } }).tone, 'risk');
  assert.equal(badgeInfo({ ...base, flag_count: 4 }).tone, 'wait');   // signals alone are not a warning
  assert.equal(badgeInfo({ ...base, first_close: 5000, final_price: 10000, warning: 'strong' }).tone, 'done');  // listed: the result, not a warning
});

import { dayStatus } from './calendar.js';

const DS = (o = {}) => ({ no: 1, name: 'S', sub_start: '2026-11-18', sub_end: '2026-11-19', listing_date: '2026-11-30', first_close: null, ...o });

test('dayStatus: listing today (not yet listed) comes first', () => {
  assert.equal(dayStatus(DS({ listing_date: '2026-11-19', sub_end: '2026-11-19' }), '2026-11-19'), '오늘 상장');
});

test('dayStatus: listing tomorrow', () => {
  assert.equal(dayStatus(DS({ sub_start: '2026-11-10', sub_end: '2026-11-11', listing_date: '2026-11-20' }), '2026-11-19'), '내일 상장');
});

test('dayStatus: the last subscription day', () => {
  assert.equal(dayStatus(DS({ sub_start: '2026-11-18', sub_end: '2026-11-19' }), '2026-11-19'), '오늘 마감');
});

test('dayStatus: the first subscription day (a one-day subscription is the deadline day)', () => {
  assert.equal(dayStatus(DS({ sub_start: '2026-11-19', sub_end: '2026-11-20' }), '2026-11-19'), '오늘 청약 시작');
  assert.equal(dayStatus(DS({ sub_start: '2026-11-19', sub_end: '2026-11-19' }), '2026-11-19'), '오늘 마감');
});

test('dayStatus: nothing special, listed stocks, missing dates', () => {
  assert.equal(dayStatus(DS({ sub_start: '2026-11-25', sub_end: '2026-11-26', listing_date: null }), '2026-11-19'), null);
  assert.equal(dayStatus(DS({ sub_start: '2026-11-17', sub_end: '2026-11-20', listing_date: null }), '2026-11-19'), null);  // in the middle of a 4-day subscription
  assert.equal(dayStatus(DS({ listing_date: '2026-11-19', first_close: 12000 }), '2026-11-19'), null);  // already listed
  assert.equal(dayStatus({ no: 1, name: 'x' }, '2026-11-19'), null);
});

test('dayStatus: tomorrow is computed as a calendar day across month and year ends', () => {
  assert.equal(dayStatus(DS({ listing_date: '2026-12-01' }), '2026-11-30'), '내일 상장');
  assert.equal(dayStatus(DS({ listing_date: '2027-01-01' }), '2026-12-31'), '내일 상장');
  assert.equal(dayStatus(DS({ listing_date: '2028-02-29' }), '2028-02-28'), '내일 상장');  // leap day
  assert.equal(dayStatus(DS({ listing_date: '2026-03-01' }), '2026-02-28'), '내일 상장');  // no leap day
});

import { listingMarks } from './calendar.js';

const LM = (no, listing_date, extra = {}) => ({ no, name: `S${no}`, listing_date, ...extra });

test('listingMarks: only stocks the user applied for, with a listing date inside the month', () => {
  const ipos = [LM(1, '2026-11-30'), LM(2, '2026-11-20'), LM(3, '2026-12-02'), LM(4, null), LM(5, '2026-10-22')];
  assert.deepEqual(listingMarks(ipos, new Set([1, 3, 4, 5]), 2026, 11).map(m => m.no), [1]);
  assert.deepEqual(listingMarks(ipos, new Set([1, 2, 3, 4, 5]), 2026, 12).map(m => m.no), [3]);
});

test('listingMarks: stocks not applied for are left out', () => {
  assert.deepEqual(listingMarks([LM(1, '2026-11-30')], new Set(), 2026, 11), []);
  assert.deepEqual(listingMarks([LM(1, '2026-11-30')], new Set([9]), 2026, 11), []);
});

test('listingMarks: month boundaries are inclusive', () => {
  const ipos = [LM(1, '2026-11-01'), LM(2, '2026-11-30'), LM(3, '2026-12-01'), LM(4, '2026-10-31')];
  assert.deepEqual(listingMarks(ipos, new Set([1, 2, 3, 4]), 2026, 11).map(m => m.no), [1, 2]);
});

test('listingMarks: a listed stock carries listed: true; the shape is {no, name, date, listed}', () => {
  const [m] = listingMarks([LM(7, '2026-11-10', { first_close: 12000 })], new Set([7]), 2026, 11);
  assert.deepEqual(m, { no: 7, name: 'S7', date: '2026-11-10', listed: true });
  const [n] = listingMarks([LM(8, '2026-11-26')], new Set([8]), 2026, 11);
  assert.equal(n.listed, false);
});

test('listingMarks: sorted by date, then stock number; two stocks on the same day both appear', () => {
  const ipos = [LM(9, '2026-11-26'), LM(3, '2026-11-26'), LM(5, '2026-11-20')];
  assert.deepEqual(listingMarks(ipos, new Set([9, 3, 5]), 2026, 11).map(m => [m.date, m.no]), [['2026-11-20', 5], ['2026-11-26', 3], ['2026-11-26', 9]]);
});

import { barTone } from './calendar.js';

const BT = (o = {}) => ({ no: 1, name: 'S', sub_start: '2026-11-17', sub_end: '2026-11-20', inst_competition: 800, flag_count: 0, unknown_count: 0, is_spac: false, ...o });

test('barTone: a stock still to come is blue (empty class) whatever its signals: waiting, signals only, none, spac', () => {
  assert.equal(barTone(BT(), '2026-11-19'), '');
  assert.equal(barTone(BT({ inst_competition: null }), '2026-11-19'), '');       // waiting for the demand result
  assert.equal(barTone(BT({ flag_count: 3 }), '2026-11-19'), '');                // signals without a warning
  assert.equal(barTone(BT({ unknown_count: 4 }), '2026-11-19'), '');
  assert.equal(barTone(BT({ is_spac: true, sub_end: '2026-11-25' }), '2026-11-19'), '');
});

test('barTone: a decline warning is the only thing that turns a coming bar red', () => {
  assert.equal(barTone(BT({ warning: 'strong' }), '2026-11-19'), 'risk');
  assert.equal(barTone(BT({ warning: 'warn' }), '2026-11-19'), 'risk');
  assert.equal(barTone(BT({ prediction: { prob: { warn: true } } }), '2026-11-19'), 'risk');
});

test('barTone: on the deadline day the stock still counts as coming (a warning stays red)', () => {
  assert.equal(barTone(BT({ sub_end: '2026-11-19', warning: 'strong' }), '2026-11-19'), 'risk');
  assert.equal(barTone(BT({ sub_end: '2026-11-19' }), '2026-11-19'), '');
});

test('barTone: the day after the deadline every bar is "done" (grey), warned, waiting or spac alike', () => {
  assert.equal(barTone(BT({ sub_end: '2026-11-18', warning: 'strong' }), '2026-11-19'), 'done');
  assert.equal(barTone(BT({ sub_end: '2026-11-18', inst_competition: null }), '2026-11-19'), 'done');
  assert.equal(barTone(BT({ is_spac: true, sub_end: '2026-11-18' }), '2026-11-19'), 'done');
});

test('barTone: a listed stock is "done"', () => {
  assert.equal(barTone(BT({ first_close: 12000, final_price: 10000 }), '2026-11-19'), 'done');
  assert.equal(barTone(BT({ first_close: 12000, final_price: 10000, sub_end: '2026-11-18' }), '2026-11-19'), 'done');
});

import { subscriptionFacts, offerInfoRows } from './calendar.js';

const UC = {
  final_price: 19000, band_low: 19000, band_high: 23000, retail_deposit_pct: 50, refund_date: '2026-11-23',
  offer_amount_mil: 15200, total_shares: 800000, retail_shares: 200000, industry: '소프트웨어',
  brokers: [
    { name: '유진투자증권', shares: 160000, limit_text: '16,000 ~ 20,000 주', limit_max: 20000 },
    { name: '신영증권', shares: 40000, limit_text: '1,300 주', limit_max: 1300 },
  ],
  revenue_mil: 12345, net_income_mil: -3600, demand_start: '2026-11-09', demand_end: '2026-11-13', inst_count: 150,
};

test('subscriptionFacts: price, minimum amount (10 shares assumed) and refund day, with real values', () => {
  assert.deepEqual(subscriptionFacts(UC), [
    { k: '공모가', v: '19,000원 (희망 19,000~23,000원)', unknown: false },
    { k: '최소 청약 금액 · 10주 가정', v: '95,000원', unknown: false },
    { k: '환불일', v: '11/23', unknown: false },
  ]);
});

test('subscriptionFacts: before the price is fixed the band top is used and said so', () => {
  const f = subscriptionFacts({ ...UC, final_price: null });
  assert.equal(f[0].v, '희망 19,000~23,000원 · 확정 전');
  assert.equal(f[1].v, '115,000원 (희망 상단 기준)');  // 10 x 23,000 x 50%
});

test('subscriptionFacts: unknown values say 확인 불가 and are never guessed', () => {
  const f = subscriptionFacts({ no: 1, name: 'x' });
  assert.deepEqual(f.map(x => [x.v, x.unknown]), [['확인 불가', true], ['확인 불가', true], ['확인 불가', true]]);
  assert.deepEqual(subscriptionFacts({ ...UC, retail_deposit_pct: null })[1], { k: '최소 청약 금액 · 10주 가정', v: '확인 불가', unknown: true });  // no 50% guess
  assert.equal(subscriptionFacts({ ...UC, final_price: null, band_high: null })[1].unknown, true);
});

test('subscriptionFacts: a price without a band is shown plainly; a band without an exact price is "확정 전"', () => {
  assert.equal(subscriptionFacts({ final_price: 8000 })[0].v, '8,000원');
  assert.equal(subscriptionFacts({ band_low: 10500, band_high: 13000 })[0].v, '희망 10,500~13,000원 · 확정 전');
});

test('offerInfoRows: amount, shares, brokers, industry, financials, demand period, institutions', () => {
  const rows = offerInfoRows({ ...UC, retail_competition: 128.456, inst_count: 150 });
  assert.deepEqual(rows, [
    { k: '공모금액', v: '152억 원' },
    { k: '공모주식', v: '총 800,000주 · 일반 200,000주 (25%)' },
    { k: '유진투자증권', v: '160,000주 · 한도 20,000주' },
    { k: '신영증권', v: '40,000주 · 한도 1,300주' },
    { k: '업종', v: '소프트웨어' },
    { k: '매출액', v: '123억 원' },
    { k: '순이익', v: '-36억 원' },
    { k: '수요예측', v: '11/9~11/13' },
    { k: '참여 기관', v: '150곳' },
    { k: '일반청약 경쟁률', v: '128.46:1' },
  ]);
});

test('offerInfoRows: rows without a value are left out; nothing known gives no rows', () => {
  assert.deepEqual(offerInfoRows({ no: 1, name: 'x' }), []);
  const rows = offerInfoRows({ offer_amount_mil: 40000, brokers: [] });
  assert.deepEqual(rows, [{ k: '공모금액', v: '400억 원' }]);
  assert.deepEqual(offerInfoRows({ total_shares: 5000000 }), [{ k: '공모주식', v: '총 5,000,000주' }]);
  assert.deepEqual(offerInfoRows({ brokers: [{ name: '가증권', shares: 10000, limit_text: '-', limit_max: null }] }), [{ k: '가증권', v: '10,000주' }]);
});

test('offerInfoRows: a large amount gets a thousands separator', () => {
  assert.equal(offerInfoRows({ offer_amount_mil: 152000 })[0].v, '1,520억 원');
});

test('subscriptionFacts: a band whose ends are equal (a spac) is shown as one price, not "2,000~2,000"', () => {
  assert.equal(subscriptionFacts({ band_low: 2000, band_high: 2000 })[0].v, '희망 2,000원 · 확정 전');
  assert.equal(subscriptionFacts({ final_price: 2000, band_low: 2000, band_high: 2000 })[0].v, '2,000원 (희망 2,000원)');
});
