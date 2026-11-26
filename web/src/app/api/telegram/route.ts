import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/server";

/** Webhook do Telegram: botões (👍/👎/Pausar/Já comprei) e comandos (/lista, /pausar, /status).
 *  Autenticado pelo header secreto registrado no setWebhook e restrito ao chat configurado. */

const TG = () => `https://api.telegram.org/bot${process.env.TELEGRAM_BOT_TOKEN}`;

async function tg(method: string, body: Record<string, unknown>) {
  await fetch(`${TG()}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

const THRESHOLD_STEP = 5;
const THRESHOLD_MIN = 40;
const THRESHOLD_MAX = 90;

export async function POST(req: Request) {
  if (req.headers.get("x-telegram-bot-api-secret-token") !== process.env.TELEGRAM_WEBHOOK_SECRET) {
    return NextResponse.json({ ok: false }, { status: 401 });
  }
  const update = await req.json();
  const chatId = String(update.callback_query?.message?.chat?.id ?? update.message?.chat?.id ?? "");
  if (chatId !== process.env.TELEGRAM_CHAT_ID) return NextResponse.json({ ok: true });
  const db = createAdminClient();

  // ---------- botões ----------
  if (update.callback_query) {
    const cq = update.callback_query;
    const [kind, id, arg] = String(cq.data ?? "").split(":");
    let answer = "ok";
    if (kind === "fb") {
      const { data: alert } = await db.from("alerts").select("id,watch_id").eq("id", id).single();
      if (alert) {
        const { data: w } = await db.from("watches").select("score_threshold").eq("id", alert.watch_id).single();
        const before = w?.score_threshold ?? 70;
        // 👍 = alerta útil -> pode receber mais (limiar desce); 👎 = ruído -> limiar sobe
        const after = Math.min(THRESHOLD_MAX, Math.max(THRESHOLD_MIN, before + (arg === "1" ? -THRESHOLD_STEP : THRESHOLD_STEP)));
        await db.from("watches").update({ score_threshold: after }).eq("id", alert.watch_id);
        await db.from("feedback").insert({
          alert_id: alert.id, watch_id: alert.watch_id, vote: Number(arg),
          threshold_before: before, threshold_after: after, channel: "telegram",
        });
        answer = `Valeu! Limiar ${before} → ${after}`;
      } else answer = "Alerta de teste — nada a ajustar";
    } else if (kind === "pause" || kind === "bought") {
      if (id !== "teste") {
        await db.from("watches").update({ status: kind === "pause" ? "paused" : "bought" }).eq("id", id);
      }
      answer = kind === "pause" ? "Monitoramento pausado" : "Boa viagem! Monitoramento encerrado ✈️";
    }
    await tg("answerCallbackQuery", { callback_query_id: cq.id, text: answer });
    return NextResponse.json({ ok: true });
  }

  // ---------- comandos ----------
  const text: string = update.message?.text ?? "";
  const reply = (t: string) => tg("sendMessage", { chat_id: chatId, text: t, parse_mode: "HTML" });

  if (text.startsWith("/lista")) {
    const { data } = await db.from("watches").select("name,status").in("status", ["active", "paused"]);
    await reply(data?.length
      ? data.map((w, i) => `${i + 1}. ${w.status === "active" ? "🟢" : "⏸"} ${w.name}`).join("\n")
      : "Nenhum monitoramento.");
  } else if (text.startsWith("/pausar")) {
    const n = Number(text.split(/\s+/)[1]);
    const { data } = await db.from("watches").select("id,name").in("status", ["active", "paused"]);
    const w = data?.[n - 1];
    if (w) {
      await db.from("watches").update({ status: "paused" }).eq("id", w.id);
      await reply(`⏸ Pausado: ${w.name}`);
    } else await reply("Use /pausar &lt;número da /lista&gt;");
  } else if (text.startsWith("/status")) {
    const month = new Date().toISOString().slice(0, 7);
    const { data: q } = await db.from("quota_usage").select("*").eq("month", month);
    const { data: h } = await db.from("source_health").select("*");
    const { data: r } = await db.from("runs").select("finished_at,ok").order("started_at", { ascending: false }).limit(1);
    await reply([
      "<b>Status</b>",
      ...(q ?? []).map((x) => `• ${x.api}: ${x.used}/${x.budget} no mês`),
      ...(h ?? []).map((x) => `• ${x.source}: ${x.consecutive_failures ? `⚠️ ${x.consecutive_failures} falhas` : "✅ ok"}`),
      r?.[0] ? `Última execução: ${new Date(r[0].finished_at).toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo" })} ${r[0].ok ? "✅" : "⚠️"}` : "Sem execuções ainda",
    ].join("\n"));
  } else if (text.startsWith("/novo")) {
    await reply("Criar por texto livre chega na Fase 4. Por enquanto, use o painel: " + (process.env.PANEL_URL ?? ""));
  }
  return NextResponse.json({ ok: true });
}
