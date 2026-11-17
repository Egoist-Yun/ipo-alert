import test from 'node:test';
import assert from 'node:assert/strict';
import { monthGrid, barsForMonth, listForMonth } from './calendar.js';

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
