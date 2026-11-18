import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeBroker, brokerLinks, showBrokerButtons, isAndroid } from './brokers.js';

const fallback = pkg => encodeURIComponent(`https://play.google.com/store/apps/details?id=${pkg}`);

test('verified broker opens its app by package with Play Store fallback', () => {
  const [l] = brokerLinks(['한국투자증권㈜']);
  assert.equal(l.verified, true);
  assert.equal(l.name, '한국투자증권');
  assert.equal(l.href, `intent://#Intent;package=com.truefriend.neosmartarenewal;S.browser_fallback_url=${fallback('com.truefriend.neosmartarenewal')};end`);
});

test('name variants map to the same broker', () => {
  assert.equal(normalizeBroker(' 케이비증권 '), 'KB증권');
  assert.equal(normalizeBroker('엔에이치투자증권'), 'NH투자증권');
  assert.equal(normalizeBroker('유진증권'), '유진투자증권');
  assert.equal(normalizeBroker('미래에셋대우'), '미래에셋증권');
  assert.equal(normalizeBroker('(주)삼성증권'), '삼성증권');
  assert.match(brokerLinks(['케이비증권'])[0].href, /package=com\.kbsec\.mts\.iplustarngm2;/);
});

test('unknown broker opens Play Store search, never a guessed package', () => {
  const [l] = brokerLinks(['신영증권']);
  assert.equal(l.verified, false);
  assert.equal(l.href, `market://search?q=${encodeURIComponent('신영증권')}&c=apps`);
});

test('duplicates and blanks produce one button each, order kept', () => {
  const ls = brokerLinks(['NH투자증권', '엔에이치투자증권', '', '삼성증권']);
  assert.deepEqual(ls.map(l => l.name), ['NH투자증권', '삼성증권']);
});

test('buttons only while the subscription is open', () => {
  const ipo = { sub_end: '2026-11-19', is_spac: false };
  assert.equal(showBrokerButtons(ipo, '2026-11-18'), true);
  assert.equal(showBrokerButtons(ipo, '2026-11-19'), true);
  assert.equal(showBrokerButtons(ipo, '2026-11-20'), false);
  assert.equal(showBrokerButtons({ sub_end: null }, '2026-11-18'), false);
  assert.equal(showBrokerButtons({ ...ipo, is_spac: true }, '2026-11-18'), false);
});

test('isAndroid', () => {
  assert.equal(isAndroid('Mozilla/5.0 (Linux; Android 14; SM-S918N) AppleWebKit/537.36 Chrome/131 Mobile Safari/537.36'), true);
  assert.equal(isAndroid('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15'), false);
  assert.equal(isAndroid('Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131'), false);
});
