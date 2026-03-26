import { supabase } from "./supabaseClient";

// ─── Email login — sign in through Supabase JS directly so the session
//     is owned by the Supabase client and auto-refreshes every hour. ──────────
export async function loginEmail(email, password) {
  const { data, error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) throw new Error(error.message || "Invalid credentials");

  const token = data.session.access_token;
  const uid   = data.user.id;

  const res = await fetch(`/api/auth/me?uid=${uid}`, {
    headers: { Authorization: `Bearer ${token}` }
  });

  if (!res.ok) {
    throw new Error("Account not found in system. Please sign up first.");
  }

  const me = await res.json();
  localStorage.setItem("access_token", token);
  localStorage.setItem("user", JSON.stringify({ uid, email, role: me.role }));
  return { uid, email, role: me.role };
}

// ─── Sign up — register in Supabase then save role via backend ────────────────
export async function signUpEmail(email, password, role) {
  // First try to sign in — if account exists in Supabase but not our DB
  const { data: signInData, error: signInError } = 
    await supabase.auth.signInWithPassword({ email, password });

  let uid, token;

  if (signInData?.session) {
    // Already in Supabase auth — just make sure they're in our DB
    uid   = signInData.user.id;
    token = signInData.session.access_token;
  } else {
    // Fresh signup
    const { data, error } = await supabase.auth.signUp({ email, password });
    if (error) throw new Error(error.message || "Signup failed");
    if (!data.session) throw new Error(
      "Check your email for a confirmation link, then sign in."
    );
    uid   = data.user.id;
    token = data.session.access_token;
  }

  // Save to our backend DB (upsert — safe to call multiple times)
  const res = await fetch("/api/auth/signup", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ email, password, role }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to save account");
  }

  return res.json();
}

// ─── Google OAuth ─────────────────────────────────────────────────────────────
export async function loginGoogle() {
  const { error } = await supabase.auth.signInWithOAuth({
    provider: "google",
    options: { redirectTo: `${window.location.origin}/auth/callback` },
  });
  if (error) throw error;
}

export async function handleGoogleCallback() {
  const { data: { session }, error } = await supabase.auth.getSession();
  if (error || !session) return null;

  const uid   = session.user.id;
  const email = session.user.email;
  const token = session.access_token;

  const me = await fetch(`/api/auth/me?uid=${uid}`, {
    headers: { Authorization: `Bearer ${token}` },
  }).then(r => r.ok ? r.json() : null);

  if (me) {
    localStorage.setItem("access_token", token);
    localStorage.setItem("user", JSON.stringify({ uid, email, role: me.role }));
    return { uid, email, role: me.role, token };
  }
  return { uid, email, role: null, token };
}

export async function setGoogleRole(uid, email, role, token) {
  const res = await fetch("/api/auth/google/set-role", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ supabase_uid: uid, email, role }),
  });
  if (!res.ok) throw new Error("Could not save role");
  localStorage.setItem("access_token", token);
  localStorage.setItem("user", JSON.stringify({ uid, email, role }));
  return role;
}

// ─── Token helpers ────────────────────────────────────────────────────────────

// Always gets the freshest token — Supabase JS auto-refreshes it silently.
export async function getValidToken() {
  const { data: { session } } = await supabase.auth.getSession();
  if (session?.access_token) {
    // Keep localStorage in sync so any direct reads are also fresh
    localStorage.setItem("access_token", session.access_token);
    return session.access_token;
  }
  // Fallback for any edge case
  return localStorage.getItem("access_token");
}

export function getToken() {
  return localStorage.getItem("access_token");
}

export function getStoredUser() {
  try { return JSON.parse(localStorage.getItem("user")); }
  catch { return null; }
}

export function logout() {
  supabase.auth.signOut();   // clears Supabase session too
  localStorage.removeItem("access_token");
  localStorage.removeItem("user");
}

export function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}