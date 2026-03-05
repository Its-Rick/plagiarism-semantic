import { useState, useEffect, useRef } from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import * as mammoth from "mammoth";
import {
  signUpEmail, loginEmail, loginGoogle,
  handleGoogleCallback, setGoogleRole,
  getStoredUser, logout,
} from "./auth";
import { supabase } from "./supabaseClient";
import { getValidToken } from "./auth";  

// ─── API helper ───────────────────────────────────────────────────────────────
async function api(path, options = {}) {
  const token = await getValidToken();   // ← was: localStorage.getItem("access_token")
  const res = await fetch(`/api${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("text/html")) throw new Error(`Route /api${path} not found on server`);
  if (res.status === 401) {
    // Token truly expired — force logout and re-login
    localStorage.removeItem("access_token");
    localStorage.removeItem("user");
    window.location.reload();
    return;
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  if (res.status === 204) return null;
  return res.json();
}

// ─── Utilities ────────────────────────────────────────────────────────────────
const getScoreColor = (score) => {
  if (score === null || score === undefined) return "#64748b";
  if (score < 25) return "#22c55e";
  if (score < 50) return "#f59e0b";
  if (score < 75) return "#f97316";
  return "#ef4444";
};
const getScoreLabel = (score) => {
  if (score === null || score === undefined) return "Pending";
  if (score < 25) return "Original";
  if (score < 50) return "Low Risk";
  if (score < 75) return "Suspicious";
  return "High Risk";
};

// ─── Countdown component ──────────────────────────────────────────────────────
function Countdown({ deadline }) {
  const [timeLeft, setTimeLeft] = useState("");
  useEffect(() => {
    const update = () => {
      const diff = new Date(deadline) - new Date();
      if (diff <= 0) { setTimeLeft("Deadline passed"); return; }
      const h = Math.floor(diff / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      setTimeLeft(`${h}h ${m}m ${s}s remaining`);
    };
    update();
    const t = setInterval(update, 1000);
    return () => clearInterval(t);
  }, [deadline]);
  const isPast = new Date(deadline) < new Date();
  return <span style={{ fontSize: 12, color: isPast ? "#ef4444" : "#f59e0b", fontWeight: 600 }}>⏱ {timeLeft}</span>;
}

// ─── Score Gauge ──────────────────────────────────────────────────────────────
function ScoreGauge({ score }) {
  if (score === null || score === undefined) {
    return (
      <div style={{ textAlign: "center", padding: "10px 20px" }}>
        <div style={{ fontSize: 28, marginBottom: 4 }}>⏳</div>
        <div style={{ fontSize: 12, color: "#64748b" }}>Pending</div>
      </div>
    );
  }
  const r = 54, cx = 70, cy = 70;
  const circumference = 2 * Math.PI * r;
  const filled = (score / 100) * circumference;
  const color = getScoreColor(score);
  return (
    <svg width="140" height="100" viewBox="0 0 140 100">
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="#1e293b" strokeWidth="10"
        strokeDasharray={`${circumference * 0.75} ${circumference * 0.25}`}
        strokeLinecap="round" transform={`rotate(135 ${cx} ${cy})`} />
      <circle cx={cx} cy={cy} r={r} fill="none" stroke={color} strokeWidth="10"
        strokeDasharray={`${filled * 0.75} ${circumference}`}
        strokeLinecap="round" transform={`rotate(135 ${cx} ${cy})`}
        style={{ transition: "stroke-dasharray 1s ease" }} />
      <text x={cx} y={cy - 4} textAnchor="middle" fill={color} fontSize="22" fontWeight="700">{score}%</text>
      <text x={cx} y={cy + 14} textAnchor="middle" fill="#94a3b8" fontSize="10">{getScoreLabel(score)}</text>
    </svg>
  );
}

function Badge({ label, color }) {
  const c = color === "green"  ? { bg: "rgba(34,197,94,0.15)",   clr: "#86efac", br: "rgba(34,197,94,0.3)" }
    : color === "amber"        ? { bg: "rgba(245,158,11,0.15)",  clr: "#fcd34d", br: "rgba(245,158,11,0.3)" }
    : color === "red"          ? { bg: "rgba(239,68,68,0.15)",   clr: "#fca5a5", br: "rgba(239,68,68,0.3)" }
    : color === "blue"         ? { bg: "rgba(99,102,241,0.15)",  clr: "#a5b4fc", br: "rgba(99,102,241,0.3)" }
    :                            { bg: "rgba(100,116,139,0.15)", clr: "#94a3b8", br: "rgba(100,116,139,0.3)" };
  return <span style={{ fontSize: 11, padding: "3px 10px", borderRadius: 99, border: `1px solid ${c.br}`, background: c.bg, color: c.clr, fontWeight: 600 }}>{label}</span>;
}

// ─── Role Picker ──────────────────────────────────────────────────────────────
function RolePicker({ onPick }) {
  const [loading, setLoading] = useState(false);
  return (
    <div style={{ minHeight: "100vh", background: "#050a14", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "'DM Sans', sans-serif" }}>
      <div style={{ background: "rgba(15,23,42,0.95)", border: "1px solid rgba(99,102,241,0.25)", borderRadius: 20, padding: 40, width: 380, textAlign: "center" }}>
        <div style={{ fontSize: 32, marginBottom: 12 }}>👤</div>
        <h2 style={{ color: "#e2e8f0", margin: "0 0 8px", fontSize: 20 }}>One last step</h2>
        <p style={{ color: "#64748b", fontSize: 14, marginBottom: 28 }}>How will you use EduCheck?</p>
        <div style={{ display: "flex", gap: 12 }}>
          {["student", "teacher"].map(role => (
            <button key={role} disabled={loading} onClick={async () => { setLoading(true); await onPick(role); }}
              style={{ flex: 1, padding: "16px", borderRadius: 12, border: "1px solid #1e293b", background: "#0f172a", color: "#e2e8f0", cursor: "pointer", fontSize: 14, fontWeight: 600, fontFamily: "'DM Sans', sans-serif" }}>
              {role === "student" ? "🎓" : "👨‍🏫"}<br />
              <span style={{ fontSize: 13, color: "#94a3b8", textTransform: "capitalize" }}>{role}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Auth Screen ──────────────────────────────────────────────────────────────
function AuthScreen({ onLogin }) {
  const [mode, setMode]         = useState("login");
  const [role, setRole]         = useState("student");
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]       = useState("");
  const [loading, setLoading]   = useState(false);

  useEffect(() => {
    if (window.location.pathname === "/auth/callback") {
      handleGoogleCallback().then(user => {
        if (user?.role) { onLogin(user); window.history.replaceState({}, "", "/"); }
      });
    }
  }, []);

  const handleSubmit = async () => {
    setError(""); setLoading(true);
    try {
      if (mode === "signup") {
        await signUpEmail(email, password, role);
        setMode("login");
        alert("Account created! Please sign in.");
      } else {
        const user = await loginEmail(email, password);
        onLogin(user);
      }
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  const s = {
    page:  { minHeight: "100vh", background: "#050a14", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "'DM Sans', sans-serif", position: "relative", overflow: "hidden" },
    card:  { position: "relative", width: 440, background: "rgba(15,23,42,0.95)", border: "1px solid rgba(99,102,241,0.25)", borderRadius: 20, padding: 40, backdropFilter: "blur(20px)" },
    label: { color: "#94a3b8", fontSize: 12, fontWeight: 600, letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: 6, display: "block" },
    input: { width: "100%", background: "#0f172a", border: "1px solid #1e293b", borderRadius: 10, padding: "12px 14px", color: "#e2e8f0", fontSize: 14, outline: "none", boxSizing: "border-box", fontFamily: "'DM Sans', sans-serif" },
    btn:   (grad) => ({ background: grad, color: "white", border: "none", borderRadius: 10, padding: "13px", fontSize: 15, fontWeight: 700, cursor: "pointer", fontFamily: "'DM Sans', sans-serif", width: "100%" }),
  };

  return (
    <div style={s.page}>
      <div style={{ position: "absolute", inset: 0, backgroundImage: "linear-gradient(rgba(99,102,241,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(99,102,241,0.06) 1px, transparent 1px)", backgroundSize: "60px 60px" }} />
      <div style={s.card}>
        <div style={{ textAlign: "center", marginBottom: 28 }}>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
            <div style={{ width: 34, height: 34, background: "linear-gradient(135deg, #6366f1, #8b5cf6)", borderRadius: 9, display: "flex", alignItems: "center", justifyContent: "center" }}>⬡</div>
            <span style={{ color: "#e2e8f0", fontSize: 22, fontWeight: 700 }}>EduCheck</span>
          </div>
          <p style={{ color: "#64748b", fontSize: 13, margin: 0 }}>AI-Powered Plagiarism Detection</p>
        </div>

        <div style={{ display: "flex", background: "#0f172a", borderRadius: 12, padding: 4, marginBottom: 24, border: "1px solid #1e293b" }}>
          {["login", "signup"].map(m => (
            <button key={m} onClick={() => setMode(m)} style={{ flex: 1, padding: "10px", borderRadius: 9, border: "none", cursor: "pointer", fontSize: 14, fontWeight: 600, fontFamily: "'DM Sans', sans-serif", background: mode === m ? "linear-gradient(135deg, #6366f1, #8b5cf6)" : "transparent", color: mode === m ? "white" : "#64748b" }}>
              {m === "login" ? "Sign In" : "Sign Up"}
            </button>
          ))}
        </div>

        {mode === "signup" && (
          <div style={{ marginBottom: 18 }}>
            <label style={s.label}>I am a</label>
            <div style={{ display: "flex", gap: 10 }}>
              {["student", "teacher"].map(r => (
                <button key={r} onClick={() => setRole(r)} style={{ flex: 1, padding: "10px", borderRadius: 10, border: `1px solid ${role === r ? "#6366f1" : "#1e293b"}`, background: role === r ? "rgba(99,102,241,0.12)" : "#0f172a", color: role === r ? "#a5b4fc" : "#64748b", cursor: "pointer", fontSize: 13, fontWeight: 600, fontFamily: "'DM Sans', sans-serif" }}>
                  {r === "student" ? "🎓 Student" : "👨‍🏫 Teacher"}
                </button>
              ))}
            </div>
          </div>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: 14, marginBottom: 16 }}>
          <div>
            <label style={s.label}>Email</label>
            <input value={email} onChange={e => setEmail(e.target.value)} placeholder="you@school.edu" style={s.input} />
          </div>
          <div>
            <label style={s.label}>Password</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••" onKeyDown={e => e.key === "Enter" && handleSubmit()} style={s.input} />
          </div>
          {error && <div style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 8, padding: "10px 14px", color: "#f87171", fontSize: 13 }}>{error}</div>}
          <button onClick={handleSubmit} disabled={loading} style={s.btn(loading ? "#374151" : "linear-gradient(135deg, #6366f1, #8b5cf6)")}>
            {loading ? "Please wait..." : mode === "login" ? "Sign In →" : "Create Account →"}
          </button>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
          <div style={{ flex: 1, height: 1, background: "#1e293b" }} />
          <span style={{ color: "#475569", fontSize: 12 }}>or</span>
          <div style={{ flex: 1, height: 1, background: "#1e293b" }} />
        </div>

        <button onClick={() => loginGoogle()} disabled={loading} style={{ ...s.btn("transparent"), border: "1px solid #1e293b", color: "#e2e8f0", display: "flex", alignItems: "center", justifyContent: "center", gap: 10, fontSize: 14 }}>
          <svg width="18" height="18" viewBox="0 0 48 48">
            <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
            <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
            <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
            <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
          </svg>
          Continue with Google
        </button>
      </div>
    </div>
  );
}

// ─── TEACHER DASHBOARD ────────────────────────────────────────────────────────
function TeacherDashboard({ user, onLogout }) {
  const [tab, setTab]                   = useState("overview");
  const [assignments, setAssignments]   = useState([]);
  const [submissions, setSubmissions]   = useState([]);
  const [selectedAssignment, setSelectedAssignment] = useState(null);
  const [showCreate, setShowCreate]     = useState(false);
  const [newTitle, setNewTitle]         = useState("");
  const [newDeadline, setNewDeadline]   = useState("");
  const [creating, setCreating]         = useState(false);
  const [editingId, setEditingId]       = useState(null);
  const [editDeadline, setEditDeadline] = useState("");
  const [toast, setToast]               = useState(null);
  const [loading, setLoading]           = useState(true);

  const showToast = (msg, type = "success") => { setToast({ msg, type }); setTimeout(() => setToast(null), 4000); };

  const refresh = () =>
    Promise.all([api("/assignments"), api("/submissions")])
      .then(([a, s]) => { setAssignments(a); setSubmissions(s); })
      .catch(err => showToast(err.message, "error"));

  useEffect(() => {
    refresh().then(() => setLoading(false));
    // Poll every 30s so teacher sees when status changes to "checked"
    const t = setInterval(refresh, 30000);
    return () => clearInterval(t);
  }, []);

  const createAssignment = async () => {
    if (!newTitle.trim()) return;
    setCreating(true);
    try {
      const result = await api("/assignments", {
        method: "POST",
        body: JSON.stringify({
          title:    newTitle.trim(),
          deadline: newDeadline ? new Date(newDeadline).toISOString() : null,
        }),
      });
      setAssignments(prev => [...prev, result]);
      setShowCreate(false); setNewTitle(""); setNewDeadline("");
      showToast(`Assignment #${result.assignment_id} created!`);
    } catch (err) { showToast(err.message, "error"); }
    setCreating(false);
  };

  const saveDeadline = async (id) => {
    if (!editDeadline) return;
    try {
      const result = await api(`/assignments/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ deadline: new Date(editDeadline).toISOString() }),
      });
      setAssignments(prev => prev.map(a => a.id === id ? { ...a, ...result } : a));
      setEditingId(null); setEditDeadline("");
      showToast("Deadline updated — plagiarism check rescheduled!");
    } catch (err) { showToast(err.message, "error"); }
  };

  const deleteAssignment = async (id) => {
    try {
      await api(`/assignments/${id}`, { method: "DELETE" });
      setAssignments(prev => prev.filter(a => a.id !== id));
      showToast("Assignment deleted");
    } catch (err) { showToast(err.message, "error"); }
  };

  const statusBadge = (a) => {
    if (a.status === "checked") return <Badge label="✓ Results Ready" color="green" />;
    if (a.status === "closed")  return <Badge label="⚙ Processing…"  color="amber" />;
    if (!a.is_open)             return <Badge label="Deadline Passed" color="red"   />;
    return <Badge label="Open for Submissions" color="blue" />;
  };

  const overviewStats = [
    { label: "Assignments",    value: assignments.length,                                                          icon: "📋", color: "#6366f1" },
    { label: "Submissions",    value: submissions.length,                                                          icon: "📝", color: "#22c55e" },
    { label: "High Risk",      value: submissions.filter(s => (s.plagiarism_percentage ?? 0) >= 75).length,        icon: "⚠️", color: "#ef4444" },
    { label: "Pending Check",  value: submissions.filter(s => s.plagiarism_percentage === null).length,            icon: "⏳", color: "#f59e0b" },
  ];

  const barData = assignments.map(a => {
    const subs = submissions.filter(s => s.assignment_id === a.id && s.plagiarism_percentage !== null);
    return {
      name: a.title.split(" ").slice(0, 2).join(" "),
      avg:  subs.length ? Math.round(subs.reduce((acc, s) => acc + s.plagiarism_percentage, 0) / subs.length) : 0,
    };
  });

  const styles = {
    page:   { minHeight: "100vh", background: "#050a14", fontFamily: "'DM Sans', sans-serif", color: "#e2e8f0" },
    sidebar:{ width: 220, background: "rgba(15,23,42,0.98)", borderRight: "1px solid #1e293b", display: "flex", flexDirection: "column", padding: "24px 0", position: "fixed", top: 0, left: 0, height: "100vh" },
    main:   { marginLeft: 220, padding: 32 },
    card:   { background: "rgba(15,23,42,0.8)", border: "1px solid #1e293b", borderRadius: 16, padding: 24 },
    navBtn: (active) => ({ display: "flex", alignItems: "center", gap: 10, padding: "11px 20px", margin: "2px 12px", borderRadius: 10, border: "none", cursor: "pointer", fontSize: 14, fontWeight: 500, fontFamily: "'DM Sans', sans-serif", color: active ? "#e2e8f0" : "#64748b", background: active ? "rgba(99,102,241,0.15)" : "transparent" }),
    input:  { background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8, padding: "10px 14px", color: "#e2e8f0", fontSize: 14, outline: "none", fontFamily: "'DM Sans', sans-serif", width: "100%", boxSizing: "border-box" },
  };

  return (
    <div style={styles.page}>
      <div style={styles.sidebar}>
        <div style={{ padding: "0 20px 24px", borderBottom: "1px solid #1e293b" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
            <div style={{ width: 30, height: 30, background: "linear-gradient(135deg, #6366f1, #8b5cf6)", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center" }}>⬡</div>
            <span style={{ fontWeight: 700, fontSize: 16 }}>EduCheck</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 34, height: 34, borderRadius: "50%", background: "linear-gradient(135deg, #6366f1, #8b5cf6)", display: "flex", alignItems: "center", justifyContent: "center" }}>👨‍🏫</div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{user.email?.split("@")[0]}</div>
              <div style={{ fontSize: 11, color: "#6366f1" }}>Teacher</div>
            </div>
          </div>
        </div>
        <nav style={{ flex: 1, paddingTop: 12 }}>
          {[["overview","📊","Overview"],["assignments","📋","Assignments"],["submissions","📝","Submissions"],["analytics","📈","Analytics"]].map(([id,icon,label]) => (
            <button key={id} onClick={() => setTab(id)} style={styles.navBtn(tab === id)}>{icon} {label}</button>
          ))}
        </nav>
        <button onClick={onLogout} style={{ ...styles.navBtn(false), margin: "0 12px 16px", color: "#ef4444" }}>🚪 Sign Out</button>
      </div>

      <div style={styles.main}>
        {toast && (
          <div style={{ position: "fixed", top: 24, right: 24, background: toast.type === "success" ? "rgba(34,197,94,0.15)" : "rgba(239,68,68,0.15)", border: `1px solid ${toast.type === "success" ? "rgba(34,197,94,0.4)" : "rgba(239,68,68,0.4)"}`, borderRadius: 12, padding: "12px 20px", color: toast.type === "success" ? "#86efac" : "#fca5a5", fontSize: 14, fontWeight: 500, zIndex: 999 }}>
            {toast.msg}
          </div>
        )}
        {loading && <div style={{ textAlign: "center", padding: 60, color: "#64748b" }}>Loading…</div>}

        {/* ── Overview ── */}
        {!loading && tab === "overview" && (
          <div>
            <h1 style={{ fontSize: 26, fontWeight: 700, marginBottom: 6 }}>Dashboard</h1>
            <p style={{ color: "#64748b", marginBottom: 28, fontSize: 14 }}>Your classroom at a glance</p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 28 }}>
              {overviewStats.map(s => (
                <div key={s.label} style={{ ...styles.card, padding: 20 }}>
                  <div style={{ fontSize: 24, marginBottom: 8 }}>{s.icon}</div>
                  <div style={{ fontSize: 32, fontWeight: 700, color: s.color, fontFamily: "'Space Mono', monospace" }}>{s.value}</div>
                  <div style={{ fontSize: 13, color: "#64748b", marginTop: 2 }}>{s.label}</div>
                </div>
              ))}
            </div>
            <div style={styles.card}>
              <h3 style={{ margin: "0 0 16px", fontSize: 15, fontWeight: 600 }}>Recent Submissions</h3>
              {submissions.slice(0, 5).map(s => {
                const a = assignments.find(a => a.id === s.assignment_id);
                return (
                  <div key={s.id} style={{ display: "flex", alignItems: "center", padding: "12px 16px", background: "#0f172a", borderRadius: 10, gap: 16, marginBottom: 8 }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 14, fontWeight: 500 }}>Student #{s.student_id}</div>
                      <div style={{ fontSize: 12, color: "#64748b" }}>{a?.title || `Assignment #${s.assignment_id}`}</div>
                    </div>
                    {s.plagiarism_percentage !== null && s.plagiarism_percentage !== undefined
                      ? <span style={{ color: getScoreColor(s.plagiarism_percentage), fontWeight: 700, fontFamily: "'Space Mono', monospace" }}>{s.plagiarism_percentage.toFixed(1)}%</span>
                      : <Badge label="⏳ Pending" color="slate" />
                    }
                  </div>
                );
              })}
              {submissions.length === 0 && <div style={{ color: "#475569", textAlign: "center", padding: 24 }}>No submissions yet</div>}
            </div>
          </div>
        )}

        {/* ── Assignments ── */}
        {!loading && tab === "assignments" && (
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
              <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>Assignments</h1>
              <button onClick={() => setShowCreate(true)} style={{ background: "linear-gradient(135deg, #6366f1, #8b5cf6)", color: "white", border: "none", borderRadius: 10, padding: "10px 20px", fontSize: 14, fontWeight: 600, cursor: "pointer", fontFamily: "'DM Sans', sans-serif" }}>+ New Assignment</button>
            </div>

            {showCreate && (
              <div style={{ ...styles.card, marginBottom: 20, border: "1px solid rgba(99,102,241,0.3)" }}>
                <h3 style={{ margin: "0 0 8px", color: "#a5b4fc", fontSize: 15 }}>New Assignment</h3>
                <p style={{ color: "#64748b", fontSize: 13, marginBottom: 14 }}>Set a deadline — the plagiarism check will run automatically once it expires.</p>
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <input value={newTitle} onChange={e => setNewTitle(e.target.value)} onKeyDown={e => e.key === "Enter" && createAssignment()} placeholder="Assignment title…" style={styles.input} />
                  <div>
                    <label style={{ color: "#94a3b8", fontSize: 12, fontWeight: 600, display: "block", marginBottom: 6, textTransform: "uppercase" }}>Deadline (optional)</label>
                    <input type="datetime-local" value={newDeadline} onChange={e => setNewDeadline(e.target.value)} style={{ ...styles.input, colorScheme: "dark" }} />
                  </div>
                  <div style={{ display: "flex", gap: 10 }}>
                    <button onClick={createAssignment} disabled={creating || !newTitle.trim()} style={{ background: creating ? "#1e293b" : "linear-gradient(135deg, #6366f1, #8b5cf6)", color: creating ? "#64748b" : "white", border: "none", borderRadius: 8, padding: "10px 22px", fontSize: 14, fontWeight: 600, cursor: "pointer", fontFamily: "'DM Sans', sans-serif" }}>{creating ? "Creating…" : "Create"}</button>
                    <button onClick={() => { setShowCreate(false); setNewTitle(""); setNewDeadline(""); }} style={{ background: "#1e293b", color: "#94a3b8", border: "none", borderRadius: 8, padding: "10px 16px", fontSize: 14, cursor: "pointer", fontFamily: "'DM Sans', sans-serif" }}>Cancel</button>
                  </div>
                </div>
              </div>
            )}

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              {assignments.map(a => {
                const subs        = submissions.filter(s => s.assignment_id === a.id);
                const checkedSubs = subs.filter(s => s.plagiarism_percentage !== null);
                return (
                  <div key={a.id} style={styles.card}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                      <span style={{ fontSize: 11, color: "#6366f1", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em" }}>Assignment #{a.id}</span>
                      <button onClick={() => deleteAssignment(a.id)} style={{ background: "none", border: "none", color: "#475569", cursor: "pointer", fontSize: 16 }}>✕</button>
                    </div>
                    <h3 style={{ margin: "0 0 8px", fontSize: 16, fontWeight: 600 }}>{a.title}</h3>

                    <div style={{ marginBottom: 10 }}>{statusBadge(a)}</div>

                    {/* Deadline display + edit */}
                    {a.deadline && editingId !== a.id && (
                      <div style={{ marginBottom: 10 }}>
                        <Countdown deadline={a.deadline} />
                        <button onClick={() => { setEditingId(a.id); setEditDeadline(""); }} style={{ marginLeft: 10, background: "none", border: "none", color: "#6366f1", fontSize: 12, cursor: "pointer", fontFamily: "'DM Sans', sans-serif", padding: 0 }}>✏️ Edit</button>
                      </div>
                    )}
                    {!a.deadline && editingId !== a.id && (
                      <div style={{ marginBottom: 10 }}>
                        <button onClick={() => { setEditingId(a.id); setEditDeadline(""); }} style={{ background: "none", border: "none", color: "#64748b", fontSize: 12, cursor: "pointer", fontFamily: "'DM Sans', sans-serif", padding: 0 }}>+ Set deadline</button>
                      </div>
                    )}
                    {editingId === a.id && (
                      <div style={{ marginBottom: 10, display: "flex", gap: 8, alignItems: "center" }}>
                        <input type="datetime-local" value={editDeadline} onChange={e => setEditDeadline(e.target.value)} style={{ ...styles.input, fontSize: 12, padding: "6px 10px", colorScheme: "dark", flex: 1 }} />
                        <button onClick={() => saveDeadline(a.id)} style={{ background: "linear-gradient(135deg, #6366f1, #8b5cf6)", color: "white", border: "none", borderRadius: 6, padding: "6px 12px", fontSize: 12, cursor: "pointer", fontFamily: "'DM Sans', sans-serif", whiteSpace: "nowrap" }}>Save</button>
                        <button onClick={() => setEditingId(null)} style={{ background: "#1e293b", color: "#94a3b8", border: "none", borderRadius: 6, padding: "6px 10px", fontSize: 12, cursor: "pointer", fontFamily: "'DM Sans', sans-serif" }}>✕</button>
                      </div>
                    )}

                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontSize: 13, color: "#64748b" }}>{subs.length} submitted · {checkedSubs.length} checked</span>
                      <button onClick={() => { setSelectedAssignment(a); setTab("submissions"); }} style={{ background: "rgba(99,102,241,0.15)", color: "#a5b4fc", border: "none", borderRadius: 8, padding: "7px 14px", fontSize: 13, cursor: "pointer", fontFamily: "'DM Sans', sans-serif" }}>View →</button>
                    </div>
                  </div>
                );
              })}
              {assignments.length === 0 && (
                <div style={{ ...styles.card, gridColumn: "span 2", textAlign: "center", padding: 60, color: "#475569" }}>
                  No assignments yet. Click "+ New Assignment" to get started.
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Submissions ── */}
        {!loading && tab === "submissions" && (
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
              <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>Submissions</h1>
              {selectedAssignment && <Badge label={selectedAssignment.title} color="blue" />}
            </div>
            <div style={{ display: "flex", gap: 8, marginBottom: 20, flexWrap: "wrap" }}>
              <button onClick={() => setSelectedAssignment(null)} style={{ background: !selectedAssignment ? "linear-gradient(135deg, #6366f1, #8b5cf6)" : "#1e293b", color: !selectedAssignment ? "white" : "#94a3b8", border: "none", borderRadius: 8, padding: "8px 16px", fontSize: 13, cursor: "pointer", fontFamily: "'DM Sans', sans-serif", fontWeight: 500 }}>All</button>
              {assignments.map(a => (
                <button key={a.id} onClick={() => setSelectedAssignment(a)} style={{ background: selectedAssignment?.id === a.id ? "linear-gradient(135deg, #6366f1, #8b5cf6)" : "#1e293b", color: selectedAssignment?.id === a.id ? "white" : "#94a3b8", border: "none", borderRadius: 8, padding: "8px 16px", fontSize: 13, cursor: "pointer", fontFamily: "'DM Sans', sans-serif", fontWeight: 500 }}>#{a.id} {a.title.split(" ").slice(0,2).join(" ")}</button>
              ))}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {(selectedAssignment ? submissions.filter(s => s.assignment_id === selectedAssignment.id) : submissions).map(s => {
                const a   = assignments.find(a => a.id === s.assignment_id);
                const pct = s.plagiarism_percentage;
                return (
                  <div key={s.id} style={styles.card}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 15 }}>Student #{s.student_id}</div>
                        <div style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>{a?.title} · Submission #{s.id}</div>
                        {s.submitted_at && <div style={{ fontSize: 11, color: "#475569", marginTop: 4 }}>Submitted: {new Date(s.submitted_at).toLocaleString()}</div>}
                        {s.checked_at   && <div style={{ fontSize: 11, color: "#475569" }}>Checked: {new Date(s.checked_at).toLocaleString()}</div>}
                      </div>
                      <ScoreGauge score={pct !== null && pct !== undefined ? Math.round(pct) : null} />
                    </div>
                  </div>
                );
              })}
              {submissions.length === 0 && <div style={{ ...styles.card, textAlign: "center", padding: 60, color: "#475569" }}>No submissions yet</div>}
            </div>
          </div>
        )}

        {/* ── Analytics ── */}
        {!loading && tab === "analytics" && (
          <div>
            <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 24 }}>Analytics</h1>
            <div style={styles.card}>
              <h3 style={{ margin: "0 0 20px", fontSize: 15, fontWeight: 600, color: "#94a3b8" }}>Avg Plagiarism by Assignment (checked submissions only)</h3>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={barData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="name" tick={{ fill: "#64748b", fontSize: 11 }} />
                  <YAxis tick={{ fill: "#64748b", fontSize: 11 }} domain={[0, 100]} />
                  <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8, color: "#e2e8f0" }} formatter={v => [`${v}%`, "Avg Score"]} />
                  <Bar dataKey="avg" radius={[6, 6, 0, 0]}>
                    {barData.map((d, i) => <Cell key={i} fill={getScoreColor(d.avg)} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── FILE HELPERS ─────────────────────────────────────────────────────────────
async function extractPdfText(file) {
  return new Promise((resolve, reject) => {
    const run = () => {
      const reader = new FileReader();
      reader.onload = async (e) => {
        try {
          const pdfjsLib = window["pdfjs-dist/build/pdf"];
          pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
          const pdf = await pdfjsLib.getDocument({ data: new Uint8Array(e.target.result) }).promise;
          let text = "";
          for (let i = 1; i <= pdf.numPages; i++) {
            const page = await pdf.getPage(i);
            const content = await page.getTextContent();
            text += content.items.map(item => item.str).join(" ") + "\n";
          }
          resolve(text.trim());
        } catch (err) { reject(err); }
      };
      reader.readAsArrayBuffer(file);
    };
    if (window["pdfjs-dist/build/pdf"]) { run(); return; }
    const s = document.createElement("script");
    s.src = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js";
    s.onload = run;
    s.onerror = () => reject(new Error("Failed to load PDF.js"));
    document.head.appendChild(s);
  });
}

async function extractFileText(file) {
  const ext = file.name.split(".").pop().toLowerCase();
  if (ext === "pdf") return extractPdfText(file);
  if (ext === "docx") {
    const buf = await file.arrayBuffer();
    const result = await mammoth.extractRawText({ arrayBuffer: buf });
    return result.value.trim();
  }
  if (ext === "txt") {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload  = (e) => resolve(e.target.result.trim());
      reader.onerror = () => reject(new Error("Failed to read file"));
      reader.readAsText(file);
    });
  }
  throw new Error("Unsupported file type. Use .pdf, .docx or .txt");
}

function FileDropZone({ onFileSelect, selectedFile, onClear }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);
  return (
    <div onDragOver={e => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)}
      onDrop={e => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) onFileSelect(f); }}
      onClick={() => !selectedFile && inputRef.current?.click()}
      style={{ border: `2px dashed ${dragging ? "#22c55e" : selectedFile ? "rgba(34,197,94,0.4)" : "#1e293b"}`, borderRadius: 12, padding: "24px 20px", textAlign: "center", cursor: selectedFile ? "default" : "pointer", background: dragging ? "rgba(34,197,94,0.05)" : "#0a111e" }}>
      <input ref={inputRef} type="file" accept=".pdf,.docx,.txt" style={{ display: "none" }} onChange={e => e.target.files[0] && onFileSelect(e.target.files[0])} />
      {selectedFile ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 12 }}>
          <span style={{ fontSize: 28 }}>{selectedFile.name.endsWith(".pdf") ? "📄" : selectedFile.name.endsWith(".txt") ? "📃" : "📝"}</span>
          <div style={{ textAlign: "left" }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: "#86efac" }}>{selectedFile.name}</div>
            <div style={{ fontSize: 12, color: "#64748b" }}>{(selectedFile.size / 1024).toFixed(1)} KB</div>
          </div>
          <button onClick={e => { e.stopPropagation(); onClear(); }} style={{ marginLeft: 8, background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.25)", borderRadius: 6, padding: "4px 10px", color: "#f87171", fontSize: 12, cursor: "pointer" }}>✕</button>
        </div>
      ) : (
        <div>
          <div style={{ fontSize: 32, marginBottom: 8 }}>📂</div>
          <div style={{ fontSize: 14, fontWeight: 600, color: "#94a3b8" }}>Drop your file or <span style={{ color: "#22c55e" }}>browse</span></div>
          <div style={{ fontSize: 12, color: "#475569", marginTop: 4 }}>PDF, DOCX or TXT</div>
        </div>
      )}
    </div>
  );
}

// ─── STUDENT DASHBOARD ────────────────────────────────────────────────────────
function StudentDashboard({ user, onLogout }) {
  const [tab, setTab]                       = useState("assignments");
  const [assignments, setAssignments]       = useState([]);
  const [mySubmissions, setMySubmissions]   = useState([]);
  const [submitting, setSubmitting]         = useState(null);
  const [texts, setTexts]                   = useState({});
  const [files, setFiles]                   = useState({});
  const [extractedTexts, setExtractedTexts] = useState({});
  const [modes, setModes]                   = useState({});
  const [toast, setToast]                   = useState(null);
  const [loading, setLoading]               = useState(true);

  const showToast = (msg, type = "success") => { setToast({ msg, type }); setTimeout(() => setToast(null), 4000); };

  useEffect(() => {
    Promise.all([api("/assignments"), api("/submissions/my")])
      .then(([a, s]) => { setAssignments(a); setMySubmissions(s); setLoading(false); })
      .catch(err => { showToast(err.message, "error"); setLoading(false); });

    // Poll every 30s — picks up results once deadline passes and check completes
    const t = setInterval(() => {
      api("/submissions/my").then(s => setMySubmissions(s)).catch(() => {});
      api("/assignments").then(a => setAssignments(a)).catch(() => {});
    }, 30000);
    return () => clearInterval(t);
  }, []);

  const submittedIds = new Set(mySubmissions.map(s => s.assignment_id));

  const handleFileSelect = async (assignmentId, file) => {
    setFiles(prev => ({ ...prev, [assignmentId]: file }));
    setExtractedTexts(prev => ({ ...prev, [assignmentId]: "" }));
    try {
      const text = await extractFileText(file);
      setExtractedTexts(prev => ({ ...prev, [assignmentId]: text }));
    } catch (err) { showToast(err.message, "error"); }
  };

  const handleSubmit = async (assignment) => {
    const mode      = modes[assignment.id] || "text";
    const finalText = mode === "text" ? (texts[assignment.id] || "") : (extractedTexts[assignment.id] || "");
    if (finalText.length < 30) return;
    setSubmitting(assignment.id);
    try {
      const result = await api("/submissions", {
        method: "POST",
        body: JSON.stringify({ assignment_id: assignment.id, text: finalText }),
      });
      setMySubmissions(prev => [...prev, {
        id:                    result.submission_id,
        assignment_id:         assignment.id,
        plagiarism_percentage: null,
        submitted_at:          new Date().toISOString(),
      }]);
      showToast("Submitted! ⏳ Results will appear automatically after the deadline passes.");
    } catch (err) { showToast(err.message, "error"); }
    setSubmitting(null);
  };

  const styles = {
    page:   { minHeight: "100vh", background: "#050a14", fontFamily: "'DM Sans', sans-serif", color: "#e2e8f0" },
    sidebar:{ width: 220, background: "rgba(15,23,42,0.98)", borderRight: "1px solid #1e293b", display: "flex", flexDirection: "column", padding: "24px 0", position: "fixed", top: 0, left: 0, height: "100vh" },
    main:   { marginLeft: 220, padding: 32 },
    card:   { background: "rgba(15,23,42,0.8)", border: "1px solid #1e293b", borderRadius: 16, padding: 24, marginBottom: 16 },
    navBtn: (active) => ({ display: "flex", alignItems: "center", gap: 10, padding: "11px 20px", margin: "2px 12px", borderRadius: 10, border: "none", cursor: "pointer", fontSize: 14, fontWeight: 500, fontFamily: "'DM Sans', sans-serif", color: active ? "#e2e8f0" : "#64748b", background: active ? "rgba(34,197,94,0.12)" : "transparent" }),
  };

  return (
    <div style={styles.page}>
      <div style={styles.sidebar}>
        <div style={{ padding: "0 20px 24px", borderBottom: "1px solid #1e293b" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
            <div style={{ width: 30, height: 30, background: "linear-gradient(135deg, #22c55e, #16a34a)", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center" }}>⬡</div>
            <span style={{ fontWeight: 700, fontSize: 16 }}>EduCheck</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 34, height: 34, borderRadius: "50%", background: "linear-gradient(135deg, #22c55e, #16a34a)", display: "flex", alignItems: "center", justifyContent: "center" }}>🎓</div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{user.email?.split("@")[0]}</div>
              <div style={{ fontSize: 11, color: "#22c55e" }}>Student</div>
            </div>
          </div>
        </div>
        <nav style={{ flex: 1, paddingTop: 12 }}>
          {[["assignments","📋","Assignments"],["mywork","📝","My Submissions"]].map(([id,icon,label]) => (
            <button key={id} onClick={() => setTab(id)} style={styles.navBtn(tab === id)}>{icon} {label}</button>
          ))}
        </nav>
        <button onClick={onLogout} style={{ ...styles.navBtn(false), margin: "0 12px 16px", color: "#ef4444" }}>🚪 Sign Out</button>
      </div>

      <div style={styles.main}>
        {toast && (
          <div style={{ position: "fixed", top: 24, right: 24, background: toast.type === "success" ? "rgba(34,197,94,0.15)" : "rgba(239,68,68,0.15)", border: `1px solid ${toast.type === "success" ? "rgba(34,197,94,0.4)" : "rgba(239,68,68,0.4)"}`, borderRadius: 12, padding: "12px 20px", color: toast.type === "success" ? "#86efac" : "#fca5a5", fontSize: 14, fontWeight: 500, zIndex: 999 }}>
            {toast.msg}
          </div>
        )}
        {loading && <div style={{ textAlign: "center", padding: 60, color: "#64748b" }}>Loading…</div>}

        {!loading && tab === "assignments" && (
          <div>
            <h1 style={{ fontSize: 26, fontWeight: 700, marginBottom: 6 }}>Assignments</h1>
            <p style={{ color: "#64748b", marginBottom: 28, fontSize: 14 }}>
              {assignments.filter(a => a.is_open && !submittedIds.has(a.id)).length} pending · {submittedIds.size} submitted
            </p>

            {assignments.map(a => {
              const isSubmitted  = submittedIds.has(a.id);
              const isOpen       = a.is_open;
              const mode         = modes[a.id] || "text";
              const myResult     = mySubmissions.find(s => s.assignment_id === a.id);
              const isSubmitting = submitting === a.id;
              const finalText    = mode === "text" ? (texts[a.id] || "") : (extractedTexts[a.id] || "");
              const isPending    = isSubmitted && (myResult?.plagiarism_percentage === null || myResult?.plagiarism_percentage === undefined);

              return (
                <div key={a.id} style={{ ...styles.card, border: isSubmitted ? "1px solid rgba(34,197,94,0.2)" : !isOpen ? "1px solid rgba(239,68,68,0.15)" : "1px solid #1e293b" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 6 }}>
                        <span style={{ fontSize: 11, color: "#6366f1", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em" }}>Assignment #{a.id}</span>
                        {isSubmitted && isPending   && <Badge label="⏳ Results Pending" color="amber" />}
                        {isSubmitted && !isPending  && <Badge label="✓ Checked" color="green" />}
                        {!isSubmitted && isOpen     && <Badge label="Open" color="blue" />}
                        {!isSubmitted && !isOpen    && <Badge label="Closed" color="red" />}
                      </div>
                      <h3 style={{ margin: "0 0 8px", fontSize: 18, fontWeight: 700 }}>{a.title}</h3>
                      {a.deadline && <Countdown deadline={a.deadline} />}
                    </div>

                    {/* Score display */}
                    {isSubmitted && !isPending && myResult?.plagiarism_percentage !== null && (
                      <div style={{ textAlign: "right", marginLeft: 20 }}>
                        <div style={{ fontSize: 12, color: "#64748b", marginBottom: 4 }}>Your Score</div>
                        <div style={{ fontSize: 26, fontWeight: 700, color: getScoreColor(myResult.plagiarism_percentage), fontFamily: "'Space Mono', monospace" }}>
                          {myResult.plagiarism_percentage.toFixed(1)}%
                        </div>
                        <Badge label={getScoreLabel(myResult.plagiarism_percentage)} color={myResult.plagiarism_percentage < 25 ? "green" : myResult.plagiarism_percentage < 75 ? "amber" : "red"} />
                      </div>
                    )}

                    {/* Pending box */}
                    {isPending && (
                      <div style={{ marginLeft: 20, textAlign: "center", background: "rgba(245,158,11,0.08)", border: "1px solid rgba(245,158,11,0.2)", borderRadius: 10, padding: "12px 18px" }}>
                        <div style={{ fontSize: 26 }}>⏳</div>
                        <div style={{ fontSize: 11, color: "#fcd34d", marginTop: 4 }}>Results after deadline</div>
                      </div>
                    )}
                  </div>

                  {/* Submit form */}
                  {!isSubmitted && isOpen && (
                    <div>
                      <div style={{ display: "flex", background: "#0a111e", borderRadius: 10, padding: 3, marginBottom: 14, border: "1px solid #1e293b", width: "fit-content" }}>
                        {[["text","✏️ Write Text"],["file","📎 Upload File"]].map(([m, label]) => (
                          <button key={m} onClick={() => setModes(prev => ({ ...prev, [a.id]: m }))} style={{ padding: "8px 16px", borderRadius: 8, border: "none", cursor: "pointer", fontSize: 13, fontWeight: 600, fontFamily: "'DM Sans', sans-serif", background: mode === m ? "linear-gradient(135deg, #22c55e, #16a34a)" : "transparent", color: mode === m ? "white" : "#64748b" }}>{label}</button>
                        ))}
                      </div>

                      {mode === "text" && (
                        <textarea value={texts[a.id] || ""} onChange={e => setTexts(prev => ({ ...prev, [a.id]: e.target.value }))} placeholder="Write your assignment here… (min 30 characters)" rows={5} style={{ width: "100%", background: "#0f172a", border: "1px solid #1e293b", borderRadius: 10, padding: "12px 16px", color: "#e2e8f0", fontSize: 14, outline: "none", resize: "vertical", boxSizing: "border-box", fontFamily: "'DM Sans', sans-serif" }} />
                      )}
                      {mode === "file" && (
                        <div>
                          <FileDropZone onFileSelect={f => handleFileSelect(a.id, f)} selectedFile={files[a.id]} onClear={() => { setFiles(prev => ({ ...prev, [a.id]: null })); setExtractedTexts(prev => ({ ...prev, [a.id]: "" })); }} />
                          {extractedTexts[a.id] && <div style={{ marginTop: 10, background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8, padding: "10px 14px", fontSize: 13, color: "#94a3b8" }}>{extractedTexts[a.id].substring(0, 300)}…</div>}
                        </div>
                      )}

                      <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}>
                        <button onClick={() => handleSubmit(a)} disabled={finalText.length < 30 || isSubmitting} style={{ background: finalText.length >= 30 && !isSubmitting ? "linear-gradient(135deg, #22c55e, #16a34a)" : "#1e293b", color: finalText.length >= 30 && !isSubmitting ? "white" : "#475569", border: "none", borderRadius: 10, padding: "11px 28px", fontSize: 14, fontWeight: 700, cursor: "pointer", fontFamily: "'DM Sans', sans-serif" }}>
                          {isSubmitting ? "Submitting…" : "Submit →"}
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Closed, not submitted */}
                  {!isSubmitted && !isOpen && (
                    <div style={{ textAlign: "center", padding: "16px 0", color: "#475569", fontSize: 14 }}>
                      🔒 Submission closed — deadline has passed
                    </div>
                  )}
                </div>
              );
            })}

            {assignments.length === 0 && (
              <div style={{ background: "rgba(15,23,42,0.8)", border: "1px solid #1e293b", borderRadius: 16, padding: 24, textAlign: "center", padding: 60, color: "#475569" }}>
                No assignments yet. Check back later.
              </div>
            )}
          </div>
        )}

        {!loading && tab === "mywork" && (
          <div>
            <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 24 }}>My Submissions</h1>
            {mySubmissions.length === 0 ? (
              <div style={{ ...styles.card, textAlign: "center", padding: 60 }}>
                <div style={{ fontSize: 48, marginBottom: 12 }}>📭</div>
                <div style={{ color: "#64748b" }}>No submissions yet</div>
              </div>
            ) : mySubmissions.map(s => {
              const a   = assignments.find(a => a.id === s.assignment_id);
              const pct = s.plagiarism_percentage;
              return (
                <div key={s.id} style={styles.card}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div>
                      <h3 style={{ margin: "0 0 4px", fontSize: 16, fontWeight: 600 }}>{a?.title || `Assignment #${s.assignment_id}`}</h3>
                      <div style={{ fontSize: 12, color: "#64748b" }}>Submission #{s.id}</div>
                      {s.submitted_at && <div style={{ fontSize: 11, color: "#475569", marginTop: 4 }}>Submitted: {new Date(s.submitted_at).toLocaleString()}</div>}
                    </div>
                    <div style={{ textAlign: "right" }}>
                      {pct !== null && pct !== undefined ? (
                        <>
                          <div style={{ fontSize: 26, fontWeight: 700, color: getScoreColor(pct), fontFamily: "'Space Mono', monospace" }}>{pct.toFixed(1)}%</div>
                          <Badge label={getScoreLabel(pct)} color={pct < 25 ? "green" : pct < 75 ? "amber" : "red"} />
                        </>
                      ) : (
                        <div style={{ textAlign: "center" }}>
                          <div style={{ fontSize: 28 }}>⏳</div>
                          <div style={{ fontSize: 12, color: "#64748b", marginTop: 4 }}>Results pending</div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── ROOT APP ─────────────────────────────────────────────────────────────────
function useApp() {
  const [user, setUser]             = useState(null);
  const [googlePending, setPending] = useState(null);
  const [loading, setLoading]       = useState(true);

  useEffect(() => {
    (async () => {
      if (window.location.pathname === "/auth/callback") {
        const result = await handleGoogleCallback();
        if (result?.role) setUser(result);
        else if (result?.uid) setPending(result);
        window.history.replaceState({}, "", "/");
        setLoading(false);
        return;
      }
      const stored = getStoredUser();
      if (stored) setUser(stored);
      setLoading(false);
    
      supabase.auth.onAuthStateChange((event, session) => {
  if (session?.access_token) {
    localStorage.setItem("access_token", session.access_token);
  }
});
    })();
  }, []);

  const handleLogin    = (u)    => setUser(u);
  const handleLogout   = ()     => { logout(); setUser(null); };
  const handleRolePick = async (role) => {
    await setGoogleRole(googlePending.uid, googlePending.email, role, googlePending.token);
    setUser({ uid: googlePending.uid, email: googlePending.email, role });
    setPending(null);
  };

  return { user, loading, googlePending, handleLogin, handleLogout, handleRolePick };
}

export default function App() {
  const { user, loading, googlePending, handleLogin, handleLogout, handleRolePick } = useApp();

  if (loading) return (
    <div style={{ minHeight: "100vh", background: "#050a14", display: "flex", alignItems: "center", justifyContent: "center", color: "#64748b", fontFamily: "DM Sans, sans-serif" }}>
      Loading...
    </div>
  );

  if (googlePending) return <RolePicker onPick={handleRolePick} />;
  if (!user) return <AuthScreen onLogin={handleLogin} />;
  if (user.role === "teacher") return <TeacherDashboard user={user} onLogout={handleLogout} />;
  return <StudentDashboard user={user} onLogout={handleLogout} />;
}