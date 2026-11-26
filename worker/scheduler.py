"""Agendador de cota: decide quais monitoramentos podem gastar uma busca ao vivo nesta execução.

Prioridade = proximidade da viagem + distância do orçamento + volatilidade recente.
Orçamento diário = (cota restante - reserva) / dias restantes no mês."""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any


@dataclass
class Candidate:
    watch: dict[str, Any]
    hours_since_last: float          # horas desde a última busca ao vivo deste monitoramento
    best_price: float | None = None
    volatility: float = 0.0          # desvio relativo recente (0..1)


def days_left_in_month(today: date | None = None) -> int:
    today = today or datetime.now(timezone.utc).date()
    return calendar.monthrange(today.year, today.month)[1] - today.day + 1


def daily_budget(remaining: float, reserve: float, today: date | None = None) -> float:
    return max(0.0, (remaining - reserve) / days_left_in_month(today))


def priority(c: Candidate, today: date | None = None) -> float:
    today = today or datetime.now(timezone.utc).date()
    w = c.watch
    first = w.get("depart_date") or w.get("depart_from")
    days_to_trip = (date.fromisoformat(first) - today).days if first else 90
    p = 0.0
    p += max(0.0, 1 - days_to_trip / 180) * 40        # viagem próxima pesa mais
    budget = w.get("budget_total")
    if budget and c.best_price:
        gap = (c.best_price - budget) / budget          # quão perto do orçamento
        p += max(0.0, 30 - abs(gap) * 100)
    p += min(1.0, c.volatility * 5) * 30               # preço mexendo = vale olhar
    return p


def pick(cands: list[Candidate], per_day: float, runs_per_day: int = 24,
         today: date | None = None) -> list[Candidate]:
    """Escolhe quantas buscas cabem nesta execução e quais monitoramentos as recebem.
    Cada monitoramento precisa esperar um intervalo mínimo proporcional à cota."""
    if per_day <= 0 or not cands:
        return []
    min_interval_h = 24 * len(cands) / per_day        # ex.: 3 monitoramentos, 8/dia -> 9h
    eligible = [c for c in cands if c.hours_since_last >= min_interval_h]
    slots = max(1, round(per_day / runs_per_day)) if per_day >= runs_per_day else 1
    eligible.sort(key=lambda c: (priority(c, today), c.hours_since_last), reverse=True)
    return eligible[:slots]
