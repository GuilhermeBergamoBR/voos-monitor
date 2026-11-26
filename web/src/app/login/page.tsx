"use client";

import { createBrowserClient } from "@supabase/ssr";
import { useState } from "react";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "sent" | "error">("idle");
  const [msg, setMsg] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const supabase = createBrowserClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    );
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: `${window.location.origin}/auth/callback`, shouldCreateUser: false },
    });
    if (error) {
      setState("error");
      setMsg(error.message);
    } else setState("sent");
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 p-6">
      <h1 className="text-2xl font-semibold">✈️ Monitor de passagens</h1>
      {state === "sent" ? (
        <p data-testid="sent">Enviamos um link de acesso para <b>{email}</b>. Abra no mesmo aparelho.</p>
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-3">
          <label className="text-sm text-neutral-600 dark:text-neutral-300" htmlFor="email">E-mail</label>
          <input
            id="email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="rounded-lg border border-neutral-300 bg-transparent px-3 py-2"
            placeholder="voce@exemplo.com"
          />
          <button className="rounded-lg bg-sky-600 px-4 py-2 font-medium text-white hover:bg-sky-700">
            Receber link de acesso
          </button>
          {state === "error" && <p className="text-sm text-red-600">{msg}</p>}
        </form>
      )}
    </main>
  );
}
