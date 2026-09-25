# codebase-autopsy

An onboarding/health tool built on **IBM Bob 2.0**'s repo-aware reasoning
(via Bob Shell). Points it at a codebase and it produces:

1. A plain-English read of what the code does and how the pieces fit
   together (via `bob run --format json`, referencing real files with `@path`)
2. A **drift score** — how far a README's documented API has diverged
   from what's actually exported in the source

Built for the IBM Bob 2.0 hackathon (lablab, Sept 25–27, 2026).

## Why this, not a bare API wrapper

Bob Shell is a CLI agent, not just an endpoint — `bob run "<prompt>"`
reasons over the files you point it at with `@filename` and returns
structured JSON (`last_message` plus token/cost stats). Using it lets
`autopsy` show off Bob's actual repo understanding rather than a single
snippet-in, snippet-out call.

## Setup

```bash
npm install          # no external deps currently, but keeps this future-proof
export BOB_API_KEY=your_inference_scoped_key
```

Bob Shell itself (the `bob` binary) needs to be installed locally and on
`PATH` for real calls. If it isn't found — or if `BOB_MOCK=true` is set —
`autopsy` automatically falls back to mock mode.

## Usage

```bash
node bin/autopsy.js ./path/to/repo
```

Run against the built-in fixture to see it work without any real repo:

```bash
node bin/autopsy.js /tmp/fixture   # see lib/ for how the fixture was built
```

## Mock mode — how it's honest

Mock mode does **not** fake intelligence. It parses `@path` references
out of the prompt, actually reads those files off disk, and reports real
heuristics (line count, rough function/export counts, a content preview).
This lets prompt construction, JSON parsing, and drift scoring all be
validated end-to-end without a live Bob install or network access —
which matters since the dev sandbox here has neither.

## Drift scoring

`lib/driftScore.js` extracts identifier-looking tokens from inline code
spans in `README.md` (documented API surface) and compares them against
actual exported/declared symbols in the source files (`module.exports`,
`exports.x =`, top-level `function`/arrow declarations). The score is:

```
mismatches / (total_unique_symbols * 2)
```

`0` = docs and code fully agree. Closer to `1` = meaningful divergence.
It also lists exactly which symbols are documented-but-missing and
which are present-but-undocumented, so it's actionable, not just a number.

## Project layout

```
bin/autopsy.js      CLI entry point
lib/bobClient.js     Shells out to `bob run --format json`, with mock fallback
lib/mockBob.js       Mock backend that reads real @path files
lib/driftScore.js    README-vs-source drift scoring
```

## Known limitations (honest, for the demo)

- Symbol extraction is regex-based and JS/TS-oriented — good enough for
  a 48-hour build, not a real parser (no AST).
- Drift scoring only looks at `README.md` vs. flat exported symbols —
  doesn't yet weigh *how* a function is described, just whether it's
  named.
- Mock mode's heuristics are intentionally simple; they exist to prove
  the pipeline works, not to substitute for real Bob reasoning in the
  final demo.
