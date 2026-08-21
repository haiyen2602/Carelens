import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

// Supabase Server Client cho Route Handlers / Server Components
// Ho tro quan ly cookie session dong bo.

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

export const isSupabaseServerConfigured = Boolean(supabaseUrl && supabaseAnonKey);

export async function createServerSupabaseClient() {
  const cookieStore = await cookies();

  return createServerClient(supabaseUrl, supabaseAnonKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) => cookieStore.set(name, value, options));
        } catch {
          // Goi tu Server Component thi setAll co the throw, co the bo qua neu co Middleware
        }
      },
    },
  });
}
