import argparse
import math
import warnings
from dataclasses import dataclass

import numpy as np

from ipo import config
from ipo.collect import market_heat, market_mood
from ipo.models import Ipo, first_day_return
from ipo.patterns import PATTERNS


@dataclass(frozen=True)
class Ctx:
    mood: float | None = None   # share of the latest listings that closed below the offer price
    heat: float | None = None   # median first-day return of the latest listings


NO_CTX = Ctx()


def clip_return(x: float) -> float:
    return min(max(x, config.RETURN_MIN), config.RETURN_MAX)


def _log(v):
    return math.log(v) if v and v > 0 else None


def _ratio(a, b):
    return a / b if a is not None and b and b > 0 else None


def _mcap(i: Ipo):
    """Market cap at the offer price in million KRW (capital / par = shares after the IPO)."""
    if None in (i.final_price, i.capital_mil, i.par_value) or not i.par_value:
        return None
    return i.final_price * i.capital_mil / i.par_value


def _price_pos(i: Ipo, c: Ctx):
    if None in (i.final_price, i.band_low, i.band_high) or i.band_high <= i.band_low:
        return None
    return (i.final_price - i.band_low) / (i.band_high - i.band_low)


# 38커뮤니케이션 writes the KOSPI board as "거래소" (most), rarely "코스피"/"유가증권"; anything else (코스닥, 코넥스) counts as 0.
KOSPI_LABELS = {"거래소", "유가증권", "코스피"}

FEATURES = {
    "comp": lambda i, c: _log(i.inst_competition),
    "lockup": lambda i, c: i.lockup_pct,
    "price_pos": _price_pos,
    "below_band": lambda i, c: i.below_band_pct,
    "float": lambda i, c: i.float_pct,
    "mood": lambda i, c: c.mood,
    "heat": lambda i, c: c.heat,
    "offer_amt": lambda i, c: _log(i.offer_amount_mil),
    "kospi": lambda i, c: None if i.market is None else float(i.market in KOSPI_LABELS),
    "bio": lambda i, c: float(i.is_bio),
    "old_share": lambda i, c: i.old_share_pct,
    "loss": lambda i, c: None if i.net_income_mil is None else float(i.net_income_mil < 0),
    "revenue": lambda i, c: _log(i.revenue_mil),
    "mcap": lambda i, c: _log(_mcap(i)),
    "offer_ratio": lambda i, c: _ratio(i.offer_amount_mil, _mcap(i)),
    "psr": lambda i, c: _log(_ratio(_mcap(i), i.revenue_mil)),
    "inst_count": lambda i, c: _log(i.inst_count),
    "retail": lambda i, c: _log(i.retail_competition),  # known only after the subscription closes
}
FEATURE_NAMES = list(FEATURES)
POST_SUBSCRIPTION = {"retail"}  # never offered to the pre-subscription model
PRE_NAMES = [n for n in FEATURE_NAMES if n not in POST_SUBSCRIPTION]


def features(ipo: Ipo, ctx: Ctx | None, names: list[str] | None = None) -> list[float | None]:
    ctx = ctx or NO_CTX
    return [FEATURES[n](ipo, ctx) for n in (names or FEATURE_NAMES)]


def open_return(h: Ipo) -> float | None:
    if not h.open_price or not h.final_price:
        return None
    return h.open_price / h.final_price - 1


def _usable(history: list[Ipo]) -> list[Ipo]:
    return [h for h in history if not h.is_spac and first_day_return(h) is not None]


def context_map(history: list[Ipo]) -> dict[int, Ctx]:
    out = {}
    for h in history:
        before = h.sub_start or h.listing_date
        out[h.no] = Ctx(market_mood(history, before), market_heat(history, before)) if before else NO_CTX
    return out


def _target_ctx(target: Ipo, history: list[Ipo], ctxs: dict | None) -> Ctx:
    if ctxs is not None and target.no in ctxs:
        return ctxs[target.no]
    before = target.sub_start or target.listing_date or "9999-12-31"
    return Ctx(market_mood(history, before), market_heat(history, before))


def _row(ipo: Ipo, ctxs: dict | None, names: list[str]) -> np.ndarray:
    ctx = (ctxs or {}).get(ipo.no, NO_CTX)
    return np.array([np.nan if v is None else v for v in features(ipo, ctx, names)], dtype=float)


def _coverage(items: list[Ipo], ctxs: dict | None, name: str) -> float:
    if not items:
        return 0.0
    return sum(1 for i in items if features(i, (ctxs or {}).get(i.no, NO_CTX), [name])[0] is not None) / len(items)


def coverage_names(items: list[Ipo], ctxs: dict | None = None) -> list[str]:
    return [n for n in PRE_NAMES if _coverage(items, ctxs, n) >= config.SELECT_MIN_COVERAGE]


def _stats(X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mean = np.nanmean(X, axis=0)
        std = np.nanstd(X, axis=0)
    return np.nan_to_num(mean), np.where(np.isnan(std) | (std == 0), 1.0, std)


def neighbors(target: Ipo, history: list[Ipo], k: int, ctxs: dict | None = None,
              names: list[str] | None = None) -> list[Ipo]:
    pool = [h for h in _usable(history) if h.no != target.no]
    if not pool:
        return []
    names = names or coverage_names(pool, ctxs)
    ctxs = dict(ctxs or {})
    ctxs.setdefault(target.no, _target_ctx(target, history, ctxs))
    X = np.array([_row(h, ctxs, names) for h in pool])
    mean, std = _stats(X)
    d = (((X - mean) / std) - ((_row(target, ctxs, names) - mean) / std)) ** 2
    cnt = (~np.isnan(d)).sum(axis=1)
    dist = np.where(cnt >= config.MIN_VALID_DIMS, np.nansum(d, axis=1) / np.maximum(cnt, 1), np.inf)
    order = [i for i in np.argsort(dist, kind="stable") if np.isfinite(dist[i])][:k]
    return [pool[i] for i in order]


def knn_summary(nbrs: list[Ipo], final_price: int) -> dict:
    rets = np.array([first_day_return(n) for n in nbrs])
    p25, med, p75 = np.percentile(rets, [25, 50, 75])
    return {
        "median": float(med), "p25": float(p25), "p75": float(p75),
        "down_count": int((rets < 0).sum()), "n": len(nbrs),
        "price_low": int(round(final_price * (1 + clip_return(p25)))),
        "price_high": int(round(final_price * (1 + clip_return(p75)))),
        "items": [{"no": n.no, "name": n.name, "return": float(r)} for n, r in zip(nbrs, rets)],
    }


@dataclass
class _Scaler:
    names: list[str]
    median: np.ndarray
    mean: np.ndarray
    std: np.ndarray

    @classmethod
    def fit(cls, X: np.ndarray, names: list[str]) -> tuple["_Scaler", np.ndarray]:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            med = np.nan_to_num(np.nanmedian(X, axis=0)) if X.shape[1] else np.zeros(0)
        X = np.where(np.isnan(X), med, X)
        mean, std = _stats(X)
        return cls(names, med, mean, std), (X - mean) / std

    def transform(self, ipo: Ipo, ctx: Ctx | None) -> np.ndarray:
        x = _row(ipo, {ipo.no: ctx or NO_CTX}, self.names)
        return (np.where(np.isnan(x), self.median, x) - self.mean) / self.std


@dataclass
class Model:
    scaler: _Scaler
    coef: np.ndarray
    intercept: float
    log: bool = False

    def predict(self, ipo: Ipo, ctx: Ctx | None) -> float:
        v = float(self.scaler.transform(ipo, ctx) @ self.coef + self.intercept)
        return float(np.expm1(v)) if self.log else v


def _design(pool: list[Ipo], ctxs: dict | None, names: list[str]):
    X = np.array([_row(h, ctxs, names) for h in pool]).reshape(len(pool), len(names))
    scaler, Z = _Scaler.fit(X, names)
    return pool, scaler, Z


def fit_ridge(history: list[Ipo], ctxs: dict | None = None, names: list[str] | None = None,
              yfun=first_day_return, log: bool = False) -> Model:
    """Ridge regression of a return. log=True fits log(1+r), which is less dragged by +200% outliers."""
    names = names or coverage_names(_usable(history), ctxs)
    pool, scaler, Z = _design([h for h in _usable(history) if yfun(h) is not None], ctxs, names)
    y = np.array([yfun(h) for h in pool])
    if log:
        y = np.log1p(y)
    yb = float(y.mean())
    coef = np.linalg.solve(Z.T @ Z + config.RIDGE_ALPHA * np.eye(Z.shape[1]), Z.T @ (y - yb))
    return Model(scaler, coef, yb, log)


def _clip_p(p: float) -> float:
    return min(max(p, config.PROB_CLIP), 1 - config.PROB_CLIP)


@dataclass
class LogitModel:
    scaler: _Scaler
    w: np.ndarray

    def predict(self, ipo: Ipo, ctx: Ctx | None) -> float:
        z = self.scaler.transform(ipo, ctx)
        return _clip_p(float(1 / (1 + np.exp(-(self.w[0] + z @ self.w[1:])))))


def fit_logistic(history: list[Ipo], ctxs: dict | None = None, names: list[str] | None = None,
                 yfun=first_day_return) -> LogitModel:
    """P(return < 0) for yfun (first-day close by default), ridge-penalised logistic regression fitted by IRLS."""
    names = names or coverage_names(_usable(history), ctxs)
    pool, scaler, Z = _design([h for h in _usable(history) if yfun(h) is not None], ctxs, names)
    y = np.array([1.0 if yfun(h) < 0 else 0.0 for h in pool])
    X = np.hstack([np.ones((len(pool), 1)), Z])
    reg = config.LOGIT_ALPHA * np.eye(X.shape[1])
    reg[0, 0] = 0.0
    w = np.zeros(X.shape[1])
    for _ in range(30):
        p = 1 / (1 + np.exp(-np.clip(X @ w, -30, 30)))
        grad = X.T @ (p - y) + reg @ w
        hess = (X.T * (p * (1 - p) + 1e-6)) @ X + reg
        step = np.linalg.solve(hess, grad)
        w -= step
        if np.abs(step).max() < 1e-7:
            break
    return LogitModel(scaler, w)


def _base_rate(past: list[Ipo]) -> float:
    return _clip_p(sum(1 for p in past if first_day_return(p) < 0) / len(past))


def _sorted_items(history: list[Ipo]) -> list[Ipo]:
    return sorted((h for h in _usable(history) if h.listing_date), key=lambda h: (h.listing_date, h.no))


def _past_of(items: list[Ipo], upto: int, target: Ipo) -> list[Ipo]:
    cutoff = target.sub_start or target.listing_date
    return [p for p in items[:upto] if p.listing_date < cutoff]


def _ensemble(target: Ipo, past: list[Ipo], ctxs: dict, names: list[str], yfun) -> dict | None:
    """Average of the k-nearest-neighbour median and the log-return ridge for one target return."""
    rows = [p for p in past if yfun(p) is not None]
    if len(rows) < config.MIN_TRAIN:
        return None
    base = float(np.median([yfun(p) for p in rows]))
    nb = neighbors(target, rows, config.K_NEIGHBORS, ctxs, names)
    knn = float(np.median([yfun(x) for x in nb])) if nb else base
    reg = clip_return(fit_ridge(rows, ctxs, names, yfun, log=True).predict(target, ctxs.get(target.no)))
    return {"knn": knn, "reg": reg, "ens": clip_return((knn + reg) / 2), "base": base}


def _logloss(p: float, down: bool) -> float:
    return -math.log(p if down else 1 - p)


def select_features(history: list[Ipo], names: list[str] | None = None) -> list[str]:
    """Greedy forward selection by walk-forward log loss on the older 70% of the data.
    The newest 30% (the test window used by evaluate) is never looked at."""
    items = _sorted_items(history)
    n = len(items)
    sel = items[: n - max(1, round(config.EVAL_TEST_RATIO * n))]
    m = len(sel)
    vstart = max(config.MIN_TRAIN, int((1 - config.EVAL_TEST_RATIO) * m))
    if m <= vstart:
        return []
    ctxs = context_map(items)
    cands = [c for c in (names or PRE_NAMES) if _coverage(sel, ctxs, c) >= config.SELECT_MIN_COVERAGE]

    def score(cols: list[str]) -> float:
        total, count = 0.0, 0
        for start in range(vstart, m, config.SELECT_CHUNK):
            past = _past_of(sel, start, sel[start])
            if len(past) < config.MIN_TRAIN:
                continue
            model = fit_logistic(past, ctxs, cols) if cols else None
            base = _base_rate(past)
            for t in sel[start:start + config.SELECT_CHUNK]:
                p = model.predict(t, ctxs.get(t.no)) if model else base
                total += _logloss(p, first_day_return(t) < 0)
                count += 1
        return total / count if count else float("inf")

    chosen: list[str] = []
    best = score([])
    while len(chosen) < config.SELECT_MAX_FEATURES:
        trials = [(score(chosen + [c]), c) for c in cands if c not in chosen]
        if not trials:
            break
        sc, pick = min(trials)
        if best - sc < config.SELECT_MIN_GAIN:
            break
        chosen.append(pick)
        best = sc
    return chosen


def walk_forward(history: list[Ipo], names: list[str] | None = None) -> list[dict]:
    items = _sorted_items(history)
    n = len(items)
    if n == 0:
        return []
    ctxs = context_map(items)
    names = names or coverage_names(items, ctxs)
    start = n - max(1, round(config.EVAL_TEST_RATIO * n))
    records = []
    for idx in range(start, n):
        target = items[idx]
        past = _past_of(items, idx, target)
        if len(past) < config.MIN_TRAIN:
            continue
        ctx = ctxs.get(target.no)
        close = _ensemble(target, past, ctxs, names, first_day_return)
        rec = {
            "no": target.no,
            "actual": first_day_return(target),
            "baseline": close["base"], "knn": close["knn"], "model": close["reg"], "ens": close["ens"],
            "p_down": fit_logistic(past, ctxs, names).predict(target, ctx),
            "p_base": _base_rate(past),
            "open_actual": open_return(target),
        }
        opened = _ensemble(target, past, ctxs, names, open_return) if rec["open_actual"] is not None else None
        for key, val in (("open_baseline", "base"), ("open_knn", "knn"), ("open_model", "reg"), ("open_ens", "ens")):
            rec[key] = opened[val] if opened else None
        records.append(rec)
    return records


def evaluate(history: list[Ipo], names: list[str] | None = None) -> dict | None:
    recs = walk_forward(history, names)
    if not recs:
        return None
    out = {}
    for method, actual in (("knn", "actual"), ("model", "actual"), ("baseline", "actual"), ("ens", "actual"),
                           ("open_knn", "open_actual"), ("open_model", "open_actual"),
                           ("open_baseline", "open_actual"), ("open_ens", "open_actual")):
        rows = [r for r in recs if r[method] is not None and r[actual] is not None]
        if not rows:
            continue
        err = [abs(r[method] - r[actual]) for r in rows]
        hit = [(r[method] < 0) == (r[actual] < 0) for r in rows]
        out[method] = {"mae": float(np.mean(err)), "direction_acc": float(np.mean(hit)), "n": len(rows)}
    for key, field in (("prob", "p_down"), ("prob_base", "p_base")):
        ps = [r[field] for r in recs]
        downs = [r["actual"] < 0 for r in recs]
        out[key] = {
            "logloss": float(np.mean([_logloss(p, d) for p, d in zip(ps, downs)])),
            "brier": float(np.mean([(p - d) ** 2 for p, d in zip(ps, downs)])),
            "accuracy": float(np.mean([(p >= 0.5) == d for p, d in zip(ps, downs)])),
            "n": len(recs),
        }
    return out


def _beats_baseline(ev: dict | None, method: str, base: str = "baseline") -> bool:
    return bool(ev and method in ev and base in ev and ev[method]["mae"] < ev[base]["mae"])


def _prob_beats_base(ev: dict | None) -> bool:
    return bool(ev and "prob" in ev and "prob_base" in ev and ev["prob"]["logloss"] < ev["prob_base"]["logloss"])


def predict_for(ipo: Ipo, history: list[Ipo], eval_result: dict | None,
                names: list[str] | None = None, calibration: dict | None = None,
                full_history: list[Ipo] | None = None, post_eval: dict | None = None) -> dict | None:
    """calibration: warning thresholds (see calibrate). full_history: 2015+ history used only for the
    post-subscription open-down probability. post_eval: evaluate(recent, names + retail)."""
    if ipo.is_spac or ipo.final_price is None or ipo.inst_competition is None:
        return None
    pool = _usable(history)
    ctxs = context_map(pool)
    ctx = _target_ctx(ipo, pool, None)
    ctxs[ipo.no] = ctx
    names = names or coverage_names(pool, ctxs)

    knn = None
    if _beats_baseline(eval_result, "knn"):
        nb = neighbors(ipo, pool, config.K_NEIGHBORS, ctxs, names)
        knn = knn_summary(nb, ipo.final_price) if nb else None

    enough = len(pool) >= config.MIN_TRAIN

    def priced(key: str, base: str, yfun, ev: dict | None, cols: list[str], ikey: str) -> dict | None:
        if not (enough and _beats_baseline(ev, key, base)):
            return None
        e = _ensemble(ipo, pool, ctxs, cols, yfun)
        if e is None:
            return None
        res = {"return": e["ens"], "price": int(round(ipo.final_price * (1 + e["ens"]))),
               "mae": ev[key]["mae"], "direction_acc": ev[key]["direction_acc"]}
        iv = ((calibration or {}).get("interval") or {}).get(ikey)
        if iv:
            mid = _log1p(e["ens"])
            res.update(price_low=int(round(ipo.final_price * math.exp(mid + iv["q10"]))),
                       price_high=int(round(ipo.final_price * math.exp(mid + iv["q90"]))),
                       range_coverage=iv["test_coverage"])
        return res

    subscribed = ipo.retail_competition is not None
    close = priced("ens", "baseline", first_day_return, eval_result, names, "close")
    opened = None
    if subscribed and post_eval:
        opened = priced("open_ens", "open_baseline", open_return, post_eval, names + ["retail"], "open_post")
        if opened:
            opened["uses_retail"] = True
    if opened is None:
        opened = priced("open_ens", "open_baseline", open_return, eval_result, names, "open_pre")

    prob = None
    if enough and _prob_beats_base(eval_result):
        prob = {"p_down": fit_logistic(pool, ctxs, names).predict(ipo, ctx), "n": len(pool)}
        if calibration:
            c = calibration["close"]
            prob.update(threshold=c["threshold"], warn=bool(prob["p_down"] >= c["threshold"]),
                        precision=c["test"]["precision"], recall=c["test"]["recall"],
                        caught=c["test"].get("caught"), warned=c["test"].get("warned"),
                        n_down=c["test"].get("n_down"),
                        strong_precision=c.get("strong_test", {}).get("precision"),
                        strong_recall=c.get("strong_test", {}).get("recall"),
                        strong_caught=c.get("strong_test", {}).get("caught"),
                        strong_warned=c.get("strong_test", {}).get("warned"))

    open_down = None
    if subscribed and calibration and full_history:
        fh = _usable(full_history)
        fctx = context_map(fh)
        fctx[ipo.no] = _target_ctx(ipo, fh, None)
        p = fit_logistic(fh, fctx, names + ["retail"], open_return).predict(ipo, fctx[ipo.no])
        c = calibration["open"]
        open_down = {"p_down": p, "threshold": c["threshold"], "warn": bool(p >= c["threshold"]),
                     "precision": c["test"]["precision"], "recall": c["test"]["recall"], "n": len(fh),
                     "caught": c["test"].get("caught"), "warned": c["test"].get("warned"),
                     "n_down": c["test"].get("n_down"),
                     "strong_precision": c.get("strong_test", {}).get("precision"),
                     "strong_recall": c.get("strong_test", {}).get("recall"),
                     "strong_caught": c.get("strong_test", {}).get("caught"),
                     "strong_warned": c.get("strong_test", {}).get("warned")}
    upbeat = ((knn is not None and knn["median"] > 0) or (close is not None and close["return"] > 0)
              or (prob is not None and prob["p_down"] < 0.5))
    conflict = ipo.flag_count >= config.CONFLICT_FLAGS and upbeat
    return {"knn": knn, "open": opened, "close": close, "prob": prob, "open_down": open_down,
            "conflict": conflict, "accuracy": eval_result, "features": names}


def warning_threshold(scores: list[float], ys: list, recall: float = config.WARN_RECALL) -> float:
    """Highest threshold on a 0.05 grid that still catches `recall` of the actual declines."""
    pos = sum(1 for y in ys if y)
    best = 0.05
    for th in [round(float(x), 2) for x in np.arange(0.05, 0.96, 0.05)]:
        caught = sum(1 for s, y in zip(scores, ys) if y and s >= th)
        if pos and caught / pos >= recall:
            best = th
    return best


def _windows(recent: list[Ipo]) -> tuple[list[Ipo], list[Ipo]]:
    items = _sorted_items(recent)
    n = len(items)
    ts = n - max(1, round(config.EVAL_TEST_RATIO * n))
    vs = max(config.MIN_TRAIN, int((1 - config.EVAL_TEST_RATIO) * ts))
    return items[vs:ts], items[ts:]


def _down_scores(window: list[Ipo], train: list[Ipo], ctxs: dict, names: list[str], yfun) -> list[tuple]:
    out = []
    for t in window:
        if yfun(t) is None:
            continue
        cutoff = t.sub_start or t.listing_date
        past = [p for p in train if p.listing_date < cutoff and yfun(p) is not None]
        if len(past) < config.MIN_TRAIN:
            continue
        out.append((fit_logistic(past, ctxs, names, yfun).predict(t, ctxs.get(t.no)), yfun(t) < 0, t))
    return out


def _warn_stats(pairs: list[tuple], th: float, agree=None) -> dict:
    pos = sum(1 for _, y, _t in pairs if y)
    warned = [y for p, y, t in pairs if p >= th and (agree is None or agree(t))]
    return {"recall": (sum(warned) / pos) if pos else 0.0,
            "precision": (sum(warned) / len(warned)) if warned else 0.0,
            "caught": int(sum(warned)), "warned": len(warned), "n_down": pos, "n": len(pairs)}


def _agree_close(t: Ipo) -> bool:
    return any(p.kind == "risk" and p.phase == "pre" and p.test(t) is True for p in PATTERNS)


def _agree_open(t: Ipo) -> bool:
    return any(p.key == "retail_lock" and p.test(t) is True for p in PATTERNS)


def _log1p(x: float) -> float:
    return math.log1p(max(x, -0.95))


def _log_residuals(window: list[Ipo], train: list[Ipo], ctxs: dict, names: list[str], yfun) -> list[float]:
    """log(1+actual) - log(1+ensemble prediction), each made only from listings before the target."""
    out = []
    for t in window:
        y = yfun(t)
        if y is None:
            continue
        cutoff = t.sub_start or t.listing_date
        e = _ensemble(t, [p for p in train if p.listing_date < cutoff], ctxs, names, yfun)
        if e:
            out.append(_log1p(y) - _log1p(e["ens"]))
    return out


def calibrate(full_history: list[Ipo], recent: list[Ipo], names: list[str]) -> dict:
    """Warning thresholds chosen on the validation window, then measured once on the test window.
    close: pre-subscription P(close < offer) trained on recent listings only.
    open: post-subscription P(open < offer) trained on the whole (2015+) history with retail competition."""
    full = _sorted_items(full_history)
    ctxs = context_map(full)
    val, test = _windows(recent)
    out = {}
    for key, train, cols, yfun in (("close", _sorted_items(recent), names, first_day_return),
                                   ("open", full, names + ["retail"], open_return)):
        v = _down_scores(val, train, ctxs, cols, yfun)
        te = _down_scores(test, train, ctxs, cols, yfun)
        th = warning_threshold([x[0] for x in v], [x[1] for x in v])
        agree = _agree_close if key == "close" else _agree_open
        out[key] = {"threshold": th, "validation": _warn_stats(v, th), "test": _warn_stats(te, th),
                    "strong_validation": _warn_stats(v, th, agree), "strong_test": _warn_stats(te, th, agree)}
    recent_items = _sorted_items(recent)
    intervals = {}
    for key, train, cols, yfun in (("close", recent_items, names, first_day_return),
                                   ("open_pre", recent_items, names, open_return),
                                   ("open_post", full, names + ["retail"], open_return)):
        rv = _log_residuals(val, train, ctxs, cols, yfun)
        rt = _log_residuals(test, train, ctxs, cols, yfun)
        if not rv or len(rv) + len(rt) < 10:
            continue
        lo, hi = np.quantile(rv, [0.1, 0.9])  # measured on the test window with validation-only quantiles
        cover = float(np.mean([lo <= r <= hi for r in rt])) if rt else 0.0
        q10, q90 = np.quantile(rv + rt, [0.1, 0.9])  # shown to the user: all residuals
        intervals[key] = {"q10": float(q10), "q90": float(q90), "test_coverage": cover, "n": len(rv) + len(rt)}
    out["interval"] = intervals
    return out


def report(history: list[Ipo], names: list[str] | None = None) -> str:
    ev = evaluate(history, names)
    if ev is None:
        return "검증할 과거 종목이 부족합니다.\n"
    lines = [f"## 가격 예측 검증 (시간 순서 검증, 종목 {ev['baseline']['n']}개)", "",
             f"사용 변수: {', '.join(names) if names else '값이 절반 이상 있는 모든 변수'}", ""]
    labels = {"knn": "비슷한 종목 비교", "model": "로그 수익률 회귀", "ens": "두 방식 평균 (화면에 표시)",
              "baseline": "기준(과거 가운데 값)"}
    for title, prefix, base in (("첫날 종가", "", "baseline"), ("시초가", "open_", "open_baseline")):
        if base not in ev:
            continue
        lines += [f"### {title}", "", "| 방식 | 평균 오차(%p) | 공모가 위/아래 적중률 |", "|---|---|---|"]
        for m in ("knn", "model", "ens", "baseline"):
            key = prefix + m
            if key in ev:
                lines.append(f"| {labels[m]} | {ev[key]['mae'] * 100:.1f} | {ev[key]['direction_acc'] * 100:.0f}% |")
        shown = _beats_baseline(ev, prefix + "ens", base)
        lines += ["", f"화면 표시: {'예 (기준보다 오차가 작음)' if shown else '아니오 (기준보다 낫지 않음)'}", ""]
    pr, pb = ev["prob"], ev["prob_base"]
    lines += ["### 공모가 아래로 끝날 확률", "", "| 방식 | log loss | Brier | 적중률 |", "|---|---|---|---|",
              f"| 모델 | {pr['logloss']:.3f} | {pr['brier']:.3f} | {pr['accuracy'] * 100:.0f}% |",
              f"| 기준(과거 하락 비율) | {pb['logloss']:.3f} | {pb['brier']:.3f} | {pb['accuracy'] * 100:.0f}% |",
              "", f"화면 표시: {'예' if _prob_beats_base(ev) else '아니오'}"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    from ipo.history import load_history

    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--select", action="store_true", help="choose variables by forward selection first")
    args = ap.parse_args()
    hist = load_history(args.report)
    chosen = select_features(hist) if args.select else None
    if chosen is not None:
        print(f"선택된 변수: {chosen}\n")
    print(report(hist, chosen))
