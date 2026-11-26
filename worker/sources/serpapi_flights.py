"""SerpApi Google Flights (ao vivo). Cada chamada consome 1 busca da cota:
- busca inicial (ida ou ida+volta; em ida+volta o preço já é o TOTAL da viagem)  -> 1
- departure_token (opções de volta)                                                -> +1
- booking_token (links de compra)                                                  -> +1
Por isso detalhes só são buscados quando um alerta vai ser enviado."""
from __future__ import annotations

import logging
from typing import Any

import requests

from worker.http import session
from worker.models import Itinerary, Layover, Segment

log = logging.getLogger(__name__)
URL = "https://serpapi.com/search.json"
CABIN = {"economy": 1, "premium_economy": 2, "business": 3, "first": 4}


class SerpApiFlights:
    name = "serpapi"

    def __init__(self, api_key: str, http: requests.Session | None = None):
        self.key = api_key
        self.http = http or session()
        self.credits_used = 0

    def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        base = {"engine": "google_flights", "gl": "br", "hl": "pt-br", "currency": "BRL",
                "api_key": self.key}
        r = self.http.get(URL, params={**base, **params}, timeout=60)
        self.credits_used += 1
        if r.status_code == 401:
            raise RuntimeError("SerpApi: chave inválida")
        if r.status_code == 429:
            raise RuntimeError("SerpApi: cota esgotada")
        r.raise_for_status()
        data = r.json()
        if data.get("error") and "hasn't returned any results" not in data["error"]:
            raise RuntimeError(f"SerpApi: {data['error']}")
        return data

    def search(self, origins: list[str], destinations: list[str], depart: str, ret: str | None,
               adults: int, cabin: str, max_stops: int | None) -> tuple[list[Itinerary], dict[str, Any]]:
        params: dict[str, Any] = {
            "departure_id": ",".join(origins),
            "arrival_id": ",".join(destinations),
            "outbound_date": depart,
            "type": 1 if ret else 2,
            "adults": adults,
            "travel_class": CABIN.get(cabin, 1),
        }
        if ret:
            params["return_date"] = ret
        if max_stops is not None:
            params["stops"] = {0: 1, 1: 2, 2: 3}.get(max_stops, 0)   # 1=direto, 2=até 1, 3=até 2
        data = self._get(params)
        return parse_results(data, depart, ret, adults), data.get("price_insights") or {}

    def booking_options(self, booking_token: str) -> list[dict[str, Any]]:
        data = self._get({"booking_token": booking_token})
        return data.get("booking_options") or []


def _self_transfer(option: dict[str, Any]) -> bool:
    text = " ".join(
        [*(option.get("extensions") or []),
         *(x for f in option.get("flights", []) for x in (f.get("extensions") or []))]
    ).lower()
    return "self transfer" in text or "autotransfer" in text or "transferência própria" in text


def _bag_included(option: dict[str, Any]) -> bool | None:
    text = " ".join(x for f in option.get("flights", []) for x in (f.get("extensions") or [])).lower()
    if "checked bag" in text and ("included" in text or "incluída" in text):
        return True
    if "bagagem despachada" in text and "inclu" in text:
        return True
    return None


def parse_results(data: dict[str, Any], depart: str, ret: str | None, adults: int) -> list[Itinerary]:
    insights = data.get("price_insights") or {}
    rng = insights.get("typical_price_range")
    out: list[Itinerary] = []
    for opt in (data.get("best_flights") or []) + (data.get("other_flights") or []):
        if not opt.get("price"):
            continue
        segs = [Segment(
            airline=f.get("airline", "?"),
            flight_number=str(f.get("flight_number", "")).replace(" ", ""),
            dep_airport=f["departure_airport"]["id"],
            arr_airport=f["arrival_airport"]["id"],
            dep_time=f["departure_airport"].get("time", depart),
            arr_time=f["arrival_airport"].get("time", ""),
            duration_min=int(f.get("duration") or 0),
            cabin=(f.get("travel_class") or "economy").lower().replace(" ", "_"),
        ) for f in opt.get("flights", [])]
        lays = [Layover(airport=l.get("id", "?"), duration_min=int(l.get("duration") or 0),
                        overnight=bool(l.get("overnight"))) for l in opt.get("layovers") or []]
        out.append(Itinerary(
            source="serpapi", live=True, depart_date=depart, return_date=ret,
            segments=segs, layovers=lays, total_duration_min=int(opt.get("total_duration") or 0),
            price_raw=float(opt["price"]), adults=adults, bag_included=_bag_included(opt),
            self_transfer=_self_transfer(opt), price_level=insights.get("price_level"),
            typical_range=(float(rng[0]), float(rng[1])) if rng and len(rng) == 2 else None,
            departure_token=opt.get("departure_token"), booking_token=opt.get("booking_token"),
            booking_url=data.get("search_metadata", {}).get("google_flights_url"),
        ))
    return out
