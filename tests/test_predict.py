import math
import statistics
from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pytest

from ipo.models import Ipo, first_day_return
from ipo.predict import (Ctx, FEATURE_NAMES, clip_return, evaluate, features, fit_logistic, fit_ridge,
                         knn_summary, neighbors, predict_for, select_features, walk_forward)


def day(n):
    return (date(2025, 1, 1) + timedelta(days=n)).isoformat()


def mk(no, comp=100.0, lock=1.0, ret=0.0, d=None, market="코스닥", bio=False, **kw):
    base = dict(no=no, name=f"s{no}", url="", market=market, is_bio=bio, band_low=90, band_high=110,
                final_price=100, inst_competition=comp, lockup_pct=lock, below_band_pct=10.0,
                float_pct=20.0, offer_amount_mil=10000, revenue_mil=5000, net_income_mil=100,
                capital_mil=2000, par_value=100, old_share_pct=0.0, inst_count=300,
                listing_date=None if d is None else day(d),
                first_close=None if ret is None else round(100 * (1 + ret)),
                open_price=None if ret is None else round(100 * (1 + ret / 2)))
    base.update(kw)
    return Ipo(**base)


def hist60(shift_after=None):
    items = []
    for i in range(60):
        ret = ((i * 37) % 100) / 100 - 0.4
        if shift_after is not None and i > shift_after:
            ret = 2.5
        items.append(mk(i, comp=50 + (i * 53) % 900, lock=(i * 7) % 20, ret=ret, d=i))
    return items


def synthetic(n=140, seed=0):
    """Fall (first-day close below offer price) is driven by low competition; other columns are noise."""
    rng = np.random.default_rng(seed)
    items = []
    for i in range(n):
        comp = float(np.exp(rng.uniform(math.log(20), math.log(1500))))
        down = comp < 200
        ret = (-0.3 if down else 0.4) + float(rng.normal(0, 0.05))
        items.append(mk(i, comp=comp, lock=float(rng.uniform(0, 20)), ret=ret, d=i,
                        below_band_pct=float(rng.uniform(0, 50)), float_pct=float(rng.uniform(10, 50)),
                        revenue_mil=int(rng.integers(1000, 90000)), inst_count=int(rng.integers(100, 900))))
    return items


def test_clip_return():
    assert clip_return(5.0) == 3.00 and clip_return(-0.9) == -0.40 and clip_return(0.1) == 0.1


def test_features_follow_requested_names_in_order():
    f = features(mk(1), Ctx(mood=0.3, heat=0.1), ["comp", "mood", "heat", "old_share", "inst_count"])
    assert f[0] == pytest.approx(math.log(100)) and f[1] == 0.3 and f[2] == 0.1 and f[3] == 0.0
    assert f[4] == pytest.approx(math.log(300))


def test_features_price_position_and_missing():
    assert features(mk(1), Ctx(None, None), ["price_pos"]) == [0.5]
    assert features(replace(mk(1), lockup_pct=None), Ctx(None, None), ["lockup"]) == [None]
    assert features(replace(mk(1), band_high=90), Ctx(None, None), ["price_pos"]) == [None]


def test_features_financial_derivations():
    nexi = mk(1, final_price=8000, capital_mil=22922, par_value=500, offer_amount_mil=40000,
              revenue_mil=5110, net_income_mil=-52331)
    mcap = 8000 * 22922 / 500  # 백만원
    f = dict(zip(FEATURE_NAMES, features(nexi, Ctx(None, None))))
    assert f["mcap"] == pytest.approx(math.log(mcap))
    assert f["offer_ratio"] == pytest.approx(40000 / mcap)
    assert f["psr"] == pytest.approx(math.log(mcap / 5110))
    assert f["loss"] == 1.0 and f["revenue"] == pytest.approx(math.log(5110))
    none = dict(zip(FEATURE_NAMES, features(mk(2, capital_mil=None, revenue_mil=None, net_income_mil=None),
                                            Ctx(None, None))))
    assert none["mcap"] is None and none["psr"] is None and none["loss"] is None and none["revenue"] is None


def test_neighbors_prefers_similar():
    hist = [mk(i, comp=60 + i, lock=0.1, ret=-0.3) for i in range(5)] + \
           [mk(100 + i, comp=1200 + i, lock=10, ret=0.8) for i in range(5)]
    nb = neighbors(mk(999, comp=65, lock=0.1, ret=None), hist, k=5, names=["comp", "lockup", "price_pos", "offer_amt"])
    assert {n.no for n in nb} == set(range(5))


def test_neighbors_skip_candidates_with_too_few_dims():
    sparse = Ipo(no=999, name="x", url="", inst_competition=65)
    assert neighbors(sparse, [mk(i) for i in range(5)], k=3, names=["comp", "lockup", "price_pos"]) == []


def test_knn_summary_counts_down_and_prices():
    s = knn_summary([mk(i, ret=r) for i, r in enumerate([-0.3, -0.1, 0.2])], final_price=10000)
    assert s["down_count"] == 2 and s["n"] == 3 and s["median"] == pytest.approx(-0.1)
    assert (s["price_low"], s["price_high"]) == (8000, 10500)
    assert [x["no"] for x in s["items"]] == [0, 1, 2]


def test_ridge_learns_linear_relation():
    hist = [mk(i, comp=10 + 25 * i, ret=-0.2 + 0.05 * math.log(10 + 25 * i)) for i in range(40)]
    model = fit_ridge(hist, names=["comp"])
    truth = -0.2 + 0.05 * math.log(300)
    assert abs(model.predict(mk(99, comp=300, ret=None), None) - truth) < 0.05


def test_logistic_probability_follows_the_signal_and_stays_in_bounds():
    hist = synthetic()
    model = fit_logistic(hist, names=["comp"])
    low = model.predict(mk(9001, comp=30, ret=None), None)
    high = model.predict(mk(9002, comp=1200, ret=None), None)
    assert low > 0.8 and high < 0.2
    assert 0.0 < min(low, high) and max(low, high) < 1.0


def test_select_features_finds_the_informative_one_and_ignores_sparse():
    hist = synthetic()
    sparse = [replace(h, float_pct=None) if i % 4 else h for i, h in enumerate(hist)]  # 25% coverage
    chosen = select_features(sparse)
    assert "comp" in chosen and "float" not in chosen and len(chosen) <= 8


def test_select_features_does_not_look_at_the_test_window():
    hist = synthetic()
    a = select_features(hist)
    flipped = hist[:-40] + [replace(h, first_close=round(h.first_close * 0.1 + 100)) for h in hist[-40:]]
    assert select_features(flipped) == a


def test_walk_forward_uses_only_past():
    first = walk_forward(hist60())[0]
    changed = walk_forward(hist60(shift_after=42))[0]
    assert first == changed


def test_walk_forward_excludes_same_day_listings():
    items = [mk(i, ret=((i * 37) % 100) / 100 - 0.4, d=i) for i in range(38)]
    items += [mk(38, ret=0.9, d=38), mk(39, ret=-0.35, d=38)]
    last = next(r for r in walk_forward(items) if r["no"] == 39)
    assert last["baseline"] == pytest.approx(statistics.median(first_day_return(i) for i in items[:38]))


def test_walk_forward_cuts_training_at_subscription_start():
    items = [mk(i, ret=((i * 37) % 100) / 100 - 0.4, d=i) for i in range(40)]
    items[39] = replace(items[39], sub_start=day(36))
    last = next(r for r in walk_forward(items) if r["no"] == 39)
    assert last["baseline"] == pytest.approx(statistics.median(first_day_return(i) for i in items[:36]))


def test_evaluate_reports_regression_and_probability_metrics():
    ev = evaluate(synthetic(), names=["comp"])
    n = len(walk_forward(synthetic(), names=["comp"]))
    for key in ("knn", "model", "baseline"):
        assert ev[key]["n"] == n and ev[key]["mae"] >= 0 and 0 <= ev[key]["direction_acc"] <= 1
    for key in ("prob", "prob_base"):
        assert ev[key]["logloss"] > 0 and 0 <= ev[key]["brier"] <= 1 and 0 <= ev[key]["accuracy"] <= 1
    assert ev["prob"]["logloss"] < ev["prob_base"]["logloss"]


def test_evaluate_none_when_too_little_history():
    assert evaluate([mk(i, ret=0.1, d=i) for i in range(5)], names=["comp"]) is None


def good_ev(**over):
    ev = {"knn": {"mae": 0.1}, "model": {"mae": 0.1}, "baseline": {"mae": 0.2},
          "ens": {"mae": 0.1, "direction_acc": 0.8}, "open_ens": {"mae": 0.1, "direction_acc": 0.9},
          "open_baseline": {"mae": 0.2},
          "prob": {"logloss": 0.4}, "prob_base": {"logloss": 0.6}}
    ev.update(over)
    return ev


def test_method_hidden_when_not_better_than_baseline():
    target = mk(500, comp=120, ret=None)
    ev = good_ev(knn={"mae": 0.30}, prob={"logloss": 0.7}, open_ens={"mae": 0.25, "direction_acc": 0.5})
    p = predict_for(target, hist60(), ev, names=["comp", "lockup"])
    assert p["knn"] is None and p["prob"] is None and p["open"] is None and p["close"] is not None
    assert -0.40 <= p["close"]["return"] <= 3.00 and p["close"]["mae"] == 0.1


def test_probability_shown_when_it_beats_base_rate():
    p = predict_for(mk(500, comp=30, ret=None), synthetic(), good_ev(), names=["comp"])
    assert 0.8 < p["prob"]["p_down"] < 1.0 and p["prob"]["n"] == 140


def test_predict_for_none_for_spac_or_missing_inputs():
    ev = good_ev()
    assert predict_for(replace(mk(1), is_spac=True), hist60(), ev, names=["comp"]) is None
    assert predict_for(replace(mk(1), final_price=None), hist60(), ev, names=["comp"]) is None
    assert predict_for(replace(mk(1), inst_competition=None), hist60(), ev, names=["comp"]) is None


def test_conflict_when_many_flags_but_prediction_points_up():
    hist = synthetic()
    up = predict_for(mk(500, comp=1200, ret=None, flag_count=5), hist, good_ev(), names=["comp"])
    assert up["conflict"] is True
    few = predict_for(mk(501, comp=1200, ret=None, flag_count=1), hist, good_ev(), names=["comp"])
    assert few["conflict"] is False
    consistent = predict_for(mk(502, comp=30, ret=None, flag_count=5), hist, good_ev(), names=["comp"])
    assert consistent["conflict"] is False


def test_ridge_on_log_returns_recovers_multiplicative_relation():
    hist = [mk(i, comp=10 + 25 * i, ret=math.expm1(-0.3 + 0.12 * math.log(10 + 25 * i))) for i in range(40)]
    model = fit_ridge(hist, names=["comp"], log=True)
    truth = math.expm1(-0.3 + 0.12 * math.log(300))
    assert abs(model.predict(mk(99, comp=300, ret=None), None) - truth) < 0.05


def test_open_and_close_predictions_are_ensembles_with_prices():
    p = predict_for(mk(500, comp=30, ret=None), synthetic(), good_ev(), names=["comp"])
    for key in ("open", "close"):
        r = p[key]["return"]
        assert -0.40 <= r <= 3.00 and p[key]["price"] == round(100 * (1 + r))
    assert p["close"]["return"] < 0 and p["open"]["return"] < 0
    assert p["open"]["mae"] == 0.1 and p["open"]["direction_acc"] == 0.9


def test_evaluate_reports_ensemble_and_open_metrics():
    ev = evaluate(synthetic(), names=["comp"])
    for key in ("ens", "open_ens", "open_baseline", "open_knn", "open_model"):
        assert ev[key]["n"] > 0 and ev[key]["mae"] >= 0
    assert ev["open_ens"]["mae"] < ev["open_baseline"]["mae"]


def test_open_metrics_skip_stocks_without_open_price():
    hist = [replace(h, open_price=None) if i % 2 else h for i, h in enumerate(synthetic())]
    ev = evaluate(hist, names=["comp"])
    assert ev["open_ens"]["n"] < ev["ens"]["n"]
