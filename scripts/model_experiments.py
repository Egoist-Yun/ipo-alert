"""Offline model experiments (one-off, not part of the nightly run). Reproduces docs/model-experiments.md.
Usage: python scripts/model_experiments.py [kosdaq.json]   (downloads KOSDAQ daily closes from Yahoo if the file is missing)
Tests: KOSDAQ 20-day return variable, time-decay weights, skip-the-warning simulation, bull/bear split, price intervals.
"""
import sys, json, random, bisect, datetime as dt
sys.path.insert(0, '.')
import numpy as np
from ipo import config
from ipo import predict as P
from ipo.history import load_history
from ipo.predict import (_sorted_items, context_map, _windows, warning_threshold, open_return, first_day_return,
                         _usable, _design, _clip_p, _ensemble, LogitModel)

import os, requests
KQ_PATH = sys.argv[1] if len(sys.argv) > 1 else "kosdaq.json"
if not os.path.exists(KQ_PATH):
    r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/%5EKQ11?period1=1420070400&period2=1795000000&interval=1d",
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=30).json()["chart"]["result"][0]
    rows = [(dt.datetime.fromtimestamp(t, dt.timezone(dt.timedelta(hours=9))).date().isoformat(), c)
            for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]) if c]
    json.dump(rows, open(KQ_PATH, "w"))
KQ = json.load(open(KQ_PATH))
dates = [d for d, _ in KQ]; closes = [c for _, c in KQ]
def kq20(i):
    d = i.sub_start or i.listing_date
    if not d: return None
    k = bisect.bisect_left(dates, d)
    return closes[k - 1] / closes[k - 21] - 1 if k - 21 >= 0 else None
P.FEATURES["kq20"] = lambda i, c: kq20(i)

hist = load_history('data/history.json')
base_names = json.load(open('data/model.json', encoding='utf-8'))['names']
full = _sorted_items(hist)
recent = [h for h in hist if h.listing_date and h.listing_date >= config.RECENT_FROM]
ctxs = context_map(full)
val, test = _windows(recent)

def days(a, b): return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days

def fit_w(past, cols, yfun, cutoff, half):
    pool, scaler, Z = _design([h for h in _usable(past) if yfun(h) is not None], ctxs, cols)
    y = np.array([1.0 if yfun(h) < 0 else 0.0 for h in pool])
    wt = np.array([0.5 ** (days(h.listing_date, cutoff) / half) if half else 1.0 for h in pool])
    wt = wt / wt.mean()
    X = np.hstack([np.ones((len(pool), 1)), Z]); reg = config.LOGIT_ALPHA * np.eye(X.shape[1]); reg[0, 0] = 0
    w = np.zeros(X.shape[1])
    for _ in range(30):
        p = 1 / (1 + np.exp(-np.clip(X @ w, -30, 30)))
        g = X.T @ (wt * (p - y)) + reg @ w
        H = (X.T * (wt * p * (1 - p) + 1e-6)) @ X + reg
        s = np.linalg.solve(H, g); w -= s
        if np.abs(s).max() < 1e-7: break
    return LogitModel(scaler, w)

def scores(window, train, cols, yfun, half=None):
    out = []
    for t in window:
        if yfun(t) is None: continue
        cutoff = t.sub_start or t.listing_date
        past = [p for p in train if p.listing_date < cutoff and yfun(p) is not None]
        if len(past) < config.MIN_TRAIN: continue
        out.append((fit_w(past, cols, yfun, cutoff, half).predict(t, ctxs.get(t.no)), yfun(t) < 0, t, yfun(t)))
    return out

def auc(pr):
    pos = [s for s, y, *_ in pr if y]; neg = [s for s, y, *_ in pr if not y]
    return float(np.mean([(p > n) + 0.5 * (p == n) for p in pos for n in neg])) if pos and neg else float('nan')

def stats(t, th):
    pos = sum(1 for _, y, *_ in t if y); w = [y for p, y, *_ in t if p >= th]
    return sum(w), len(w), pos, len(t)

def boot(vals, f, B=1000, seed=3):
    r = random.Random(seed); xs = sorted(f([r.choice(vals) for _ in vals]) for _ in range(B))
    return xs[int(.05 * B)], xs[int(.95 * B)]

def run(label, train, cols, yfun, half=None, show=True):
    v = scores(val, train, cols, yfun, half); t = scores(test, train, cols, yfun, half)
    th = warning_threshold([x[0] for x in v], [x[1] for x in v])
    c, w, pos, n = stats(t, th); br = np.mean([(p - y) ** 2 for p, y, *_ in t])
    if show:
        print(f"{label:34s} th={th:.2f} valAUC={auc(v):.3f} testAUC={auc(t):.3f} Brier={br:.3f} caught {c}/{pos} warned {w} (prec {c/max(w,1)*100:.0f}%)")
    return v, t, th

print("val", len(val), "test", len(test))
fullT = full
for tag, tr, cols0, yf in (("OPEN", fullT, base_names + ["retail"], open_return), ("CLOSE", _sorted_items(recent), base_names, first_day_return)):
    print("==", tag)
    run("base", tr, cols0, yf)
    run("+kq20", tr, cols0 + ["kq20"], yf)
    for h in (180, 365, 730):
        run(f"base decay half={h}d", tr, cols0, yf, h)
    run("+kq20 decay 365", tr, cols0 + ["kq20"], yf, 365)

# simulation: sell at open (OPEN) / hold to close (CLOSE)
def sim(tag, t, th, yf):
    rets = [r for _, _, _, r in t]
    kept = [r for p, _, _, r in t if p < th]; skipped = [r for p, _, _, r in t if p >= th]
    f = lambda s: float(np.mean(s))
    d = [(p, r) for p, _, _, r in t]
    def diff(sample):
        a = np.mean([r for _, r in sample]); b = [r for p, r in sample if p < th]
        return (np.mean(b) if b else 0) - a
    lo, hi = boot(d, diff)
    med = lambda x: float(np.median(x)) if x else float("nan")
    print(f"   중앙값: 전부 {med(rets)*100:+.0f}% | 참여 {med(kept)*100:+.0f}% | 건너뜀 {med(skipped)*100:+.0f}%")
    print(f"{tag}: 전부 평균 {f(rets)*100:+.1f}% 최악 {min(rets)*100:+.0f}% n={len(rets)} | 경고 건너뜀 평균 {f(kept)*100:+.1f}% 최악 {min(kept)*100:+.0f}% 참여 {len(kept)} | 건너뛴 종목 평균 {f(skipped)*100:+.1f}% ({len(skipped)}개)"
          f" | 평균 차이 {(f(kept)-f(rets))*100:+.1f}%p [90% 구간 {lo*100:+.1f}~{hi*100:+.1f}]")
print("== SIMULATION (공모가 대비, 수수료·세금 제외)")
for tag, tr, cols0, yf in (("시초가 매도(청약후)", fullT, base_names + ["retail"], open_return), ("종가 보유(청약전)", _sorted_items(recent), base_names, first_day_return)):
    v, t, th = run(tag + " base", tr, cols0, yf, show=False)
    sim(tag, t, th, yf)

# regime split by KOSDAQ 20d sign (test window)
print("== REGIME (test, kq20<0 = 하락장)")
for tag, tr, cols0, yf in (("OPEN", fullT, base_names + ["retail"], open_return), ("CLOSE", _sorted_items(recent), base_names, first_day_return)):
    v, t, th = run(tag, tr, cols0, yf, show=False)
    for name, f in (("하락장", lambda x: (kq20(x[2]) or 0) < 0), ("상승장", lambda x: (kq20(x[2]) or 0) >= 0)):
        sub = [x for x in t if f(x)]
        c, w, pos, n = stats(sub, th)
        print(f"{tag} {name}: n={n} 하락 {pos}개 | 포착 {c}/{pos} 경고 {w} | AUC={auc(sub):.2f} | 평균수익 {np.mean([x[3] for x in sub])*100:+.0f}%")

# quantile interval
print("== QUANTILE (시초가, ensemble, 로그 잔차)")
def preds(window, train, cols, yf):
    out = []
    for t in window:
        if yf(t) is None: continue
        cutoff = t.sub_start or t.listing_date
        past = [p for p in train if p.listing_date < cutoff]
        e = _ensemble(t, past, ctxs, cols, yf)
        if e: out.append((e["ens"], yf(t)))
    return out
cols = base_names + ["retail"]
pv = preds(val, fullT, cols, open_return); pt = preds(test, fullT, cols, open_return)
lr = lambda p, a: np.log1p(max(a, -.95)) - np.log1p(max(p, -.95))
res = np.array([lr(p, a) for p, a in pv]); q = np.quantile(res, [.1, .5, .9]); print("val 잔차 분위수", np.round(q, 3))
cov = np.mean([(np.log1p(max(a, -.95)) >= np.log1p(max(p, -.95)) + q[0]) and (np.log1p(max(a, -.95)) <= np.log1p(max(p, -.95)) + q[2]) for p, a in pt])
wid = np.mean([np.expm1(np.log1p(max(p, -.95)) + q[2]) - np.expm1(np.log1p(max(p, -.95)) + q[0]) for p, _ in pt])
print(f"test 80% 구간 실제 포함률 {cov*100:.0f}% (n={len(pt)}) 평균 구간 폭 {wid*100:.0f}%p")
