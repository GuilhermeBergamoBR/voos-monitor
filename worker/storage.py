"""Acesso ao Supabase via PostgREST com a service_role (só no worker; nunca no browser)."""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from worker.http import session
from worker.models import Itinerary
from worker.scoring import WatchHistory


def month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


class Store:
    def __init__(self, url: str, service_key: str, http: requests.Session | None = None):
        self.base = url.rstrip("/") + "/rest/v1"
        self.http = http or session()
        self.http.headers.update({
            "apikey": service_key, "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
        })

    # ---------- genérico ----------
    def _get(self, table: str, **params: str) -> list[dict[str, Any]]:
        r = self.http.get(f"{self.base}/{table}", params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def _post(self, table: str, rows: Any, upsert: bool = False, returning: bool = False) -> Any:
        prefer = ["return=representation" if returning else "return=minimal"]
        if upsert:
            prefer.append("resolution=merge-duplicates")
        r = self.http.post(f"{self.base}/{table}", json=rows, headers={"Prefer": ",".join(prefer)}, timeout=30)
        r.raise_for_status()
        return r.json() if returning else None

    def _patch(self, table: str, match: dict[str, str], values: dict[str, Any]) -> None:
        r = self.http.patch(f"{self.base}/{table}", params=match, json=values, timeout=30)
        r.raise_for_status()

    # ---------- monitoramentos ----------
    def active_watches(self, watch_id: str | None = None) -> list[dict[str, Any]]:
        params = {"status": "eq.active", "select": "*"}
        if watch_id:
            params = {"id": f"eq.{watch_id}", "select": "*"}
        return self._get("watches", **params)

    def set_watch(self, watch_id: str, **values: Any) -> None:
        self._patch("watches", {"id": f"eq.{watch_id}"}, values)

    # ---------- histórico ----------
    def history(self, watch_id: str) -> WatchHistory:
        since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        obs = self._get("price_observations", watch_id=f"eq.{watch_id}", live="is.true",
                        select="price_total,observed_at", order="observed_at.desc", limit="5000")
        prices30 = [o["price_total"] for o in obs if o["observed_at"] >= since]
        since14 = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
        prices14 = [o["price_total"] for o in obs if o["observed_at"] >= since14]
        alerts = self._get("alerts", watch_id=f"eq.{watch_id}", select="fingerprint,price_total,rule",
                           order="sent_at.asc")
        last: dict[str, float] = {}
        for a in alerts:
            if a.get("fingerprint"):
                last[a["fingerprint"]] = a["price_total"]
        return WatchHistory(
            min_price=min((o["price_total"] for o in obs), default=None),
            median14=statistics.median(prices14) if len(prices14) >= 3 else None,
            median30=statistics.median(prices30) if len(prices30) >= 3 else None,
            ever_below_budget=any(a["rule"] == "first_below_budget" for a in alerts),
            last_alert_price=last,
        )

    def record(self, watch_id: str, its: list[Itinerary]) -> None:
        if not its:
            return
        now = datetime.now(timezone.utc).isoformat()
        self._post("itineraries", [{"fingerprint": i.fingerprint, "summary": i.to_dict(), "last_seen": now}
                                   for i in {i.fingerprint: i for i in its}.values()], upsert=True)
        self._post("price_observations", [{
            "watch_id": watch_id, "fingerprint": i.fingerprint, "source": i.source, "live": i.live,
            "depart_date": i.depart_date, "return_date": i.return_date, "price_total": i.price_total,
            "price_raw": i.price_raw, "currency": i.currency, "price_level": i.price_level,
            "typical_low": i.typical_range[0] if i.typical_range else None,
            "typical_high": i.typical_range[1] if i.typical_range else None,
            "booking_url": i.booking_url,
        } for i in its])

    def log_search(self, watch_id: str | None, source: str, params: dict[str, Any], credits: int,
                   ok: bool, error: str | None = None) -> None:
        import hashlib, json
        qh = hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()
        self._post("searches", {"watch_id": watch_id, "source": source, "query_hash": qh, "params": params,
                                "credits_used": credits, "ok": ok, "error": (error or "")[:500] or None})

    def save_alert(self, row: dict[str, Any]) -> str:
        return self._post("alerts", row, returning=True)[0]["id"]

    # ---------- cota ----------
    def quota(self, api: str, budget: float) -> tuple[float, float]:
        rows = self._get("quota_usage", api=f"eq.{api}", month=f"eq.{month()}")
        if not rows:
            self._post("quota_usage", {"api": api, "month": month(), "used": 0, "budget": budget}, upsert=True)
            return 0.0, budget
        return float(rows[0]["used"]), float(budget)

    def add_usage(self, api: str, amount: float, budget: float) -> None:
        used, _ = self.quota(api, budget)
        self._post("quota_usage", {"api": api, "month": month(), "used": used + amount, "budget": budget},
                   upsert=True)

    # ---------- saúde / execuções ----------
    def health(self, source: str, ok: bool, error: str | None, threshold: int) -> str | None:
        rows = self._get("source_health", source=f"eq.{source}")
        fails, warned = (rows[0]["consecutive_failures"], rows[0]["warned"]) if rows else (0, False)
        event = None
        now = datetime.now(timezone.utc).isoformat()
        row: dict[str, Any] = {"source": source, "updated_at": now}
        if ok:
            event = "up" if warned else None
            row.update(consecutive_failures=0, warned=False, last_ok=now)
        else:
            fails += 1
            if fails >= threshold and not warned:
                event, warned = "down", True
            row.update(consecutive_failures=fails, warned=warned, last_error=(error or "")[:500])
        self._post("source_health", row, upsert=True)
        return event

    def run(self, summary: dict[str, Any], ok: bool, started: str) -> None:
        self._post("runs", {"started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
                            "ok": ok, "summary": summary})
