'use strict';

/**
 * Builds a single self-contained HTML report (no external CSS/JS/fonts —
 * everything inline) so it's safe to demo offline. Takes the same data
 * autopsy.js already collects; doesn't require a live Bob call to render.
 */
function generateHtmlReport(data) {
  const {
    repoName,
    bobMessage,
    mocked,
    fallbackReason,
    drift,       // { score, claimedCount, actualCount, inSync, documentedButMissing, presentButUndocumented } | null
    fileStats,   // [{ file, lineCount, approxFunctions }]
  } = data;

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>codebase-autopsy — ${escapeHtml(repoName)}</title>
<style>
  :root {
    --bg: #f7f7f8;
    --panel: #ffffff;
    --text: #1a1a1a;
    --muted: #6b6b6b;
    --border: #e2e2e4;
    --accent: #4f46e5;
    --good: #16a34a;
    --warn: #d97706;
    --bad: #dc2626;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --bg: #0f0f12;
      --panel: #1a1a1f;
      --text: #eaeaea;
      --muted: #9a9a9a;
      --border: #2c2c33;
      --accent: #818cf8;
      --good: #4ade80;
      --warn: #fbbf24;
      --bad: #f87171;
    }
  }
  :root[data-theme="dark"] {
    --bg: #0f0f12;
    --panel: #1a1a1f;
    --text: #eaeaea;
    --muted: #9a9a9a;
    --border: #2c2c33;
    --accent: #818cf8;
    --good: #4ade80;
    --warn: #fbbf24;
    --bad: #f87171;
  }
  * { box-sizing: border-box; }
  html { scroll-padding-top: env(safe-area-inset-top, 0px); }
  body {
    margin: 0;
    padding: env(safe-area-inset-top, 0px) 0 env(safe-area-inset-bottom, 0px) 0;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    line-height: 1.5;
  }
  .wrap { max-width: 880px; margin: 0 auto; padding: 32px 20px 64px; }
  h1 { font-size: 1.5rem; margin: 0 0 4px; }
  .subtitle { color: var(--muted); font-size: 0.9rem; margin-bottom: 28px; }
  .grid { display: grid; grid-template-columns: 220px 1fr; gap: 20px; margin-bottom: 24px; }
  @media (max-width: 640px) { .grid { grid-template-columns: 1fr; } }
  .panel {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
  }
  .panel h2 { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); margin: 0 0 14px; }
  .gauge-wrap { display: flex; flex-direction: column; align-items: center; justify-content: center; }
  .gauge-label { font-size: 0.8rem; color: var(--muted); margin-top: 8px; text-align: center; }
  .badge-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
  .badge { padding: 3px 10px; border-radius: 999px; font-size: 0.8rem; font-family: ui-monospace, monospace; }
  .badge.missing { background: color-mix(in srgb, var(--bad) 18%, transparent); color: var(--bad); }
  .badge.undoc { background: color-mix(in srgb, var(--warn) 18%, transparent); color: var(--warn); }
  .badge.sync { background: color-mix(in srgb, var(--good) 18%, transparent); color: var(--good); }
  .bar-row { display: flex; align-items: center; gap: 10px; margin: 8px 0; }
  .bar-label { width: 140px; font-size: 0.8rem; font-family: ui-monospace, monospace; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex-shrink: 0; }
  .bar-track { flex: 1; background: var(--border); border-radius: 4px; height: 10px; overflow: hidden; }
  .bar-fill { height: 100%; background: var(--accent); border-radius: 4px; }
  .bar-value { width: 34px; font-size: 0.75rem; color: var(--muted); text-align: right; flex-shrink: 0; }
  .bob-text { white-space: pre-wrap; font-family: ui-monospace, monospace; font-size: 0.85rem; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 14px; max-height: 320px; overflow-y: auto; }
  .mock-tag { display: inline-block; margin-top: 10px; font-size: 0.75rem; color: var(--warn); border: 1px solid var(--warn); border-radius: 6px; padding: 2px 8px; }
  .empty { color: var(--muted); font-size: 0.85rem; font-style: italic; }
</style>
</head>
<body>
<div class="wrap">
  <h1>codebase-autopsy</h1>
  <div class="subtitle">${escapeHtml(repoName)} · generated ${escapeHtml(new Date().toISOString())}</div>

  <div class="grid">
    <div class="panel gauge-wrap">
      <h2 style="align-self:flex-start;">Drift score</h2>
      ${drift ? driftGaugeSvg(drift.score) : '<div class="empty">No README found — nothing to compare.</div>'}
      ${drift ? `<div class="gauge-label">${drift.score} &nbsp;·&nbsp; ${drift.claimedCount} documented / ${drift.actualCount} actual symbols</div>` : ''}
    </div>

    <div class="panel">
      <h2>Symbol diff</h2>
      ${drift ? symbolBadges(drift) : '<div class="empty">No README to diff against.</div>'}
    </div>
  </div>

  <div class="panel" style="margin-bottom:24px;">
    <h2>File complexity (approx. functions per file)</h2>
    ${fileBars(fileStats)}
  </div>

  <div class="panel">
    <h2>Bob's read on the codebase</h2>
    <div class="bob-text">${escapeHtml(bobMessage || '(no response)')}</div>
    ${mocked ? `<div class="mock-tag">mock mode${fallbackReason ? ': ' + escapeHtml(fallbackReason) : ''}</div>` : ''}
  </div>
</div>
</body>
</html>`;
}

function driftGaugeSvg(score) {
  const clamped = Math.max(0, Math.min(1, score));
  const color = clamped < 0.2 ? 'var(--good)' : clamped < 0.5 ? 'var(--warn)' : 'var(--bad)';
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - clamped);
  return `<svg width="140" height="140" viewBox="0 0 140 140">
    <circle cx="70" cy="70" r="${radius}" fill="none" stroke="var(--border)" stroke-width="14" />
    <circle cx="70" cy="70" r="${radius}" fill="none" stroke="${color}" stroke-width="14"
      stroke-dasharray="${circumference}" stroke-dashoffset="${offset}"
      stroke-linecap="round" transform="rotate(-90 70 70)" />
    <text x="70" y="76" text-anchor="middle" font-size="26" font-weight="600" fill="var(--text)" font-family="ui-monospace, monospace">${clamped.toFixed(2)}</text>
  </svg>`;
}

function symbolBadges(drift) {
  const { inSync, documentedButMissing, presentButUndocumented } = drift;
  if (!inSync.length && !documentedButMissing.length && !presentButUndocumented.length) {
    return '<div class="empty">No comparable symbols found.</div>';
  }
  const row = (items, cls) => items.map((s) => `<span class="badge ${cls}">${escapeHtml(s)}</span>`).join('');
  return `<div class="badge-row">${row(inSync, 'sync')}${row(documentedButMissing, 'missing')}${row(presentButUndocumented, 'undoc')}</div>
  <div style="margin-top:10px; font-size:0.75rem; color:var(--muted);">
    <span style="color:var(--good);">●</span> in sync &nbsp;
    <span style="color:var(--bad);">●</span> documented but missing &nbsp;
    <span style="color:var(--warn);">●</span> present but undocumented
  </div>`;
}

function fileBars(fileStats) {
  if (!fileStats || fileStats.length === 0) {
    return '<div class="empty">No source files scanned.</div>';
  }
  const max = Math.max(1, ...fileStats.map((f) => f.approxFunctions));
  return fileStats
    .map((f) => {
      const pct = Math.round((f.approxFunctions / max) * 100);
      return `<div class="bar-row">
        <div class="bar-label" title="${escapeHtml(f.file)}">${escapeHtml(f.file)}</div>
        <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
        <div class="bar-value">${f.approxFunctions}</div>
      </div>`;
    })
    .join('');
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

module.exports = { generateHtmlReport };
