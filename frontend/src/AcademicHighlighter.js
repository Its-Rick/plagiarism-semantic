/**
 * AcademicHighlighter.js
 * ──────────────────────
 * Takes the JSON from /api/academic-check and wraps matched segments
 * in <mark> tags with tooltip showing source paper + similarity %.
 *
 * Usage:
 *   const html = highlightPlagiarism(originalText, apiResult);
 *   document.getElementById('output').innerHTML = html;
 */

/**
 * Main highlight function.
 * @param {string} text        - The original submission text
 * @param {object} result      - JSON from /api/academic-check
 * @returns {string}           - HTML string with <mark> tags inserted
 */
export function highlightPlagiarism(text, result) {
  if (!result?.matched_segments?.length) return escapeHtml(text);

  // Sort segments by start position (ascending) and deduplicate overlaps
  const segments = deduplicateSegments(
    [...result.matched_segments].sort((a, b) => a.start_char - b.start_char)
  );

  let html = '';
  let cursor = 0;

  for (const seg of segments) {
    const start = seg.start_char;
    const end   = seg.end_char;

    // Validate bounds
    if (start < cursor || start >= text.length) continue;

    // Plain text before this match
    html += escapeHtml(text.slice(cursor, start));

    // Colour based on severity
    const colour = getSeverityColour(seg.similarity_pct);
    const src    = seg.source;
    const authors = src.authors?.join(', ') || 'Unknown authors';
    const year    = src.year ? ` (${src.year})` : '';
    const srcName = src.source === 'arxiv' ? 'ArXiv' : 'Semantic Scholar';

    // Build tooltip content (data attributes — styled via CSS)
    html += `<mark
      class="plagiarism-mark"
      style="background:${colour.bg}; border-bottom: 2px solid ${colour.border}; cursor:pointer; position:relative;"
      data-similarity="${seg.similarity_pct}"
      data-title="${escapeAttr(src.title)}"
      data-authors="${escapeAttr(authors + year)}"
      data-url="${escapeAttr(src.url)}"
      data-source="${escapeAttr(srcName)}"
    >${escapeHtml(text.slice(start, end))}<span class="plagiarism-tooltip">
        <strong>${escapeHtml(src.title)}</strong><br>
        <em>${escapeHtml(authors)}${year}</em><br>
        <span class="sim-badge" style="color:${colour.border}">${seg.similarity_pct}% similar</span><br>
        ${src.url
          ? `<a href="${escapeAttr(src.url)}" target="_blank" rel="noopener">View on ${srcName} →</a>`
          : `<span>Source: ${srcName}</span>`
        }
      </span></mark>`;

    cursor = end;
  }

  // Remaining plain text
  html += escapeHtml(text.slice(cursor));

  return html;
}

/**
 * Severity colours based on similarity percentage.
 */
function getSeverityColour(pct) {
  if (pct >= 90) return { bg: 'rgba(239,68,68,0.18)',  border: '#ef4444' };  // red
  if (pct >= 75) return { bg: 'rgba(249,115,22,0.18)', border: '#f97316' };  // orange
  if (pct >= 60) return { bg: 'rgba(245,158,11,0.18)', border: '#f59e0b' };  // amber
  return              { bg: 'rgba(234,179,8,0.14)',  border: '#eab308' };    // yellow
}

/**
 * Remove overlapping segments (keep the one with higher similarity).
 */
function deduplicateSegments(sorted) {
  const result = [];
  let lastEnd = -1;
  for (const seg of sorted) {
    if (seg.start_char >= lastEnd) {
      result.push(seg);
      lastEnd = seg.end_char;
    } else if (seg.similarity_pct > (result.at(-1)?.similarity_pct ?? 0)) {
      result[result.length - 1] = seg;
      lastEnd = seg.end_char;
    }
  }
  return result;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escapeAttr(str) {
  return String(str || '').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/**
 * CSS to inject once into the page for tooltip styling.
 * Call injectHighlightStyles() once on app mount.
 */
export function injectHighlightStyles() {
  if (document.getElementById('plagiarism-styles')) return;
  const style = document.createElement('style');
  style.id = 'plagiarism-styles';
  style.textContent = `
    .plagiarism-mark {
      border-radius: 3px;
      padding: 1px 2px;
      transition: filter 0.15s;
    }
    .plagiarism-mark:hover { filter: brightness(1.2); }

    .plagiarism-tooltip {
      display: none;
      position: absolute;
      bottom: calc(100% + 8px);
      left: 50%;
      transform: translateX(-50%);
      background: #0f172a;
      border: 1px solid #1e293b;
      border-radius: 10px;
      padding: 10px 14px;
      min-width: 260px;
      max-width: 340px;
      font-size: 12.5px;
      line-height: 1.6;
      color: #e2e8f0;
      z-index: 1000;
      box-shadow: 0 8px 32px rgba(0,0,0,0.5);
      pointer-events: auto;
      white-space: normal;
    }

    .plagiarism-tooltip a {
      color: #60a5fa;
      text-decoration: none;
      font-size: 12px;
    }

    .plagiarism-tooltip a:hover { text-decoration: underline; }

    .plagiarism-tooltip .sim-badge {
      font-weight: 700;
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
    }

    .plagiarism-tooltip::after {
      content: '';
      position: absolute;
      top: 100%;
      left: 50%;
      transform: translateX(-50%);
      border: 6px solid transparent;
      border-top-color: #1e293b;
    }

    .plagiarism-mark:hover .plagiarism-tooltip,
    .plagiarism-mark:focus .plagiarism-tooltip {
      display: block;
    }
  `;
  document.head.appendChild(style);
}