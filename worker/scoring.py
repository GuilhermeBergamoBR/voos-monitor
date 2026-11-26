"""Regras de alerta determinísticas + score 0-100. O LLM nunca decide se alerta."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from worker.models import Itinerary

SENSITIVITY_PCT = {"conservative": 20.0, "balanced": 12.0, "aggressive": 7.0}
MIN_VAR_PCT = 5.0
MIN_VAR_BRL = 150.0
ERROR_FARE_PCT = 40.0
REALERT_PCT = 5.0


@dataclass
class WatchHistory:
    min_price: float | None = None          # menor preço AO VIVO já visto
    median14: float | None = None
    median30: float | None = None
    ever_below_budget: bool = False
    last_alert_price: dict[str, float] = field(default_factory=dict)   # fingerprint -> preço


@dataclass
class Decision:
    alert: bool
    score: int
    rule: str | None
    reasons: list[str]
    urgent: bool = False


def _pct_below(price: float, ref: float | None) -> float | None:
    return (ref - price) / ref * 100 if ref else None


def _significant(price: float, ref: float | None) -> bool:
    return bool(ref) and (ref - price) >= MIN_VAR_BRL and (ref - price) / ref * 100 >= MIN_VAR_PCT


def evaluate(it: Itinerary, w: dict[str, Any], h: WatchHistory) -> Decision:
    price = it.price_total
    if not it.live:
        return Decision(False, 0, None, ["preço só de cache"])

    reasons: list[tuple[str, str]] = []
    lo = it.typical_range[0] if it.typical_range else None

    # 4. erro tarifário: >= 40% abaixo do piso da faixa típica
    below_floor = _pct_below(price, lo)
    urgent = below_floor is not None and below_floor >= ERROR_FARE_PCT
    if urgent:
        reasons.append(("error_fare", f"provável erro tarifário: {below_floor:.0f}% abaixo do piso da faixa típica"))

    # 1. price_level low e abaixo do menor já visto
    if it.price_level == "low" and h.min_price and price < h.min_price and _significant(price, h.min_price):
        reasons.append(("low_and_record", f"Google diz 'baixo' e é o menor já visto (antes {h.min_price:,.0f})"))

    # 2. X% abaixo da mediana 14/30 dias
    x = SENSITIVITY_PCT.get(w.get("sensitivity", "balanced"), 12.0)
    for label, med in (("14", h.median14), ("30", h.median30)):
        d = _pct_below(price, med)
        if d is not None and d >= x and _significant(price, med):
            reasons.append(("below_median", f"{d:.0f}% abaixo da mediana de {label} dias"))
            break

    # 3. primeira vez abaixo do orçamento
    budget = w.get("budget_total")
    if budget and price <= budget and not h.ever_below_budget:
        reasons.append(("first_below_budget", f"primeira vez abaixo do orçamento (R$ {budget:,.0f})"))

    if not reasons:
        return Decision(False, 0, None, [])

    # não repetir o mesmo fingerprint sem nova queda >= 5%
    prev = h.last_alert_price.get(it.fingerprint)
    if prev is not None and price > prev * (1 - REALERT_PCT / 100):
        return Decision(False, 0, None, ["já alertado"])

    # ---- score ----
    ref = h.median30 or h.median14 or (sum(it.typical_range) / 2 if it.typical_range else None)
    drop = max(0.0, _pct_below(price, ref) or 0.0)
    score = min(50.0, drop * 2.5)                                   # desconto real
    score += {"low": 15, "typical": 5}.get(it.price_level or "", 0) # sinal do Google
    if budget:
        score += 15 if price <= budget else max(0.0, 15 - (price - budget) / budget * 100)
    score += 10 if it.stops == 0 else (5 if it.stops == 1 else 0)  # conforto
    score += 10 if urgent else 0
    score_i = int(round(min(100.0, score)))
    threshold = int(w.get("score_threshold") or 70)
    if score_i < threshold and not urgent:
        return Decision(False, score_i, reasons[0][0], [r for _, r in reasons])
    return Decision(True, score_i, reasons[0][0], [r for _, r in reasons], urgent=urgent)
