import { createServerClient } from "@supabase/ssr";
import { createClient as createAdmin } from "@supabase/supabase-js";
import { cookies } from "next/headers";

/** Cliente com a sessão do usuário (respeita RLS). */
export async function createClient() {
  const cookieStore = await cookies();
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => cookieStore.getAll(),
        setAll: (list) => {
          try {
            list.forEach(({ name, value, options }) => cookieStore.set(name, value, options));
          } catch {
            /* chamado de Server Component: o middleware renova a sessão */
          }
        },
      },
    },
  );
}

/** Cliente service_role — SOMENTE em rotas de servidor (webhook do Telegram). Nunca no browser. */
export function createAdminClient() {
  return createAdmin(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.SUPABASE_SERVICE_ROLE_KEY!, {
    auth: { persistSession: false },
  });
}

export function isAllowedEmail(email?: string | null): boolean {
  const list = (process.env.ALLOWED_EMAILS ?? "").split(",").map((e) => e.trim().toLowerCase());
  return !!email && list.includes(email.toLowerCase());
}
