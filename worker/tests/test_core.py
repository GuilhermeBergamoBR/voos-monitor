import json
from datetime import date
from pathlib import Path

import pytest

from worker.fingerprint import airport_change, fingerprint, rejection_reason
from worker.main import CFG, prepare
from worker.pricing import comparable_price
from worker.scheduler import Candidate, daily_budget, pick, priority
from worker.scoring import WatchHistory, evaluate
from worker.sources.serpapi_flights import parse_results

FIX = Path(__file__).parent / "fixtures"
WATCH = {"id": "w1", "name": "SP → Lisboa", "sensitivity": "balanced", "score_threshold": 70,
         "budget_total": 7000, "max_stops": 1, "need_checked_bag": False, "min_layover_minutes": 60,
         "max_layover_hours": 8}


@pytest.fixture
def its():
    data = json.loads((FIX / "serpapi_gru_lis_SINTETICO.json").read_text(encoding="utf-8"))
    return parse_results(data, "2027-03-10", "2027-03-20", 2)


# ---------- parse + filtros ----------
def test_parse_serpapi(its):
    assert len(its) == 3
    assert its[0].price_level == "low" and its[0].typical_range == (7400.0, 9800.0)
    assert its[0].segments[0].flight_number == "TP82"
    assert its[2].self_transfer is True


def test_filters_reject_short_layover_and_airport_change(its):
    assert rejection_reason(its[0], WATCH) is None
    assert "conexão curta" in rejection_reason(its[1], WATCH)        # 50 min em MAD
    assert airport_change(its[2])                                     # chega LHR, sai LGW
    assert rejection_reason(its[2], WATCH) == "troca de aeroporto na conexão"
    assert rejection_reason(its[2], {**WATCH, "allow_airport_change": True}) == "self-transfer"


def test_prepare_keeps_only_acceptable_sorted(its):
    ok = prepare(its, WATCH)
    assert [i.segments[0].airline for i in ok] == ["TAP"]


def test_fingerprint_stable_and_distinct(its):
    assert fingerprint(its[0]) == fingerprint(its[0])
    assert fingerprint(its[0]) != fingerprint(its[1])


# ---------- preço real ----------
def test_comparable_price_adds_bag_for_group_both_ways(its):
    it = its[0]
    assert comparable_price(it, need_bag=False, cfg=CFG) == 6420
    # internacional: R$ 400 x 2 trechos x 2 pessoas
    assert comparable_price(it, need_bag=True, cfg=CFG) == 6420 + 1600


def test_comparable_price_adds_iof_for_foreign_currency(its):
    it = its[0]
    it.currency, it.price_raw = "USD", 1000.0
    assert comparable_price(it, need_bag=False, cfg=CFG) == 1035.0


# ---------- scoring ----------
def _best(its, price):
    it = prepare(its, WATCH)[0]
    it.price_total = price
    return it


def test_error_fare_is_urgent(its):
    d = evaluate(_best(its, 4200), WATCH, WatchHistory(min_price=6800))
    assert d.alert and d.urgent and d.rule == "error_fare"


def test_low_level_and_record_alerts(its):
    d = evaluate(_best(its, 6000), WATCH, WatchHistory(min_price=6500, median30=8000))
    assert d.alert and d.score >= 70


def test_small_variation_ignored(its):
    it = _best(its, 6420)
    it.price_level = "typical"
    d = evaluate(it, {**WATCH, "budget_total": None}, WatchHistory(min_price=6500, median30=6600))
    assert not d.alert                            # -R$ 80, abaixo de R$ 150


def test_cache_only_never_alerts(its):
    it = _best(its, 3000)
    it.live = False
    assert not evaluate(it, WATCH, WatchHistory(min_price=6800)).alert


def test_same_fingerprint_needs_5pct_more(its):
    it = _best(its, 6000)
    h = WatchHistory(min_price=6500, median30=8000, last_alert_price={it.fingerprint: 6200})
    assert not evaluate(it, WATCH, h).alert
    it.price_total = 5800
    h.min_price = 6000
    assert evaluate(it, WATCH, h).alert


def test_first_below_budget_only_once(its):
    it = _best(its, 6900)
    it.price_level = "typical"
    w = {**WATCH, "score_threshold": 40}
    assert evaluate(it, w, WatchHistory(min_price=7200)).rule == "first_below_budget"
    assert not evaluate(it, w, WatchHistory(min_price=7200, ever_below_budget=True)).alert


# ---------- agendador ----------
def test_daily_budget_spreads_remaining_quota():
    assert daily_budget(250, 20, date(2026, 12, 1)) == pytest.approx(230 / 31)


def test_pick_respects_min_interval_and_priority():
    near = Candidate({"depart_date": "2027-01-10", "budget_total": 5000}, hours_since_last=30, best_price=5200)
    far = Candidate({"depart_date": "2027-09-10"}, hours_since_last=30)
    fresh = Candidate({"depart_date": "2027-01-05"}, hours_since_last=1)
    today = date(2026, 12, 1)
    assert priority(near, today) > priority(far, today)
    chosen = pick([far, near, fresh], per_day=7.4, today=today)
    assert chosen == [near]                       # 1 por execução; o recém-buscado espera
