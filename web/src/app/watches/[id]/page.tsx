import Link from "next/link";
import { notFound } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import WatchForm from "../WatchForm";

export const dynamic = "force-dynamic";

const brl = (v: number | null | undefined) =>
  v == null ? "—" : v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });

export default async function WatchPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await createClient();
  const { data: watch } = await supabase.from("watches").select("*").eq("id", id).single();
  if (!watch) notFound();
  const { data: obs } = await supabase
    .from("price_observations").select("*").eq("watch_id", id)
    .order("observed_at", { ascending: false }).limit(30);
  const { data: alerts } = await supabase
    .from("alerts").select("*").eq("watch_id", id).order("sent_at", { ascending: false }).limit(10);

  return (
    <main className="mx-auto max-w-xl p-4 sm:p-6">
      <Link href="/" className="text-sm text-sky-700">← voltar</Link>
      <h1 className="my-4 text-xl font-semibold">{watch.name}</h1>

      <section className="mb-6">
        <h2 className="mb-2 font-medium">Últimos preços</h2>
        {!obs?.length ? (
          <p className="text-sm text-neutral-500">Ainda sem coleta. O worker roda de hora em hora.</p>
        ) : (
          <ul className="divide-y divide-neutral-200 text-sm dark:divide-neutral-800">
            {obs.map((o) => (
              <li key={o.id} className="flex justify-between py-1.5">
                <span>{new Date(o.observed_at).toLocaleString("pt-BR")} · {o.source}{o.price_level ? ` · ${o.price_level}` : ""}</span>
                <b>{brl(o.price_total)}</b>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mb-6">
        <h2 className="mb-2 font-medium">Alertas enviados</h2>
        {!alerts?.length ? <p className="text-sm text-neutral-500">Nenhum ainda.</p> : (
          <ul className="grid gap-2 text-sm">
            {alerts.map((a) => (
              <li key={a.id}>{new Date(a.sent_at).toLocaleString("pt-BR")} — <b>{brl(a.price_total)}</b> · score {a.score} · {a.why}</li>
            ))}
          </ul>
        )}
      </section>

      <h2 className="mb-2 font-medium">Editar</h2>
      <WatchForm watch={watch} />
    </main>
  );
}
