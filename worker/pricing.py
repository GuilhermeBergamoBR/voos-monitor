"""Preço comparável = tarifa + taxas + bagagem despachada (se exigida) + IOF (venda em moeda estrangeira)."""
from __future__ import annotations

from typing import Any

from worker.models import Itinerary

# Bagagem despachada estimada por trecho e por pessoa (R$). Ajustável em config.yaml.
DEFAULT_BAG_FEES = {
    "domestic": 150.0,      # LATAM/GOL/Azul no Brasil, 1 mala de 23 kg (média)
    "international": 400.0, # América do Sul / EUA / Europa, tarifas básicas
}
BR_AIRPORTS_PREFIXES = ("GRU", "CGH", "VCP", "GIG", "SDU", "BSB", "CNF", "SSA", "REC", "FOR",
                        "POA", "CWB", "FLN", "BEL", "MAO", "NAT", "MCZ", "JPA", "AJU", "VIX",
                        "GYN", "CGB", "CGR", "THE", "SLZ", "PMW", "IGU", "NVT", "BPS", "FEN")


def is_domestic(it: Itinerary) -> bool:
    return all(s.dep_airport in BR_AIRPORTS_PREFIXES and s.arr_airport in BR_AIRPORTS_PREFIXES
               for s in it.segments)


def comparable_price(it: Itinerary, need_bag: bool, cfg: dict[str, Any]) -> float:
    pc = cfg.get("pricing", {})
    total = it.price_raw
    if need_bag and it.bag_included is not True:
        fees = {**DEFAULT_BAG_FEES, **pc.get("bag_fees", {})}
        per = fees["domestic"] if is_domestic(it) else fees["international"]
        legs = 2 if it.return_date else 1
        total += per * legs * it.adults
    if it.currency.upper() != "BRL":
        total *= 1 + pc.get("iof_pct", 3.5) / 100
    return round(total, 2)
