// Brokerage apps verified on Google Play on 2026-11-18 (see docs/superpowers/specs/2026-11-18-broker-app-button-design.md).
// Never add a guessed package name: unknown brokers fall back to a Play Store search.
export const BROKER_APPS = {
  '한국투자증권': 'com.truefriend.neosmartarenewal',
  '미래에셋증권': 'com.miraeasset.trade',
  '삼성증권': 'com.samsungpop.android.mpop',
  '키움증권': 'com.kiwoom.heromts',
  'NH투자증권': 'com.wooriwm.txsmart',
  'KB증권': 'com.kbsec.mts.iplustarngm2',
  '대신증권': 'com.daishin.creon',
  '신한투자증권': 'com.shinhaninvest.nsmts',
  '유진투자증권': 'com.eugenefn.smartchampion2',
  'IBK투자증권': 'com.ibks.ione.mts',
  '유안타증권': 'com.yuanta.tradars',
  '현대차증권': 'com.hmsec.mts',
};

const ALIASES = [
  [/^케이비/, 'KB'],
  [/^엔에이치/, 'NH'],
  [/^아이비케이/, 'IBK'],
  [/^유진증권$/, '유진투자증권'],
  [/^미래에셋대우$/, '미래에셋증권'],
];

export function normalizeBroker(name) {
  let n = String(name || '').replace(/\(주\)|㈜|\s+/g, '');
  for (const [re, to] of ALIASES) n = n.replace(re, to);
  return n;
}

const MY_BROKERS_KEY = 'ipo-my-brokers';

export function readMyBrokers(storage) {
  try {
    const list = JSON.parse(storage.getItem(MY_BROKERS_KEY));
    if (!Array.isArray(list)) return new Set();
    return new Set(list.filter(name => typeof name === 'string').map(normalizeBroker).filter(Boolean));
  } catch (e) {
    return new Set();
  }
}

export function saveMyBrokers(storage, set) {
  try { storage.setItem(MY_BROKERS_KEY, JSON.stringify([...set].sort())); } catch (e) { /* storage blocked */ }
}

export function toggleMyBroker(set, name) {
  const next = new Set(set);
  const broker = normalizeBroker(name);
  if (broker && !next.delete(broker)) next.add(broker);
  return next;
}

export function myBrokerMatches(ipo, mine) {
  if (!mine.size) return [];
  const names = (ipo.underwriters || []).map(normalizeBroker);
  return [...new Set(names.filter(name => name && mine.has(name)))];
}

export function brokerLinks(underwriters) {
  const seen = new Set();
  const out = [];
  for (const raw of underwriters || []) {
    const name = normalizeBroker(raw);
    if (!name || seen.has(name)) continue;
    seen.add(name);
    const pkg = BROKER_APPS[name];
    const href = pkg
      ? `intent://#Intent;package=${pkg};S.browser_fallback_url=${encodeURIComponent(`https://play.google.com/store/apps/details?id=${pkg}`)};end`
      : `market://search?q=${encodeURIComponent(name)}&c=apps`;
    out.push({ name, href, verified: Boolean(pkg), pkg: pkg || null });
  }
  return out;
}

export function showBrokerButtons(ipo, todayIso) {
  return Boolean(ipo && !ipo.is_spac && ipo.sub_end && ipo.sub_end >= todayIso);
}

export function isAndroid(userAgent) {
  return /Android/i.test(userAgent || '');
}

// Inside the Capacitor app a verified broker is launched by package name (AppLauncher.openUrl takes a package name);
// anywhere else the intent / search link is kept.
export function brokerAction(link, native) {
  if (native && link.verified && link.pkg) {
    return { type: 'launch', url: link.pkg, fallback: `market://details?id=${link.pkg}` };
  }
  return { type: 'link', href: link.href };
}

export function isNativeApp(win) {
  return win?.Capacitor?.isNativePlatform?.() === true;
}
