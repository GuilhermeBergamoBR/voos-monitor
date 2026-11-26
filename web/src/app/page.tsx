import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { duplicateWatch, setStatus } from "./watches/actions";

const brl = (v: number | null | undefined) =>
  v == null ? "—" : v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });

export const dynamic = "force-dynamic";

export default async function Home() {
  const supabase = await createClient();
  const { data: watches } = await supabase
    .from("watches").select("*").neq("status", "archived").order("created_at", { ascending: false });
  const { data: obs } = await supabase
    .from("price_observations").select("watch_id,price_total,observed_at")
    .order("observed_at", { ascending: false }).limit(1000);
  const best = new Map<string, number>();
  for (const o of obs ?? []) {
    const cur = best.get(o.watch_id);
    if (cur === undefined || o.price_total < cur) best.set(o.watch_id, o.price_total);
  }

  return (
    <main className="mx-auto max-w-3xl p-4 sm:p-6">
      <header className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold">✈️ Monitoramentos</h1>
        <Link href="/watches/new" className="rounded-lg bg-sky-600 px-3 py-2 text-sm font-medium text-white">
          + Novo
        </Link>
      </header>
      {!watches?.length && <p className="text-neutral-500">Nenhum monitoramento ainda.</p>}
      <ul className="grid gap-3">
        {watches?.map((w) => (
          <li key={w.id} className="rounded-xl border border-neutral-200 p-4 dark:border-neutral-800">
            <div className="flex items-start justify-between gap-3">
              <div>
                <Link href={`/watches/${w.id}`} className="font-medium hover:underline">{w.name}</Link>
                <p className="text-sm text-neutral-500">
                  {w.origins.join("/")} → {w.destinations.join("/")} ·{" "}
                  {w.date_mode === "fixed" ? `${w.depart_date ?? "?"}${w.return_date ? ` ↔ ${w.return_date}` : ""}` : "datas flexíveis"}
                  {" · "}{w.adults} pax
                </p>
              </div>
              <span className={`rounded-full px-2 py-0.5 text-xs ${w.status === "active" ? "bg-emerald-100 text-emerald-800" : "bg-neutral-200 text-neutral-700"}`}>
                {w.status === "active" ? "ativo" : w.status === "paused" ? "pausado" : w.status}
              </span>
            </div>
            <p className="mt-2 text-sm">
              Melhor preço visto: <b>{brl(best.get(w.id))}</b> · Orçamento: {brl(w.budget_total)}
            </p>
            <div className="mt-3 flex gap-2 text-sm">
              <form action={setStatus.bind(null, w.id, w.status === "active" ? "paused" : "active")}>
                <button className="rounded border px-2 py-1">{w.status === "active" ? "Pausar" : "Retomar"}</button>
              </form>
              <form action={duplicateWatch.bind(null, w.id)}>
                <button className="rounded border px-2 py-1">Duplicar</button>
              </form>
              <form action={setStatus.bind(null, w.id, "archived")}>
                <button className="rounded border px-2 py-1">Arquivar</button>
              </form>
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
