import argparse
import math
import warnings
from dataclasses import dataclass

import numpy as np

from ipo import config
from ipo.collect import market_mood
from ipo.models import Ipo, first_day_return


def clip_return(x: float) -> float:
    return min(max(x, config.RETURN_MIN), config.RETURN_MAX)


def _log(v):
    return math.log(v) if v and v > 0 else None


def features(ipo: Ipo, mood: float | None) -> list[float | None]:
    pos = None
    if None not in (ipo.final_price, ipo.band_low, ipo.band_high) and ipo.band_high > ipo.band_low:
        pos = (ipo.final_price - ipo.band_low) / (ipo.band_high - ipo.band_low)
    return [
        _log(ipo.inst_competition), ipo.lockup_pct, pos, ipo.below_band_pct, ipo.float_pct, mood,
        _log(ipo.offer_amount_mil),
        None if ipo.market is None else float(ipo.market == "유가증권"),
        float(ipo.is_bio),
    ]


def _usable(history: list[Ipo]) -> list[Ipo]:
    return [h for h in history if not h.is_spac and first_day_return(h) is not None]


def _moods(history: list[Ipo]) -> dict[int, float | None]:
    return {h.no: (market_mood(history, h.sub_start or h.listing_date) if (h.sub_start or h.listing_date) else None)
            for h in history}


def _row(ipo: Ipo, moods: dict) -> np.ndarray:
    return np.array([np.nan if v is None else v for v in features(ipo, moods.get(ipo.no))], dtype=float)


def _target_mood(target: Ipo, history: list[Ipo], moods: dict | None) -> float | None:
    if moods is not None and target.no in moods:
        return moods[target.no]
    return market_mood(history, target.sub_start or target.listing_date or "9999-12-31")


def _stats(X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mean = np.nanmean(X, axis=0)
        std = np.nanstd(X, axis=0)
    return np.nan_to_num(mean), np.where(np.isnan(std) | (std == 0), 1.0, std)


def neighbors(target: Ipo, history: list[Ipo], k: int, moods: dict | None = None) -> list[Ipo]:
    pool = [h for h in _usable(history) if h.no != target.no]
    if not pool:
        return []
    moods = dict(moods) if moods is not None else _moods(history)
    moods.setdefault(target.no, _target_mood(target, history, None))
    X = np.array([_row(h, moods) for h in pool])
    mean, std = _stats(X)
    Z = (X - mean) / std
    t = (_row(target, moods) - mean) / std
    d = (Z - t) ** 2
    valid = ~np.isnan(d)
    cnt = valid.sum(axis=1)
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
class Model:
    median: np.ndarray
    mean: np.ndarray
    std: np.ndarray
    coef: np.ndarray
    intercept: float

    def predict(self, ipo: Ipo, mood: float | None) -> float:
        x = _row(ipo, {ipo.no: mood})
        x = np.where(np.isnan(x), self.median, x)
        return float(((x - self.mean) / self.std) @ self.coef + self.intercept)


def fit_ridge(history: list[Ipo], moods: dict | None = None) -> Model:
    pool = _usable(history)
    moods = moods if moods is not None else _moods(history)
    X = np.array([_row(h, moods) for h in pool])
    y = np.array([first_day_return(h) for h in pool])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        med = np.nan_to_num(np.nanmedian(X, axis=0))
    X = np.where(np.isnan(X), med, X)
    mean, std = _stats(X)
    Z = (X - mean) / std
    yb = float(y.mean())
    coef = np.linalg.solve(Z.T @ Z + config.RIDGE_ALPHA * np.eye(Z.shape[1]), Z.T @ (y - yb))
    return Model(med, mean, std, coef, yb)


def walk_forward(history: list[Ipo]) -> list[dict]:
    items = sorted((h for h in _usable(history) if h.listing_date), key=lambda h: (h.listing_date, h.no))
    n = len(items)
    if n == 0:
        return []
    moods = _moods(items)
    start = n - max(1, round(config.EVAL_TEST_RATIO * n))
    records = []
    for idx in range(start, n):
        target = items[idx]
        cutoff = target.sub_start or target.listing_date
        past = [p for p in items[:idx] if p.listing_date < cutoff]
        if len(past) < config.MIN_TRAIN:
            continue
        base = float(np.median([first_day_return(p) for p in past]))
        nb = neighbors(target, past, config.K_NEIGHBORS, moods)
        knn = float(np.median([first_day_return(x) for x in nb])) if nb else base
        model = clip_return(fit_ridge(past, moods).predict(target, moods[target.no]))
        records.append({"no": target.no, "actual": first_day_return(target),
                        "knn": knn, "model": model, "baseline": base})
    return records


def evaluate(history: list[Ipo]) -> dict | None:
    recs = walk_forward(history)
    if not recs:
        return None
    out = {}
    for method in ("knn", "model", "baseline"):
        err = [abs(r[method] - r["actual"]) for r in recs]
        hit = [(r[method] < 0) == (r["actual"] < 0) for r in recs]
        out[method] = {"mae": float(np.mean(err)), "direction_acc": float(np.mean(hit)), "n": len(recs)}
    return out


def _beats_baseline(ev: dict | None, method: str) -> bool:
    return bool(ev and method in ev and "baseline" in ev and ev[method]["mae"] < ev["baseline"]["mae"])


def predict_for(ipo: Ipo, history: list[Ipo], eval_result: dict | None) -> dict | None:
    if ipo.is_spac or ipo.final_price is None or ipo.inst_competition is None:
        return None
    pool = _usable(history)
    moods = _moods(pool)
    moods[ipo.no] = _target_mood(ipo, pool, None)

    knn = None
    if _beats_baseline(eval_result, "knn"):
        nb = neighbors(ipo, pool, config.K_NEIGHBORS, moods)
        knn = knn_summary(nb, ipo.final_price) if nb else None

    model = None
    if _beats_baseline(eval_result, "model") and len(pool) >= config.MIN_TRAIN:
        r = clip_return(fit_ridge(pool, moods).predict(ipo, moods[ipo.no]))
        model = {"return": r, "price": int(round(ipo.final_price * (1 + r))),
                 "mae": eval_result["model"]["mae"]}
    return {"knn": knn, "model": model, "accuracy": eval_result}


def report(history: list[Ipo]) -> str:
    ev = evaluate(history)
    if ev is None:
        return "검증할 과거 종목이 부족합니다.\n"
    names = {"knn": "비슷한 종목 비교(가운데 값)", "model": "예측 모델", "baseline": "기준(과거 가운데 값)"}
    lines = [f"## 첫날 가격 예측 검증 (시간 순서 검증, 종목 {ev['baseline']['n']}개)", "",
             "| 방식 | 평균 오차(%p) | 공모가 위/아래 적중률 | 화면 표시 |", "|---|---|---|---|"]
    for m in ("knn", "model", "baseline"):
        show = "-" if m == "baseline" else ("표시" if _beats_baseline(ev, m) else "숨김")
        lines.append(f"| {names[m]} | {ev[m]['mae'] * 100:.1f} | {ev[m]['direction_acc'] * 100:.0f}% | {show} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    from ipo.history import load_history

    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    print(report(load_history(ap.parse_args().report)))
