#!/usr/bin/env node
'use strict';

const path = require('path');
const fs = require('fs');
const { runBob } = require('../lib/bobClient');
const { computeDrift } = require('../lib/driftScore');
const { generateHtmlReport } = require('../lib/htmlReport');

async function main() {
  const { targetDir, htmlOutPath } = parseArgs(process.argv.slice(2));
  const cwd = path.resolve(process.cwd(), targetDir);

  if (!fs.existsSync(cwd)) {
    console.error(`Path not found: ${cwd}`);
    process.exit(1);
  }

  const readmePath = findReadme(cwd);
  const sourceFiles = findSourceFiles(cwd, { limit: 25 });

  console.log(`codebase-autopsy — analyzing ${cwd}`);
  console.log(`  README: ${readmePath || '(none found)'}`);
  console.log(`  Source files scanned: ${sourceFiles.length}`);
  console.log('');

  // 1. Ask Bob for a plain-English read of the repo's key files.
  const fileRefs = sourceFiles.slice(0, 8).map((f) => `@${f}`).join(' ');
  const prompt = `Explain what this codebase does and how its main pieces fit together. Reference files: ${fileRefs}`;

  let bobResult;
  try {
    bobResult = await runBob(prompt, { cwd });
  } catch (err) {
    console.error(`Bob call failed: ${err.message}`);
    process.exit(1);
  }

  console.log('--- Bob\'s read on the codebase ---');
  console.log(bobResult.last_message);
  if (bobResult.mocked) {
    console.log(`\n(mock mode${bobResult.fallbackReason ? ': ' + bobResult.fallbackReason : ''})`);
  }
  console.log('');

  // 2. Compute doc/code drift, if a README exists.
  if (readmePath) {
    const drift = computeDrift(path.relative(cwd, readmePath), sourceFiles, cwd);
    console.log('--- Drift report (README vs. source) ---');
    console.log(`  Drift score: ${drift.score}  (0 = in sync, closer to 1 = diverged)`);
    console.log(`  Documented symbols: ${drift.claimedCount}`);
    console.log(`  Actual symbols found: ${drift.actualCount}`);
    if (drift.documentedButMissing.length) {
      console.log(`  Documented but missing: ${drift.documentedButMissing.join(', ')}`);
    }
    if (drift.presentButUndocumented.length) {
      console.log(`  Present but undocumented: ${drift.presentButUndocumented.join(', ')}`);
    }
  } else {
    console.log('--- Drift report ---');
    console.log('  Skipped: no README.md found to compare against.');
  }

  // 3. Optionally write a visual HTML report.
  if (htmlOutPath) {
    const fileStats = gatherFileStats(sourceFiles, cwd);
    const driftForReport = readmePath
      ? computeDrift(path.relative(cwd, readmePath), sourceFiles, cwd)
      : null;
    const html = generateHtmlReport({
      repoName: path.basename(cwd),
      bobMessage: bobResult.last_message,
      mocked: bobResult.mocked,
      fallbackReason: bobResult.fallbackReason,
      drift: driftForReport,
      fileStats,
    });
    const outPath = path.resolve(process.cwd(), htmlOutPath);
    fs.writeFileSync(outPath, html, 'utf8');
    console.log('');
    console.log(`--- HTML report written to ${outPath} ---`);
  }
}

// Independent of mock mode, so the report works with real Bob output too.
function gatherFileStats(sourceFiles, cwd) {
  return sourceFiles.map((f) => {
    try {
      const content = fs.readFileSync(path.resolve(cwd, f), 'utf8');
      const approxFunctions = (content.match(/\bfunction\b|\b=>\b/g) || []).length;
      return { file: f, lineCount: content.split('\n').length, approxFunctions };
    } catch {
      return { file: f, lineCount: 0, approxFunctions: 0 };
    }
  });
}

function parseArgs(argv) {
  let targetDir = '.';
  let htmlOutPath = null;
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--html') {
      htmlOutPath = argv[i + 1] || 'autopsy-report.html';
      i++; // consume the value
    } else if (!argv[i].startsWith('--')) {
      targetDir = argv[i];
    }
  }
  return { targetDir, htmlOutPath };
}

function findReadme(dir) {
  const candidates = ['README.md', 'Readme.md', 'readme.md'];
  for (const c of candidates) {
    const p = path.join(dir, c);
    if (fs.existsSync(p)) return p;
  }
  return null;
}

function findSourceFiles(dir, { limit = 25, exts = ['.js', '.ts', '.jsx', '.tsx'] } = {}) {
  const ignore = new Set(['node_modules', '.git', 'dist', 'build', 'coverage']);
  const results = [];

  function walk(current) {
    if (results.length >= limit) return;
    let entries;
    try {
      entries = fs.readdirSync(current, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      if (results.length >= limit) return;
      if (ignore.has(entry.name)) continue;
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) {
        walk(full);
      } else if (exts.includes(path.extname(entry.name))) {
        results.push(path.relative(dir, full));
      }
    }
  }

  walk(dir);
  return results;
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
