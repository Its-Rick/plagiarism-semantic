/**
 * AcademicCheckPanel.jsx — EduCheck v2
 * ─────────────────────────────────────
 * Academic plagiarism check supporting:
 *   · Paste text directly
 *   · Upload .pdf, .docx, or .txt file
 *
 * Endpoints used:
 *   POST /api/academic-check        → JSON body { text, threshold }
 *   POST /api/academic-check/file   → multipart/form-data { file, threshold }
 */

import { useState, useEffect, useRef } from "react";
import { highlightPlagiarism, injectHighlightStyles } from "./AcademicHighlighter";

// ── API helpers ───────────────────────────────────────────────────────────────

function authHeaders(extra = {}) {
  const token = localStorage.getItem("access_token");
  return token ? { Authorization: `Bearer ${token}`, ...extra } : extra;
}

async function apiJson(path, options = {}) {
  const res = await fetch(`/api${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...authHeaders(), ...(options.headers || {}) },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return res.json();
}

async function apiFile(path, formData) {
  const res = await fetch(`/api${path}`, {
    method: "POST",
    headers: authHeaders(),   // NO Content-Type — browser sets multipart boundary
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return res.json();
}

// ── Color helpers ─────────────────────────────────────────────────────────────

const scoreColor = (pct) => {
  if (pct >= 75) return "#ef4444";
  if (pct >= 50) return "#f97316";
  if (pct >= 25) return "#f59e0b";
  return "#22c55e";
};
const scoreLabel = (pct) => {
  if (pct >= 75) return "High Risk";
  if (pct >= 50) return "Suspicious";
  if (pct >= 25) return "Low Risk";
  return "Original";
};

const FILE_ICONS = { pdf: "📄", docx: "📝", txt: "📃" };
const fileExt    = (name = "") => (name.split(".").pop() || "").toLowerCase();

// ── Score Gauge ───────────────────────────────────────────────────────────────
function ScoreGauge({ score }) {
  const r = 54, cx = 70, cy = 70;
  const circ   = 2 * Math.PI * r;
  const filled = (score / 100) * circ;
  const color  = scoreColor(score);
  return (
    <svg width="140" height="100" viewBox="0 0 140 100">
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="#1e293b" strokeWidth="10"
        strokeDasharray={`${circ * 0.75} ${circ * 0.25}`} strokeLinecap="round"
        transform={`rotate(135 ${cx} ${cy})`} />
      <circle cx={cx} cy={cy} r={r} fill="none" stroke={color} strokeWidth="10"
        strokeDasharray={`${filled * 0.75} ${circ}`} strokeLinecap="round"
        transform={`rotate(135 ${cx} ${cy})`}
        style={{ transition: "stroke-dasharray 1s ease" }} />
      <text x={cx} y={cy - 4} textAnchor="middle" fill={color} fontSize="22" fontWeight="700">{score}%</text>
      <text x={cx} y={cy + 14} textAnchor="middle" fill="#94a3b8" fontSize="10">{scoreLabel(score)}</text>
    </svg>
  );
}

// ── Score breakdown bar ───────────────────────────────────────────────────────
function BreakdownBar({ sem, fp }) {
  if (sem == null) return null;
  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ fontSize: 11, color: "#64748b", marginBottom: 4, display: "flex", justifyContent: "space-between" }}>
        <span>Score breakdown</span>
        <span style={{ fontFamily: "monospace" }}>Semantic {sem}% · Fingerprint {fp}%</span>
      </div>
      <div style={{ display: "flex", height: 6, borderRadius: 4, overflow: "hidden", background: "#1e293b" }}>
        <div style={{ width: `${(sem / 100) * 60}%`, background: "linear-gradient(90deg,#6366f1,#8b5cf6)", transition: "width .8s ease" }} />
        <div style={{ width: `${(fp  / 100) * 40}%`, background: "linear-gradient(90deg,#f59e0b,#ef4444)", transition: "width .8s ease" }} />
      </div>
      <div style={{ display: "flex", gap: 12, marginTop: 4 }}>
        {[["#8b5cf6","Semantic (BERT)"],["#f59e0b","Fingerprint (shingle)"]].map(([c,l]) => (
          <span key={l} style={{ fontSize: 10, color: "#64748b", display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: c, display: "inline-block" }} />{l}
          </span>
        ))}
      </div>
    </div>
  );
}

// ── Source match card ─────────────────────────────────────────────────────────
function SourceCard({ seg }) {
  const { source, similarity_pct, semantic_score, exact_score, text } = seg;
  const color = scoreColor(similarity_pct);
  const badges = [];
  if (semantic_score >= 50) badges.push(["BERT",    "#8b5cf6"]);
  if (exact_score    >= 20) badges.push(["SHINGLE", "#f59e0b"]);
  if (!badges.length)       badges.push(["HYBRID",  "#6366f1"]);

  const srcName = source?.source === "arXiv" ? "arXiv"
                : source?.source === "OpenAlex" ? "OpenAlex"
                : source?.source === "GitHub"   ? "GitHub"
                : source?.source || "Source";

  return (
    <div style={{ background: "#0a111e", border: `1px solid ${color}33`, borderLeft: `3px solid ${color}`, borderRadius: 10, padding: "12px 16px", marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6, alignItems: "center", flexWrap: "wrap", gap: 6 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 12, color, fontWeight: 700, fontFamily: "monospace" }}>{similarity_pct}% match</span>
          {badges.map(([label, bc]) => (
            <span key={label} style={{ fontSize: 10, padding: "2px 7px", borderRadius: 99, fontWeight: 700, background: `${bc}22`, color: bc, border: `1px solid ${bc}44`, fontFamily: "monospace" }}>{label}</span>
          ))}
        </div>
        <span style={{ fontSize: 11, color: "#475569" }}>{srcName}{source?.year ? ` · ${source.year}` : ""}</span>
      </div>
      <div style={{ fontSize: 13, color: "#e2e8f0", fontWeight: 600, marginBottom: 4, lineHeight: 1.4 }}>{source?.title}</div>
      <div style={{ fontSize: 12, color: "#94a3b8", fontStyle: "italic", background: "#0f172a", borderRadius: 6, padding: "6px 10px", borderLeft: "2px solid #1e293b", marginBottom: 8, lineHeight: 1.5 }}>"{text}"</div>
      <BreakdownBar sem={semantic_score} fp={exact_score} />
      {source?.url && (
        <a href={source.url} target="_blank" rel="noopener"
          style={{ fontSize: 12, color: "#60a5fa", textDecoration: "none", display: "inline-block", marginTop: 8 }}>
          View source →
        </a>
      )}
    </div>
  );
}

// ── File drop zone ────────────────────────────────────────────────────────────
function FileDropZone({ selectedFile, onFileSelect, onClear }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);
  const ext = selectedFile ? fileExt(selectedFile.name) : "";

  return (
    <div
      onDragOver={e => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={e => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) onFileSelect(f); }}
      onClick={() => !selectedFile && inputRef.current?.click()}
      style={{
        border: `2px dashed ${dragging ? "#6366f1" : selectedFile ? "rgba(99,102,241,0.4)" : "#1e293b"}`,
        borderRadius: 12, padding: "22px 20px", textAlign: "center",
        cursor: selectedFile ? "default" : "pointer",
        background: dragging ? "rgba(99,102,241,0.05)" : "#0a111e",
        transition: "all 0.2s",
      }}
    >
      <input ref={inputRef} type="file" accept=".pdf,.docx,.txt"
        style={{ display: "none" }}
        onChange={e => e.target.files[0] && onFileSelect(e.target.files[0])} />

      {selectedFile ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 12 }}>
          <span style={{ fontSize: 30 }}>{FILE_ICONS[ext] || "📁"}</span>
          <div style={{ textAlign: "left" }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: "#a5b4fc" }}>{selectedFile.name}</div>
            <div style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>
              {(selectedFile.size / 1024).toFixed(1)} KB · {ext.toUpperCase()}
            </div>
          </div>
          <button onClick={e => { e.stopPropagation(); onClear(); }}
            style={{ marginLeft: 8, background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.25)", borderRadius: 6, padding: "4px 10px", color: "#f87171", fontSize: 12, cursor: "pointer" }}>✕</button>
        </div>
      ) : (
        <div>
          <div style={{ fontSize: 30, marginBottom: 8 }}>📂</div>
          <div style={{ fontSize: 14, fontWeight: 600, color: "#94a3b8" }}>
            Drop your file or <span style={{ color: "#6366f1" }}>browse</span>
          </div>
          <div style={{ fontSize: 12, color: "#475569", marginTop: 4 }}>PDF · DOCX · TXT — max 10 MB</div>
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function AcademicCheckPanel() {
  const [mode, setMode]         = useState("text");       // "text" | "file"
  const [text, setText]         = useState("");
  const [file, setFile]         = useState(null);
  const [threshold, setThresh]  = useState(0.65);
  const [loading, setLoading]   = useState(false);
  const [result, setResult]     = useState(null);
  const [error, setError]       = useState("");
  const [tab, setTab]           = useState("highlighted");
  const highlightRef            = useRef(null);
  const inputText               = mode === "text" ? text : "";

  useEffect(() => { injectHighlightStyles(); }, []);
  useEffect(() => {
    if (result && highlightRef.current && mode === "text") {
      highlightRef.current.innerHTML = highlightPlagiarism(text, result);
    }
  }, [result, text, mode]);

  const canRun = mode === "text"
    ? text.trim().length >= 50
    : file !== null;

  const run = async () => {
    setError(""); setLoading(true); setResult(null);
    try {
      let data;
      if (mode === "text") {
        if (text.trim().length < 50) throw new Error("Please enter at least 50 characters.");
        data = await apiJson("/academic-check", {
          method: "POST",
          body: JSON.stringify({ text: text.trim(), threshold }),
        });
      } else {
        if (!file) throw new Error("Please select a file.");
        const fd = new FormData();
        fd.append("file", file);
        fd.append("threshold", String(threshold));
        data = await apiFile("/academic-check/file", fd);
      }
      setResult(data);
    } catch (e) {
      setError(e.message);
    }
    setLoading(false);
  };

  // Styles
  const card   = { background: "rgba(15,23,42,0.8)", border: "1px solid #1e293b", borderRadius: 16, padding: 24, marginBottom: 20 };
  const input  = { width: "100%", background: "#0f172a", border: "1px solid #1e293b", borderRadius: 10, padding: "12px 16px", color: "#e2e8f0", fontSize: 14, outline: "none", resize: "vertical", fontFamily: "'DM Sans', sans-serif", boxSizing: "border-box" };
  const modeBtn = (active) => ({ padding: "9px 18px", borderRadius: 9, border: "none", cursor: "pointer", fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, background: active ? "linear-gradient(135deg,#6366f1,#8b5cf6)" : "transparent", color: active ? "white" : "#64748b" });
  const tabBtn  = (active) => ({ padding: "10px 20px", borderRadius: 10, border: "none", cursor: "pointer", fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, background: active ? "linear-gradient(135deg,#6366f1,#8b5cf6)" : "#1e293b", color: active ? "white" : "#94a3b8" });

  return (
    <div style={{ fontFamily: "'DM Sans', sans-serif", color: "#e2e8f0" }}>
      {/* Header */}
      <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>🎓 Academic Plagiarism Check</h2>
      <p style={{ color: "#64748b", fontSize: 13, marginBottom: 10 }}>
        5-stage hybrid pipeline · arXiv + OpenAlex + GitHub · BM25 + Fingerprint + BERT
      </p>

      {/* Pipeline pills */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 20 }}>
        {[["1","Preprocess","#64748b"],["2","BM25 + 3 Sources","#22c55e"],["3","Fingerprint","#f59e0b"],["4","BERT Semantic","#8b5cf6"],["5","Hybrid Score","#6366f1"]].map(([n,l,c]) => (
          <span key={n} style={{ fontSize: 11, padding: "3px 10px", borderRadius: 99, fontWeight: 600, background: `${c}22`, color: c, border: `1px solid ${c}44` }}>
            Stage {n} · {l}
          </span>
        ))}
      </div>

      {/* Input card */}
      <div style={card}>

        {/* Mode switcher */}
        <div style={{ display: "flex", background: "#0f172a", borderRadius: 12, padding: 4, marginBottom: 16, border: "1px solid #1e293b", width: "fit-content" }}>
          <button onClick={() => { setMode("text"); setFile(null); setResult(null); }} style={modeBtn(mode === "text")}>✏️ Paste Text</button>
          <button onClick={() => { setMode("file"); setText(""); setResult(null); }} style={modeBtn(mode === "file")}>📎 Upload File</button>
        </div>

        {/* Text input */}
        {mode === "text" && (
          <textarea value={text} onChange={e => setText(e.target.value)}
            placeholder="Paste your text here (minimum 50 characters)…"
            rows={8} style={input} />
        )}

        {/* File input */}
        {mode === "file" && (
          <FileDropZone
            selectedFile={file}
            onFileSelect={f => { setFile(f); setResult(null); setError(""); }}
            onClear={() => { setFile(null); setResult(null); }}
          />
        )}

        {/* Threshold + Run button */}
        <div style={{ display: "flex", alignItems: "center", gap: 20, marginTop: 14, flexWrap: "wrap" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1 }}>
            <label style={{ fontSize: 13, color: "#94a3b8", whiteSpace: "nowrap" }}>Threshold:</label>
            <input type="range" min={0.5} max={0.95} step={0.05} value={threshold}
              onChange={e => setThresh(parseFloat(e.target.value))} style={{ flex: 1 }} />
            <span style={{ fontSize: 13, color: "#f59e0b", fontFamily: "monospace", minWidth: 36 }}>
              {Math.round(threshold * 100)}%
            </span>
          </div>
          <button onClick={run} disabled={loading || !canRun}
            style={{
              background: loading || !canRun ? "#1e293b" : "linear-gradient(135deg,#6366f1,#8b5cf6)",
              color: loading || !canRun ? "#475569" : "white",
              border: "none", borderRadius: 10, padding: "11px 28px",
              fontSize: 14, fontWeight: 700, cursor: loading || !canRun ? "not-allowed" : "pointer",
              fontFamily: "'DM Sans', sans-serif",
            }}>
            {loading ? "Running pipeline…" : "Check →"}
          </button>
        </div>

        {/* Loading status */}
        {loading && (
          <div style={{ marginTop: 14, padding: "14px 16px", background: "#0a111e", borderRadius: 10, border: "1px solid #1e293b" }}>
            <div style={{ fontSize: 13, color: "#6366f1", fontWeight: 600, marginBottom: 8 }}>⟳ Running 5-stage hybrid pipeline…</div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {(mode === "file" ? ["Extracting text","BM25 indexing"] : ["BM25 indexing"])
                .concat(["Fetching arXiv","Fetching OpenAlex","Fetching GitHub","Shingling","BERT encoding","Hybrid scoring"])
                .map(s => (
                  <span key={s} style={{ fontSize: 11, color: "#475569", background: "#0f172a", borderRadius: 6, padding: "3px 8px", border: "1px solid #1e293b" }}>{s}</span>
                ))}
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div style={{ marginTop: 12, padding: "10px 14px", background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 8, color: "#f87171", fontSize: 13 }}>
            {error}
          </div>
        )}
      </div>

      {/* Results */}
      {result && (
        <>
          {/* File info banner */}
          {result.filename && (
            <div style={{ marginBottom: 16, padding: "10px 16px", background: "rgba(99,102,241,0.08)", border: "1px solid rgba(99,102,241,0.2)", borderRadius: 10, display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 20 }}>{FILE_ICONS[fileExt(result.filename)] || "📁"}</span>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#a5b4fc" }}>{result.filename}</div>
                <div style={{ fontSize: 11, color: "#64748b" }}>{result.char_count?.toLocaleString()} characters extracted</div>
              </div>
            </div>
          )}

          {/* Summary stats */}
          <div style={{ display: "grid", gridTemplateColumns: "auto 1fr 1fr 1fr 1fr", gap: 12, marginBottom: 20 }}>
            <div style={{ ...card, padding: "16px 20px", marginBottom: 0, display: "flex", alignItems: "center" }}>
              <ScoreGauge score={result.overall_similarity_pct ?? result.plagiarism_percentage} />
            </div>
            {[
              { label: "Matches Found",    value: result.matched_segments?.length ?? result.matches?.length ?? 0, color: scoreColor(result.overall_similarity_pct ?? result.plagiarism_percentage) },
              { label: "Papers Searched",  value: result.sources_checked,   color: "#6366f1" },
              { label: "Sentences",        value: result.sentences_checked, color: "#22c55e" },
              { label: "Time",             value: `${result.elapsed_seconds}s`, color: "#94a3b8" },
            ].map(s => (
              <div key={s.label} style={{ ...card, padding: "16px 20px", marginBottom: 0 }}>
                <div style={{ fontSize: 24, fontWeight: 700, color: s.color, fontFamily: "monospace" }}>{s.value}</div>
                <div style={{ fontSize: 12, color: "#64748b", marginTop: 4 }}>{s.label}</div>
              </div>
            ))}
          </div>

          {/* Tabs — hide Highlighted for file mode (no char positions) */}
          <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
            {mode === "text" && (
              <button onClick={() => setTab("highlighted")} style={tabBtn(tab === "highlighted")}>🖊 Highlighted Text</button>
            )}
            <button onClick={() => setTab("sources")} style={tabBtn(tab === "sources")}>
              📚 Sources ({result.matched_segments?.length ?? result.matches?.length ?? 0})
            </button>
          </div>

          {/* Highlighted text (text mode only) */}
          {tab === "highlighted" && mode === "text" && (
            <div style={card}>
              <div style={{ fontSize: 12, color: "#64748b", marginBottom: 12, display: "flex", gap: 16, flexWrap: "wrap" }}>
                {[["#ef4444","≥90%"],["#f97316","≥75%"],["#f59e0b","≥60%"],["#eab308","≥threshold"]].map(([c,l]) => (
                  <span key={l} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ width: 12, height: 12, borderRadius: 2, display: "inline-block", background: c+"44", border: `2px solid ${c}` }} />{l}
                  </span>
                ))}
                <span style={{ color: "#475569" }}>· Hover for source</span>
              </div>
              <div ref={highlightRef} style={{ fontSize: 14, lineHeight: 1.8, color: "#cbd5e1", background: "#0a111e", borderRadius: 10, padding: "16px 18px", whiteSpace: "pre-wrap", border: "1px solid #1e293b" }} />
            </div>
          )}

          {/* Sources list */}
          {tab === "sources" && (
            <div style={card}>
              {(result.matched_segments?.length ?? 0) === 0 && (result.matches?.length ?? 0) === 0 ? (
                <div style={{ textAlign: "center", padding: 40, color: "#475569" }}>
                  <div style={{ fontSize: 32, marginBottom: 8 }}>✅</div>
                  No significant matches found against academic sources.
                </div>
              ) : (
                (result.matched_segments ?? result.matches ?? [])
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