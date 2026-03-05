import { createClient } from "@supabase/supabase-js";

const SUPABASE_URL      = import.meta.env.VITE_SUPABASE_URL;
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY;

// This will show in browser console on every page load
console.log("[Supabase] URL:", SUPABASE_URL);
console.log("[Supabase] Key:", SUPABASE_ANON_KEY ? "loaded ✓" : "MISSING ✗");

if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
  throw new Error("Supabase env vars missing — check frontend/.env and rebuild");
}

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);