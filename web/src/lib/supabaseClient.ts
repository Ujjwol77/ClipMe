import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseAnonKey) {
  console.warn(
    "NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY are not set. " +
      "Auth and storage upload will not work until web/.env.local is configured."
  );
}

// Falls back to a placeholder so builds (and pages that don't touch auth) don't crash
// when env vars aren't configured yet; real auth/storage calls will fail loudly instead.
export const supabase = createClient(
  supabaseUrl || "https://placeholder.supabase.co",
  supabaseAnonKey || "placeholder-anon-key"
);

export const STORAGE_BUCKET = process.env.NEXT_PUBLIC_STORAGE_BUCKET ?? "clipme-media";
