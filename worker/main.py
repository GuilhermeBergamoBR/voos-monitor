"""Uma execução do worker (Fase 1: datas fixas via SerpApi).

python -m worker.main                 normal
python -m worker.main --dry-run       não grava nem envia
python -m worker.main --send-test     envia um alerta de teste no formato real
python -m worker.main --watch-id ID   roda só um monitoramento (ignora o agendador)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from worker.fingerprint import fingerprint, rejection_reason
from worker.models import Itinerary
from worker.notify import Telegram, format_alert, keyboard
from worker.pricing import comparable_price
from worker.scheduler import Candidate, daily_budget, pick
from worker.scoring import WatchHistory, evaluate
from worker.sources.serpapi_flights import SerpApiFlights


class JsonFormatter(logging.Formatter):
    def format(self, r: logging.LogRecord) -> str:
        return json.dumps({"t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                           "lvl": r.levelname, "mod": r.name, "msg": r.getMessage()}, ensure_ascii=False)


log = logging.getLogger("worker")
CFG = yaml.safe_load((Path(__file__).parent / "config.yaml").read_text(encoding="utf-8"))


def env(name: str) -> str | None:
    return (os.environ.get(name) or "").strip() or None


def quiet_now() -> bool:
    q = CFG["quiet_hours"]
    h = datetime.now(ZoneInfo(CFG["timezone"])).hour
    return h >= q["start"] or h < q["end"]


def prepare(its: list[Itinerary], w: dict[str, Any]) -> list[Itinerary]:
    ok = []
    for it in its:
        it.price_total = comparable_price(it, bool(w.get("need_checked_bag")), CFG)
        it.fingerprint = fingerprint(it)
        why = rejection_reason(it, w)
        if why:
            log.debug("rejeitado: %s", why)
            continue
        ok.append(it)
    return sorted(ok, key=lambda i: i.price_total)


def pct_below_normal(it: Itinerary, h: WatchHistory) -> float:
    ref = h.median30 or h.median14 or (sum(it.typical_range) / 2 if it.typical_range else None)
    return max(0.0, (ref - it.price_total) / ref * 100) if ref else 0.0


def build_alert(w: dict[str, Any], it: Itinerary, h: WatchHistory, dec) -> dict[str, Any]:
    return {
        "watch": {"id": w["id"], "name": w["name"]}, "itinerary": it.to_dict(), "score": dec.score,
        "rule": dec.rule, "reasons": dec.reasons, "why": "; ".join(dec.reasons[:2]),
        "urgent": dec.urgent, "min_price": h.min_price, "pct_below": pct_below_normal(it, h),
    }


def send_grouped(tg: Telegram, alerts: list[dict[str, Any]], ids: list[str], panel: str | None) -> int | None:
    if len(alerts) == 1:
        return tg.send(format_alert(alerts[0]), keyboard(ids[0], alerts[0]["watch"]["id"], panel))
    text = f"<b>{len(alerts)} achados de passagem</b>\n\n" + "\n\n".join(
        f"<b>#{n}</b> " + format_alert(a) for n, a in enumerate(alerts, 1))
    rows: list[list[dict[str, str]]] = []
    for n, (a, aid) in enumerate(zip(alerts, ids), 1):
        kb = keyboard(aid, a["watch"]["id"], None)["inline_keyboard"][0]
        rows.append([{**b, "text": f"#{n} {b['text']}"} for b in kb])
    return tg.send(text[:4000], {"inline_keyboard": rows})


def send_test(tg: Telegram, panel: str | None) -> None:
    from worker.models import Layover, Segment
    it = Itinerary(
        source="serpapi", live=True, depart_date="2027-03-10", return_date="2027-03-20",
        segments=[Segment("TAP", "TP82", "GRU", "LIS", "2027-03-10 22:35", "2027-03-11 11:50", 615)],
        layovers=[], total_duration_min=615, price_raw=5980.0, adults=2, bag_included=True,
        price_level="low", typical_range=(7400.0, 9800.0),
        booking_url="https://www.google.com/travel/flights",
    )
    it.price_total, it.fingerprint = it.price_raw, "teste"
    h = WatchHistory(min_price=6890.0)
    alert = {"watch": {"id": "teste", "name": "🧪 TESTE — SP → Lisboa"}, "itinerary": it.to_dict(),
             "score": 88, "why": "Exemplo: 19% abaixo da faixa típica e menor preço já visto",
             "urgent": False, "min_price": h.min_price, "pct_below": 30.0}
    mid = tg.send(format_alert(alert), keyboard("teste", "teste", panel))
    log.info("mensagem de teste enviada: %s", bool(mid))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--send-test", action="store_true")
    ap.add_argument("--watch-id")
    args = ap.parse_args(argv)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    tg = Telegram(env("TELEGRAM_BOT_TOKEN"), env("TELEGRAM_CHAT_ID")) \
        if env("TELEGRAM_BOT_TOKEN") and env("TELEGRAM_CHAT_ID") else None
    panel = env("PANEL_URL")
    if args.send_test:
        if not tg:
            log.error("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID ausentes")
            return 1
        send_test(tg, panel)
        return 0

    from worker.storage import Store
    if not (env("SUPABASE_URL") and env("SUPABASE_SERVICE_ROLE_KEY")):
        log.error("SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY ausentes")
        return 1
    store = Store(env("SUPABASE_URL"), env("SUPABASE_SERVICE_ROLE_KEY"))
    started = datetime.now(timezone.utc).isoformat()
    summary: dict[str, Any] = {"searches": 0, "alerts": 0, "watches": 0, "errors": []}
    threshold = CFG["health_failures_to_warn"]

    watches = [w for w in store.active_watches(args.watch_id) if w["date_mode"] == "fixed"]
    summary["watches"] = len(watches)
    budget = CFG["quotas"]["serpapi_searches"]
    used, _ = store.quota("serpapi", budget)
    per_day = daily_budget(budget - used, CFG["quotas"]["reserve_for_alerts"])

    # última busca ao vivo de cada monitoramento
    cands = []
    for w in watches:
        last = store._get("searches", watch_id=f"eq.{w['id']}", source="eq.serpapi", ok="is.true",
                          select="created_at", order="created_at.desc", limit="1")
        hours = 1e9 if not last else (datetime.now(timezone.utc) -
                                      datetime.fromisoformat(last[0]["created_at"])).total_seconds() / 3600
        cands.append(Candidate(watch=w, hours_since_last=hours))
    chosen = cands if args.watch_id else pick(cands, per_day)
    log.info("cota serpapi: %d/%d usadas, %.1f/dia, %d monitoramento(s) nesta execução",
             used, budget, per_day, len(chosen))

    serp = SerpApiFlights(env("SERPAPI_KEY")) if env("SERPAPI_KEY") else None
    pending: list[tuple[dict[str, Any], dict[str, Any]]] = []      # (alerta, linha do banco)
    health_msgs: list[str] = []
    for c in chosen:
        w = c.watch
        if not serp:
            break
        params = {"origins": w["origins"], "destinations": w["destinations"], "depart": str(w["depart_date"]),
                  "ret": str(w["return_date"]) if w.get("return_date") and not w["one_way"] else None,
                  "adults": w["adults"], "cabin": w["cabin"], "max_stops": w.get("max_stops")}
        before = serp.credits_used
        try:
            its, _insights = serp.search(**params)
            ok, err = True, None
        except Exception as e:  # noqa: BLE001
            its, ok, err = [], False, f"{type(e).__name__}: {e}"
            summary["errors"].append(err[:200])
            log.error("serpapi falhou no monitoramento %s: %s", w["id"], err[:200])
        spent = serp.credits_used - before
        summary["searches"] += spent
        if not args.dry_run:
            store.log_search(w["id"], "serpapi", params, spent, ok, err)
            store.add_usage("serpapi", spent, budget)
            ev = store.health("serpapi", ok, err, threshold)
            if ev == "down":
                health_msgs.append(f"⚠️ monitor com problema em <b>SerpApi</b> ({threshold} falhas seguidas)")
            elif ev == "up":
                health_msgs.append("✅ SerpApi voltou ao normal")
        accepted = prepare(its, w)
        h = store.history(w["id"])
        cold = h.min_price is None
        best = accepted[0] if accepted else None
        if best and not cold:
            dec = evaluate(best, w, h)
            log.info("monitoramento %s: melhor %.0f, score %d, alerta=%s", w["id"], best.price_total,
                     dec.score, dec.alert)
            if dec.alert:
                a = build_alert(w, best, h, dec)
                row = {"watch_id": w["id"], "fingerprint": best.fingerprint, "price_total": best.price_total,
                       "score": dec.score, "rule": dec.rule, "reasons": dec.reasons, "why": a["why"],
                       "payload": a, "pending": quiet_now() and not dec.urgent}
                pending.append((a, row))
        elif cold:
            log.info("monitoramento %s: coleta inicial silenciosa", w["id"])
        if not args.dry_run:
            store.record(w["id"], accepted[:CFG["store_top_n"]])

    if args.dry_run:
        for a, _ in pending:
            print("\n===== SERIA ENVIADO =====\n" + format_alert(a))
        return 0

    to_send = [(a, r) for a, r in pending if not r["pending"]]
    for a, r in pending:
        if r["pending"]:
            store.save_alert(r)          # fica na fila até as 7h
    if not quiet_now():
        queued = store._get("alerts", pending="is.true", select="id,payload", order="sent_at.asc")
        if queued and tg:
            mid = send_grouped(tg, [q["payload"] for q in queued], [q["id"] for q in queued], panel)
            if mid:
                for q in queued:
                    store._patch("alerts", {"id": f"eq.{q['id']}"},
                                 {"pending": False, "telegram_message_id": mid})
    if to_send and tg:
        ids = [store.save_alert(r) for _, r in to_send]
        mid = send_grouped(tg, [a for a, _ in to_send], ids, panel)
        for i in ids:   # falhou o envio -> volta para a fila e tenta na próxima execução
            store._patch("alerts", {"id": f"eq.{i}"},
                         {"telegram_message_id": mid} if mid else {"pending": True})
    summary["alerts"] = len(pending)
    if tg:
        for m in health_msgs:
            tg.send(m)
    store.run(summary, ok=not summary["errors"], started=started)
    log.info("fim: %s", json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
