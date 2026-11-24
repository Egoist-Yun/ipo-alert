import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeBroker, brokerLinks, showBrokerButtons, isAndroid, brokerAction, isNativeApp } from './brokers.js';
import * as brokers from './brokers.js';

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

test('brokerLinks exposes the package of verified brokers only', () => {
  assert.equal(brokerLinks(['유진증권'])[0].pkg, 'com.eugenefn.smartchampion2');
  assert.equal(brokerLinks(['신영증권'])[0].pkg, null);
});

test('inside the app a verified broker is launched directly with a Play Store fallback', () => {
  const link = brokerLinks(['유진투자증권'])[0];
  assert.deepEqual(brokerAction(link, true), {
    type: 'launch', url: 'com.eugenefn.smartchampion2', fallback: 'market://details?id=com.eugenefn.smartchampion2',
  });
});

test('inside the app an unknown broker still opens the Play Store search', () => {
  const link = brokerLinks(['신영증권'])[0];
  assert.deepEqual(brokerAction(link, true), { type: 'link', href: link.href });
});

test('outside the app the intent link is kept', () => {
  const link = brokerLinks(['유진투자증권'])[0];
  assert.deepEqual(brokerAction(link, false), { type: 'link', href: link.href });
});

test('isNativeApp is safe in any environment', () => {
  assert.equal(isNativeApp(undefined), false);
  assert.equal(isNativeApp({}), false);
  assert.equal(isNativeApp({ Capacitor: {} }), false);
  assert.equal(isNativeApp({ Capacitor: { isNativePlatform: () => false } }), false);
  assert.equal(isNativeApp({ Capacitor: { isNativePlatform: () => true } }), true);
});

test('내 증권사는 표기 차이를 정리하고 주간사 순서대로 한 번씩 표시한다', () => {
  const ipo = { underwriters: ['유진증권', '(주) 삼성 증권', '유진투자증권', '신영증권'] };
  const mine = new Set(['삼성증권', '유진투자증권']);
  assert.deepEqual(brokers.myBrokerMatches(ipo, mine), ['유진투자증권', '삼성증권']);
});

test('일치하는 주간사가 있을 때만 내 증권사를 표시한다', () => {
  const mine = new Set(['삼성증권']);
  assert.deepEqual(brokers.myBrokerMatches({}, mine), []);
  assert.deepEqual(brokers.myBrokerMatches({ underwriters: [] }, mine), []);
  assert.deepEqual(brokers.myBrokerMatches({ underwriters: ['신영증권'] }, mine), []);
  assert.deepEqual(brokers.myBrokerMatches({ underwriters: ['삼성증권'] }, new Set()), []);
});

test('저장된 내 증권사 이름을 정리하고 잘못된 항목은 건너뛴다', () => {
  const storage = new Map([['ipo-my-brokers', '["유진증권","유진투자증권","(주) 삼성 증권",1,null," "]']]);
  assert.deepEqual(brokers.readMyBrokers({ getItem: key => storage.get(key) }), new Set(['유진투자증권', '삼성증권']));
});

test('저장 값이 비어 있거나 읽을 수 없으면 선택이 비어 있다', () => {
  for (const value of [null, '{', '{}', '"삼성증권"']) {
    assert.deepEqual(brokers.readMyBrokers({ getItem: () => value }), new Set());
  }
  assert.deepEqual(brokers.readMyBrokers({ getItem() { throw new Error('저장소 차단'); } }), new Set());
});

test('내 증권사를 선택하고 해제해도 기존 Set은 그대로다', () => {
  const initial = new Set(['삼성증권']);
  const selected = brokers.toggleMyBroker(initial, '(주) 유진증권');
  const cleared = brokers.toggleMyBroker(selected, '유진투자증권');
  assert.notEqual(selected, initial);
  assert.notEqual(cleared, selected);
  assert.deepEqual(initial, new Set(['삼성증권']));
  assert.deepEqual(selected, new Set(['삼성증권', '유진투자증권']));
  assert.deepEqual(cleared, initial);
});

test('내 증권사는 이름순으로 저장하고 저장소 오류는 전파하지 않는다', () => {
  const stored = new Map();
  const mine = new Set(['유진투자증권', '삼성증권', 'KB증권']);
  brokers.saveMyBrokers({ setItem: (key, value) => stored.set(key, value) }, mine);
  assert.equal(stored.get('ipo-my-brokers'), '["KB증권","삼성증권","유진투자증권"]');
  assert.doesNotThrow(() => brokers.saveMyBrokers({ setItem() { throw new Error('저장소 차단'); } }, mine));
});
