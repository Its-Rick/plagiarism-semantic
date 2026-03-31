/**
 * AcademicCheckPanel.jsx
 * ──────────────────────
 * Drop this component inside App.jsx — add it to the Student Dashboard
 * as a new tab, or use it standalone.
 *
 * Shows:
 *   - Text input with file support
 *   - Overall similarity score
 *   - Highlighted output with source tooltips
 *   - Source cards listing matched papers
 */

import { useState, useEffect, useRef } from "react";
import { highlightPlagiarism, injectHighlightStyles } from "./AcademicHighlighter";

// ── helpers ──────────────────────────────────────────────────────────────────
async function api(path, options = {}) {
  const token = localStorage.getItem("access_token");
  const res = await fetch(`/api${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return res.json();
}

const getScoreColor = (pct) => {
  if (pct >= 75) return "#ef4444";
  if (pct >= 50) return "#f97316";
  if (pct >= 25) return "#f59e0b";
  return "#22c55e";
};

const getScoreLabel = (pct) => {
  if (pct >= 75) return "High Risk";
  if (pct >= 50) return "Suspicious";
  if (pct >= 25) return "Low Risk";
  return "Original";
};

// ── Score arc gauge ───────────────────────────────────────────────────────────
function ScoreGauge({ score }) {
  const r = 54, cx = 70, cy = 70;
  const circumference = 2 * Math.PI * r;
  const filled = (score / 100) * circumference;
  const color  = getScoreColor(score);
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

// ── Source card ───────────────────────────────────────────────────────────────
function SourceCard({ seg }) {
  const { source, similarity_pct, text } = seg;
  const color = getScoreColor(similarity_pct);
  return (
    <div style={{
      background: "#0a111e", border: `1px solid ${color}33`,
      borderLeft: `3px solid ${color}`, borderRadius: 10,
      padding: "12px 16px", marginBottom: 10,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ fontSize: 12, color, fontWeight: 700, fontFamily: "monospace" }}>
          {similarity_pct}% similar
        </span>
        <span style={{ fontSize: 11, color: "#475569" }}>
          {source.source === "arxiv" ? "ArXiv" : "Semantic Scholar"}
          {source.year ? ` · ${source.year}` : ""}
        </span>
      </div>
      <div style={{ fontSize: 13, color: "#e2e8f0", fontWeight: 600, marginBottom: 4, lineHeight: 1.4 }}>
        {source.title}
      </div>
      {source.authors?.length > 0 && (
        <div style={{ fontSize: 12, color: "#64748b", marginBottom: 6 }}>
          {source.authors.join(", ")}
        </div>
      )}
      <div style={{ fontSize: 12, color: "#94a3b8", fontStyle: "italic",
        background: "#0f172a", borderRadius: 6, padding: "6px 10px",
        borderLeft: "2px solid #1e293b", marginBottom: 8, lineHeight: 1.5 }}>
        "{text}"
      </div>
      {source.url && (
        <a href={source.url} target="_blank" rel="noopener"
          style={{ fontSize: 12, color: "#60a5fa", textDecoration: "none" }}>
          View paper →
        </a>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function AcademicCheckPanel() {
  const [text, setText]         = useState("");
  const [threshold, setThresh]  = useState(0.75);
  const [loading, setLoading]   = useState(false);
  const [result, setResult]     = useState(null);
  const [error, setError]       = useState("");
  const [tab, setTab]           = useState("highlighted"); // "highlighted" | "sources"
  const highlightRef            = useRef(null);
 
  useEffect(() => { injectHighlightStyles(); }, []);
 
  // Inject highlighted HTML when result arrives
  useEffect(() => {
    if (result && highlightRef.current) {
      highlightRef.current.innerHTML = highlightPlagiarism(text, result);
    }
  }, [result, text]);
 
  const run = async () => {
    if (text.trim().length < 50) {
      setError("Please enter at least 50 characters.");
      return;
    }
    setError(""); setLoading(true); setResult(null);
    try {
      const data = await api("/academic-check", {
        method: "POST",
        body: JSON.stringify({ text: text.trim(), threshold }),
      });
      setResult(data);
    } catch (e) {
      setError(e.message);
    }
    setLoading(false);
  };
 
  const card   = { background: "rgba(15,23,42,0.8)", border: "1px solid #1e293b",
                   borderRadius: 16, padding: 24, marginBottom: 20 };
  const input  = { width: "100%", background: "#0f172a", border: "1px solid #1e293b",
                   borderRadius: 10, padding: "12px 16px", color: "#e2e8f0", fontSize: 14,
                   outline: "none", resize: "vertical", fontFamily: "'DM Sans', sans-serif",
                   boxSizing: "border-box" };
  const btn    = (active) => ({
    padding: "10px 20px", borderRadius: 10, border: "none", cursor: "pointer",
    fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600,
    background: active ? "linear-gradient(135deg, #6366f1, #8b5cf6)" : "#1e293b",
    color: active ? "white" : "#94a3b8",
  });
 
  return (
    <div style={{ fontFamily: "'DM Sans', sans-serif", color: "#e2e8f0" }}>
      <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 6 }}>
        🎓 Academic Plagiarism Check
      </h2>
      <p style={{ color: "#64748b", fontSize: 14, marginBottom: 24 }}>
        Checks your text against millions of research papers via Semantic Scholar and ArXiv.
      </p>
 
      {/* Input card */}
      <div style={card}>
        <textarea
          value={text}
          onChange={e => setText(e.target.value)}
          placeholder="Paste your text here (minimum 50 characters)…"
          rows={8}
          style={input}
        />
 
        <div style={{ display: "flex", alignItems: "center", gap: 20, marginTop: 14,
          flexWrap: "wrap" }}>
          {/* Threshold slider */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1 }}>
            <label style={{ fontSize: 13, color: "#94a3b8", whiteSpace: "nowrap" }}>
              Threshold:
            </label>
            <input type="range" min={0.5} max={0.95} step={0.05}
              value={threshold}
              onChange={e => setThresh(parseFloat(e.target.value))}
              style={{ flex: 1 }}
            />
            <span style={{ fontSize: 13, color: "#f59e0b", fontFamily: "monospace",
              minWidth: 36 }}>
              {Math.round(threshold * 100)}%
            </span>
          </div>
 
          <button
            onClick={run}
            disabled={loading || text.trim().length < 50}
            style={{
              background: loading || text.trim().length < 50
                ? "#1e293b"
                : "linear-gradient(135deg, #6366f1, #8b5cf6)",
              color: loading || text.trim().length < 50 ? "#475569" : "white",
              border: "none", borderRadius: 10, padding: "11px 28px",
              fontSize: 14, fontWeight: 700, cursor: "pointer",
              fontFamily: "'DM Sans', sans-serif",
            }}
          >
            {loading ? "Checking…" : "Check Against Papers →"}
          </button>
        </div>
 
        {loading && (
          <div style={{ marginTop: 16, padding: "12px 16px", background: "#0a111e",
            borderRadius: 10, border: "1px solid #1e293b", fontSize: 13, color: "#64748b" }}>
            <span style={{ color: "#6366f1" }}>⟳</span> Querying Semantic Scholar &amp; ArXiv
            simultaneously… This takes 5–15 seconds.
          </div>
        )}
 
        {error && (
          <div style={{ marginTop: 12, padding: "10px 14px",
            background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)",
            borderRadius: 8, color: "#f87171", fontSize: 13 }}>
            {error}
          </div>
        )}
      </div>
 
      {/* Results */}
      {result && (
        <>
          {/* Summary row */}
          <div style={{ display: "grid", gridTemplateColumns: "auto 1fr 1fr 1fr",
            gap: 16, marginBottom: 20 }}>
            <div style={{ ...card, padding: "16px 20px", marginBottom: 0,
              display: "flex", alignItems: "center" }}>
              <ScoreGauge score={result.overall_similarity_pct} />
            </div>
            {[
              { label: "Matches Found",    value: result.matched_segments.length, color: getScoreColor(result.overall_similarity_pct) },
              { label: "Papers Searched",  value: result.sources_checked,         color: "#6366f1" },
              { label: "Time Taken",       value: `${result.elapsed_seconds}s`,   color: "#22c55e" },
            ].map(s => (
              <div key={s.label} style={{ ...card, padding: "16px 20px", marginBottom: 0 }}>
                <div style={{ fontSize: 26, fontWeight: 700, color: s.color,
                  fontFamily: "monospace" }}>{s.value}</div>
                <div style={{ fontSize: 12, color: "#64748b", marginTop: 4 }}>{s.label}</div>
              </div>
            ))}
          </div>
 
          {/* Tab switcher */}
          <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
            <button onClick={() => setTab("highlighted")} style={btn(tab === "highlighted")}>
              🖊 Highlighted Text
            </button>
            <button onClick={() => setTab("sources")} style={btn(tab === "sources")}>
              📚 Sources ({result.matched_segments.length})
            </button>
          </div>
 
          {/* Highlighted text */}
          {tab === "highlighted" && (
            <div style={card}>
              <div style={{ fontSize: 12, color: "#64748b", marginBottom: 12,
                display: "flex", gap: 16, flexWrap: "wrap" }}>
                {[
                  { color: "#ef4444", label: "≥90% similar" },
                  { color: "#f97316", label: "≥75% similar" },
                  { color: "#f59e0b", label: "≥60% similar" },
                  { color: "#eab308", label: "≥threshold" },
                ].map(l => (
                  <span key={l.label} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ width: 12, height: 12, borderRadius: 2, display: "inline-block",
                      background: l.color + "44", border: `2px solid ${l.color}` }} />
                    {l.label}
                  </span>
                ))}
                <span style={{ color: "#475569" }}>· Hover highlighted text for source</span>
              </div>
              <div
                ref={highlightRef}
                style={{ fontSize: 14, lineHeight: 1.8, color: "#cbd5e1",
                  background: "#0a111e", borderRadius: 10, padding: "16px 18px",
                  whiteSpace: "pre-wrap", border: "1px solid #1e293b" }}
              />
            </div>
          )}
 
          {/* Sources list */}
          {tab === "sources" && (
            <div style={card}>
              {result.matched_segments.length === 0 ? (
                <div style={{ textAlign: "center", padding: 40, color: "#475569" }}>
                  <div style={{ fontSize: 32, marginBottom: 8 }}>✅</div>
                  No significant matches found against academic papers.
                </div>
              ) : (
                result.matched_segments
                  .sort((a, b) => b.similarity_pct - a.similarity_pct)
                  .map((seg, i) => <SourceCard key={i} seg={seg} />)
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}