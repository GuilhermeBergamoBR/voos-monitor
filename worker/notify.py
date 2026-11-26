"""Telegram: alertas em HTML com botões (👍/👎/Pausar/Já comprei/Abrir no painel)."""
from __future__ import annotations

import html
import json
import logging
from typing import Any

import requests

from worker.http import session

log = logging.getLogger(__name__)


def brl(v: float | None) -> str:
    if v is None:
        return "—"
    return "R$ " + f"{v:,.0f}".replace(",", ".")


def fmt_duration(m: int) -> str:
    return f"{m // 60}h{m % 60:02d}"


def format_alert(a: dict[str, Any]) -> str:
    it, w = a["itinerary"], a["watch"]
    segs = it["segments"]
    route = f"{segs[0]['dep_airport']} → {segs[-1]['arr_airport']}" if segs else w["name"]
    dates = it["depart_date"] + (f" ↔ {it['return_date']}" if it.get("return_date") else " (só ida)")
    stops = "direto" if it["stops"] == 0 else f"{it['stops']} escala(s)"
    bag = {True: "bagagem incluída", None: "bagagem: verificar", False: "sem bagagem"}[it.get("bag_included")]
    pax = it.get("adults", 2)
    rng = it.get("typical_range")
    lines = [
        ("🚨 <b>PROVÁVEL ERRO TARIFÁRIO</b>\n" if a.get("urgent") else "") +
        f"✈️ <b>{html.escape(w['name'])}</b> — {html.escape(route)}",
        f"📅 {dates}",
        f"🛫 {html.escape(', '.join(it['airlines']))} · {stops} · {fmt_duration(it['total_duration_min'])} · {bag}",
        f"💰 <b>{brl(it['price_total'])}</b> total ({brl(it['price_total'] / pax)}/pessoa, {pax} pax)",
        f"📊 Menor já visto: {brl(a.get('min_price'))}"
        + (f" · faixa típica {brl(rng[0])}–{brl(rng[1])}" if rng else ""),
        f"📉 {a['pct_below']:.0f}% abaixo do normal · Score {a['score']}/100",
        f"✅ {html.escape(a['why'])}",
    ]
    if it.get("booking_url"):
        lines.append(f"🔗 <a href=\"{html.escape(it['booking_url'])}\">ver no Google Flights</a>")
    return "\n".join(lines)


def keyboard(alert_id: str, watch_id: str, panel_url: str | None) -> dict[str, Any]:
    rows = [[
        {"text": "👍", "callback_data": f"fb:{alert_id}:1"},
        {"text": "👎", "callback_data": f"fb:{alert_id}:-1"},
        {"text": "⏸ Pausar", "callback_data": f"pause:{watch_id}"},
        {"text": "✅ Já comprei", "callback_data": f"bought:{watch_id}"},
    ]]
    if panel_url:
        rows.append([{"text": "Abrir no painel", "url": f"{panel_url.rstrip('/')}/watches/{watch_id}"}])
    return {"inline_keyboard": rows}


class Telegram:
    def __init__(self, token: str, chat_id: str, http: requests.Session | None = None):
        self.base = f"https://api.telegram.org/bot{token}"
        self.chat_id = chat_id
        self.http = http or session()

    def send(self, text: str, markup: dict[str, Any] | None = None) -> int | None:
        data: dict[str, Any] = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML",
                                "disable_web_page_preview": "true"}
        if markup:
            data["reply_markup"] = json.dumps(markup)
        try:
            r = self.http.post(f"{self.base}/sendMessage", data=data, timeout=30)
            body = r.json()
        except (requests.RequestException, ValueError) as e:
            log.warning("telegram: erro %s", type(e).__name__)
            return None
        if not body.get("ok"):
            log.warning("telegram: %s", body.get("description"))   # nunca loga a URL (tem o token)
            return None
        return body["result"]["message_id"]
