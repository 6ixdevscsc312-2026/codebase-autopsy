'use strict';

const fs = require('fs');
const path = require('path');

// Pulls identifier-looking tokens out of inline code spans / code blocks
// in a markdown doc, e.g. `runBob()`, `computeDrift`.
const CODE_SPAN_RE = /`([a-zA-Z_$][\w$]*)\s*\(?/g;

// Pulls exported/declared function-ish names out of JS source.
const EXPORT_PATTERNS = [
  /module\.exports\s*=\s*\{([^}]*)\}/s,          // module.exports = { a, b }
  /exports\.([a-zA-Z_$][\w$]*)\s*=/g,             // exports.foo =
  /function\s+([a-zA-Z_$][\w$]*)\s*\(/g,          // function foo(
  /const\s+([a-zA-Z_$][\w$]*)\s*=\s*(?:async\s*)?\(/g, // const foo = (async) (
];

/**
 * Computes a "drift score": how much a doc file (typically README.md)
 * claims about the codebase's public surface diverges from what's
 * actually there.
 *
 * score = 0   -> perfectly in sync
 * score -> 1  -> heavy divergence (lots documented-but-missing and/or
 *                 present-but-undocumented symbols)
 *
 * This is a heuristic, not ground truth — it's meant to flag files
 * worth a human (or Bob) second look, not to be authoritative.
 */
function computeDrift(docPath, sourcePaths, cwd = process.cwd()) {
  const docText = safeRead(path.resolve(cwd, docPath));
  const claimed = docText ? extractClaimedSymbols(docText) : new Set();

  const actual = new Set();
  const perFile = [];
  for (const srcPath of sourcePaths) {
    const resolved = path.resolve(cwd, srcPath);
    const text = safeRead(resolved);
    if (text == null) {
      perFile.push({ file: srcPath, found: false });
      continue;
    }
    const symbols = extractActualSymbols(text);
    symbols.forEach((s) => actual.add(s));
    perFile.push({ file: srcPath, found: true, symbols: [...symbols] });
  }

  const documentedButMissing = [...claimed].filter((s) => !actual.has(s));
  const presentButUndocumented = [...actual].filter((s) => !claimed.has(s));
  const inSync = [...claimed].filter((s) => actual.has(s));

  const totalSurface = new Set([...claimed, ...actual]).size;
  const mismatches = documentedButMissing.length + presentButUndocumented.length;
  const score = totalSurface === 0 ? 0 : round(mismatches / (totalSurface * 2), 3);

  return {
    docPath,
    score, // 0 (in sync) .. ~1 (heavy drift)
    claimedCount: claimed.size,
    actualCount: actual.size,
    inSync,
    documentedButMissing,
    presentButUndocumented,
    perFile,
  };
}

function extractClaimedSymbols(docText) {
  const found = new Set();
  let m;
  CODE_SPAN_RE.lastIndex = 0;
  while ((m = CODE_SPAN_RE.exec(docText)) !== null) {
    found.add(m[1]);
  }
  return found;
}

function extractActualSymbols(sourceText) {
  const found = new Set();

  const moduleExportsMatch = sourceText.match(EXPORT_PATTERNS[0]);
  if (moduleExportsMatch) {
    moduleExportsMatch[1]
      .split(',')
      .map((s) => s.trim().split(':')[0].trim())
      .filter(Boolean)
      .forEach((s) => found.add(s));
  }

  for (const re of [EXPORT_PATTERNS[1], EXPORT_PATTERNS[2], EXPORT_PATTERNS[3]]) {
    re.lastIndex = 0;
    let m;
    while ((m = re.exec(sourceText)) !== null) {
      found.add(m[1]);
    }
  }

  return found;
}

function safeRead(p) {
  try {
    return fs.readFileSync(p, 'utf8');
  } catch {
    return null;
  }
}

function round(n, dp) {
  const f = 10 ** dp;
  return Math.round(n * f) / f;
}

module.exports = { computeDrift };
