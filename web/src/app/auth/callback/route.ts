import { NextResponse } from "next/server";
import { createClient, isAllowedEmail } from "@/lib/supabase/server";

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  if (code) {
    const supabase = await createClient();
    const { data, error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error && isAllowedEmail(data.user?.email)) {
      return NextResponse.redirect(`${origin}/`);
    }
    await supabase.auth.signOut();
  }
  return NextResponse.redirect(`${origin}/login?erro=acesso`);
}
