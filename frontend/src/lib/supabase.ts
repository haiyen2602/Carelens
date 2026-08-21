import { createBrowserClient } from "@supabase/ssr";

// Supabase Browser Client (Singleton) cho Client Components & Web UI
// Su dung Public URL va Anon Key de xac thuc OAuth / Email.

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

export const isSupabaseConfigured = Boolean(supabaseUrl && supabaseAnonKey);

export function createClient() {
  if (!isSupabaseConfigured) {
    // Tranh crash khi render tren server luc thieu bien env, bao loi ro rang khi goi action
    return null;
  }
  return createBrowserClient(supabaseUrl, supabaseAnonKey);
}

export const supabase = isSupabaseConfigured
  ? createBrowserClient(supabaseUrl, supabaseAnonKey)
  : null;
