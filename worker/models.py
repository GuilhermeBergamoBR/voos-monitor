from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Segment:
    airline: str
    flight_number: str
    dep_airport: str
    arr_airport: str
    dep_time: str            # "2027-03-10 22:35" (horário local do aeroporto)
    arr_time: str
    duration_min: int
    cabin: str = "economy"


@dataclass
class Layover:
    airport: str
    duration_min: int
    overnight: bool = False


@dataclass
class Itinerary:
    """Uma opção de viagem (ida, ou ida+volta) com preço do GRUPO."""

    source: str
    live: bool                         # False = dado de cache (não pode gerar alerta sozinho)
    depart_date: str
    return_date: str | None
    segments: list[Segment]
    layovers: list[Layover]
    total_duration_min: int
    price_raw: float                   # preço como a fonte deu (grupo)
    currency: str = "BRL"
    adults: int = 2
    bag_included: bool | None = None   # None = desconhecido
    self_transfer: bool = False
    price_level: str | None = None     # low | typical | high
    typical_range: tuple[float, float] | None = None
    departure_token: str | None = None
    booking_token: str | None = None
    booking_url: str | None = None
    price_total: float = 0.0           # preço comparável (preenchido por pricing)
    fingerprint: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def airlines(self) -> list[str]:
        return sorted({s.airline for s in self.segments})

    @property
    def stops(self) -> int:
        return max(0, len(self.segments) - 1)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["airlines"] = self.airlines
        d["stops"] = self.stops
        return d
