"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

const list = (v: FormDataEntryValue | null) =>
  String(v ?? "")
    .split(/[,\s]+/)
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean);
const num = (v: FormDataEntryValue | null) => (v === null || v === "" ? null : Number(v));
const str = (v: FormDataEntryValue | null) => (v === null || v === "" ? null : String(v));

function fromForm(f: FormData) {
  const flexible = f.get("date_mode") === "flexible";
  return {
    name: String(f.get("name") ?? "").trim(),
    origins: list(f.get("origins")),
    destinations: list(f.get("destinations")),
    date_mode: flexible ? "flexible" : "fixed",
    depart_date: flexible ? null : str(f.get("depart_date")),
    return_date: flexible ? null : str(f.get("return_date")),
    depart_from: flexible ? str(f.get("depart_from")) : null,
    depart_to: flexible ? str(f.get("depart_to")) : null,
    nights_min: flexible ? num(f.get("nights_min")) : null,
    nights_max: flexible ? num(f.get("nights_max")) : null,
    one_way: f.get("one_way") === "on",
    adults: num(f.get("adults")) ?? 2,
    cabin: String(f.get("cabin") ?? "economy"),
    max_stops: num(f.get("max_stops")),
    max_duration_hours: num(f.get("max_duration_hours")),
    need_checked_bag: f.get("need_checked_bag") === "on",
    budget_total: num(f.get("budget_total")),
    sensitivity: String(f.get("sensitivity") ?? "balanced"),
  };
}

export async function saveWatch(formData: FormData) {
  const supabase = await createClient();
  const id = str(formData.get("id"));
  const row = fromForm(formData);
  if (!row.name || !row.origins.length || !row.destinations.length) {
    throw new Error("Preencha nome, origem e destino.");
  }
  const { error } = id
    ? await supabase.from("watches").update(row).eq("id", id)
    : await supabase.from("watches").insert(row);
  if (error) throw new Error(error.message);
  revalidatePath("/");
  redirect("/");
}

export async function setStatus(id: string, status: "active" | "paused" | "archived") {
  const supabase = await createClient();
  const { error } = await supabase.from("watches").update({ status }).eq("id", id);
  if (error) throw new Error(error.message);
  revalidatePath("/");
}

export async function duplicateWatch(id: string) {
  const supabase = await createClient();
  const { data, error } = await supabase.from("watches").select("*").eq("id", id).single();
  if (error || !data) throw new Error(error?.message ?? "não encontrado");
  const { id: _id, created_at: _c, updated_at: _u, created_by: _b, ...rest } = data;
  void _id; void _c; void _u; void _b;
  await supabase.from("watches").insert({ ...rest, name: `${rest.name} (cópia)`, status: "paused" });
  revalidatePath("/");
}
