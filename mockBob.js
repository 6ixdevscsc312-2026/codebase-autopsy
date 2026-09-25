'use strict';

const fs = require('fs');
const path = require('path');

// Matches @relative/path.js or @./relative/path.js style references.
const FILE_REF_RE = /@([./\w\-]+\.\w+)/g;

/**
 * A mock Bob backend that actually reads the files referenced in the
 * prompt (via @path) so downstream logic — prompt construction, JSON
 * parsing, drift scoring — can be exercised meaningfully without a
 * live Bob Shell install or network access.
 *
 * This is NOT a smart model. It does simple, honest heuristics over
 * real file content: function/export counts, rough size, and a naive
 * summary line per file. Good enough to validate the pipeline; not a
 * substitute for the real `bob run` output.
 */
async function runMock(prompt, opts = {}) {
  const cwd = opts.cwd || process.cwd();
  const refs = extractFileRefs(prompt);

  const fileSummaries = refs.map((ref) => summarizeFile(ref, cwd));

  const last_message = buildMockMessage(prompt, fileSummaries);

  return {
    last_message,
    tokens: {
      prompt: estimateTokens(prompt),
      completion: estimateTokens(last_message),
    },
    cost: {
      bobcoins: 0, // mock calls are free
    },
    mocked: true,
    filesRead: fileSummaries.map((f) => f.ref),
  };
}

function extractFileRefs(prompt) {
  const matches = [...prompt.matchAll(FILE_REF_RE)];
  return [...new Set(matches.map((m) => m[1]))];
}

function summarizeFile(ref, cwd) {
  const resolved = path.resolve(cwd, ref);
  try {
    const content = fs.readFileSync(resolved, 'utf8');
    const lines = content.split('\n');
    const functionCount = (content.match(/\bfunction\b|\b=>\b/g) || []).length;
    const exportCount = (content.match(/\bexport(s)?\b|\bmodule\.exports\b/g) || []).length;
    return {
      ref,
      found: true,
      lineCount: lines.length,
      byteSize: Buffer.byteLength(content, 'utf8'),
      approxFunctions: functionCount,
      approxExports: exportCount,
      preview: lines.slice(0, 3).join(' ').slice(0, 120),
    };
  } catch (err) {
    return { ref, found: false, error: err.code || err.message };
  }
}

function buildMockMessage(prompt, fileSummaries) {
  if (fileSummaries.length === 0) {
    return `[mock] No @file references found in prompt. Prompt was: "${truncate(prompt, 80)}"`;
  }

  const lines = fileSummaries.map((f) => {
    if (!f.found) {
      return `- ${f.ref}: NOT FOUND (${f.error})`;
    }
    return `- ${f.ref}: ${f.lineCount} lines, ~${f.approxFunctions} functions/arrows, ~${f.approxExports} export statements. Starts: "${f.preview}"`;
  });

  return [
    '[mock response — not real Bob output]',
    `Analyzed ${fileSummaries.length} referenced file(s):`,
    ...lines,
  ].join('\n');
}

function estimateTokens(text) {
  // rough, not exact — good enough for mock-mode stats
  return Math.ceil(text.length / 4);
}

function truncate(str, n) {
  return str.length > n ? str.slice(0, n) + '…' : str;
}

module.exports = { runMock };
