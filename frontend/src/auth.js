import { supabase } from "./supabaseClient";

const API = "";  // same origin

export async function loginEmail(email, password) {
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error("Invalid credentials");
  const data = await res.json();

  // Store token directly — skip supabase.auth.setSession entirely
  localStorage.setItem("access_token", data.access_token);
  localStorage.setItem("user", JSON.stringify({
    uid: data.uid, email: data.email, role: data.role,
  }));

  // Add this to loginEmail, after the fetch succeeds:
supabase.auth.onAuthStateChange((event, session) => {
  if (session?.access_token) {
    localStorage.setItem("access_token", session.access_token);
  }
});

  return { uid: data.uid, email: data.email, role: data.role };
}

export async function signUpEmail(email, password, role) {
  const res = await fetch("/api/auth/signup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, role }),
  });
  if (!res.ok) throw new Error((await res.json()).detail || "Signup failed");
  return res.json();
}

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
  const me = await fetch(`/api/auth/me?uid=${uid}`).then(r => r.ok ? r.json() : null);
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

export function getToken() {
  return localStorage.getItem("access_token");
}

export function getStoredUser() {
  try { return JSON.parse(localStorage.getItem("user")); }
  catch { return null; }
}

export function logout() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("user");
}

export function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function getValidToken() {
  // Try to get a fresh session from Supabase
  const { data: { session }, error } = await supabase.auth.getSession();
  if (session?.access_token) {
    // Update stored token with fresh one
    localStorage.setItem("access_token", session.access_token);
    return session.access_token;
  }
  // Fall back to stored token
  return localStorage.getItem("access_token");
}