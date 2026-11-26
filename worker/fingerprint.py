"""Fingerprint de itinerário e filtros de qualidade (conexão, duração, troca de aeroporto)."""
from __future__ import annotations

import hashlib
from typing import Any

from worker.models import Itinerary


def fingerprint(it: Itinerary) -> str:
    parts = [f"{s.airline}{s.flight_number}@{s.dep_time[:10]}:{s.dep_airport}-{s.arr_airport}"
             for s in it.segments]
    cabin = it.segments[0].cabin if it.segments else "?"
    key = "|".join(parts) + f"|ret={it.return_date or '-'}|cab={cabin}|bag={it.bag_included}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def airport_change(it: Itinerary) -> bool:
    return any(a.arr_airport != b.dep_airport for a, b in zip(it.segments, it.segments[1:]))


def rejection_reason(it: Itinerary, w: dict[str, Any]) -> str | None:
    """Retorna o motivo da rejeição, ou None se o itinerário é aceitável para o monitoramento."""
    if airport_change(it) and not w.get("allow_airport_change"):
        return "troca de aeroporto na conexão"
    if it.self_transfer and not w.get("allow_self_transfer"):
        return "self-transfer"
    max_stops = w.get("max_stops")
    if max_stops is not None and it.stops > max_stops:
        return f"{it.stops} escalas"
    min_lay = w.get("min_layover_minutes") or 60
    max_lay = (w.get("max_layover_hours") or 8) * 60
    for lay in it.layovers:
        if lay.duration_min < min_lay:
            return f"conexão curta ({lay.duration_min} min)"
        if lay.duration_min > max_lay:
            return f"conexão longa ({lay.duration_min // 60}h)"
    max_dur = w.get("max_duration_hours")
    if max_dur and it.total_duration_min > max_dur * 60:
        return f"duração {it.total_duration_min // 60}h"
    airlines = w.get("airlines")
    if airlines and not set(it.airlines) & set(airlines):
        return "companhia fora da lista"
    return None
