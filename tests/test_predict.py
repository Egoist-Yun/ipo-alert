import math
from dataclasses import replace
from datetime import date, timedelta

import pytest

from ipo.models import Ipo
from ipo.predict import (clip_return, evaluate, features, fit_ridge, knn_summary, neighbors,
                         predict_for, walk_forward)


def mk(no, comp=100.0, lock=1.0, ret=0.0, day=None, market="코스닥", bio=False):
    return Ipo(no=no, name=f"s{no}", url="", market=market, is_bio=bio, band_low=90, band_high=110,
               final_price=100, inst_competition=comp, lockup_pct=lock, below_band_pct=10.0,
               float_pct=20.0, offer_amount_mil=10000,
               listing_date=None if day is None else (date(2025, 1, 1) + timedelta(days=day)).isoformat(),
               first_close=None if ret is None else round(100 * (1 + ret)))


def hist60(shift_after=None):
    items = []
    for i in range(60):
        ret = ((i * 37) % 100) / 100 - 0.4
        if shift_after is not None and i > shift_after:
            ret = 2.5
        items.append(mk(i, comp=50 + (i * 53) % 900, lock=(i * 7) % 20, ret=ret, day=i))
    return items


def test_clip_return():
    assert clip_return(5.0) == 3.00 and clip_return(-0.9) == -0.40 and clip_return(0.1) == 0.1


def test_features_order_and_missing():
    f = features(mk(1), mood=0.3)
    assert len(f) == 9
    assert f[0] == pytest.approx(math.log(100)) and f[1] == 1.0 and f[2] == 0.5 and f[5] == 0.3
    assert f[7] == 0.0 and f[8] == 0.0
    assert features(replace(mk(1), lockup_pct=None), None)[1] is None
    assert features(replace(mk(1), band_high=90), None)[2] is None


def test_neighbors_prefers_similar():
    hist = [mk(i, comp=60 + i, lock=0.1, ret=-0.3) for i in range(5)] + \
           [mk(100 + i, comp=1200 + i, lock=10, ret=0.8) for i in range(5)]
    nb = neighbors(mk(999, comp=65, lock=0.1, ret=None), hist, k=5)
    assert {n.no for n in nb} == set(range(5))


def test_neighbors_ignore_missing_dims():
    target = mk(999, comp=65, lock=None, ret=None)
    assert len(neighbors(target, [mk(i, comp=60, lock=0.1, ret=-0.2) for i in range(3)], k=3)) == 3


def test_neighbors_skip_candidates_with_too_few_dims():
    sparse = Ipo(no=999, name="x", url="", inst_competition=65)
    assert neighbors(sparse, [mk(i) for i in range(5)], k=3) == []


def test_knn_summary_counts_down_and_prices():
    s = knn_summary([mk(i, ret=r) for i, r in enumerate([-0.3, -0.1, 0.2])], final_price=10000)
    assert s["down_count"] == 2 and s["n"] == 3
    assert s["median"] == pytest.approx(-0.1)
    assert (s["price_low"], s["price_high"]) == (8000, 10500)
    assert [x["no"] for x in s["items"]] == [0, 1, 2]


def test_ridge_learns_linear_relation():
    hist = [mk(i, comp=10 + 25 * i, ret=-0.2 + 0.05 * math.log(10 + 25 * i)) for i in range(40)]
    model = fit_ridge(hist)
    truth = -0.2 + 0.05 * math.log(300)
    assert abs(model.predict(mk(99, comp=300, ret=None), None) - truth) < 0.05


def test_walk_forward_uses_only_past():
    first = walk_forward(hist60())[0]
    changed = walk_forward(hist60(shift_after=42))[0]
    assert first == changed


def test_evaluate_aggregates_all_methods():
    ev = evaluate(hist60())
    n = len(walk_forward(hist60()))
    for key in ("knn", "model", "baseline"):
        assert ev[key]["n"] == n and ev[key]["mae"] >= 0 and 0 <= ev[key]["direction_acc"] <= 1


def test_evaluate_none_when_too_little_history():
    assert evaluate([mk(i, ret=0.1, day=i) for i in range(5)]) is None


def test_method_hidden_when_not_better_than_baseline():
    target = mk(500, comp=120, ret=None)
    ev = {"knn": {"mae": 0.30}, "model": {"mae": 0.20}, "baseline": {"mae": 0.25}}
    p = predict_for(target, hist60(), ev)
    assert p["knn"] is None and p["model"] is not None
    assert -0.40 <= p["model"]["return"] <= 3.00 and p["model"]["mae"] == 0.20


def test_predict_for_none_for_spac_or_missing_inputs():
    ev = {"knn": {"mae": 0.1}, "model": {"mae": 0.1}, "baseline": {"mae": 0.2}}
    assert predict_for(replace(mk(1), is_spac=True), hist60(), ev) is None
    assert predict_for(replace(mk(1), final_price=None), hist60(), ev) is None
    assert predict_for(replace(mk(1), inst_competition=None), hist60(), ev) is None
