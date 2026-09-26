# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Project

Python 3.10+ tool. No package manager manifest (no `setup.py`/`pyproject.toml`). Dependencies are stdlib only (`ast`, `subprocess`, `dataclasses`) plus the external `bob` CLI binary. No `pip install` step.

## Run commands

```bash
# Full live run (requires BOB_API_KEY + bob binary on PATH)
python3 -m autopsy.main <repo_path>

# Offline/demo mode — no credentials or binary needed
python3 -m autopsy.main sample_repo --mock

# Ingest-only smoke test
python3 -m autopsy.ingest sample_repo

# Graph-only smoke test
python3 -m autopsy.graph sample_repo
```

## Tests

`tests/` directory exists but is empty. No test framework is configured. Use `--mock` mode + manual inspection to validate the pipeline offline.

## Environment

- `BOB_API_KEY` — Inference-scoped key for the real `bob` CLI (required for live runs).
- `AUTOPSY_MOCK_BOB=1` — auto-enables mock mode; `BobClient` checks this before requiring `BOB_API_KEY`.
- Mock mode is **not** a fake: it reads the actual referenced files and applies a heuristic, so pipeline logic (JSON parsing, scoring, reporting) is exercised for real.

## Code style

- All modules use `from __future__ import annotations` for forward-reference support.
- Data models use `@dataclass` (from `dataclasses`) throughout — not plain dicts or NamedTuples.
- `ModuleInfo.path` is always **relative** to `repo_root` (set via `os.path.relpath`). Never store or compare absolute paths.
- `BobClient.run()` appends `@path` references to the prompt tail — Bob Shell reads them as file refs, not just inline text.
- `bob run` output is parsed from the **last line** of stdout only (`splitlines()[-1]`); earlier lines may be progress noise.

## Architecture

```
walk_repo()  →  list[ModuleInfo]  →  build_graph()  →  RepoGraph
                                                          ↓
                                                     find_cycles()
                                                     in_degree() / out_degree()
                                          ↓
                              analyze_module() via BobClient.run()
                                          ↓
                                     JSON verdict → drift report
```

- `ingest.py` is purely AST-based — no AI, no network.
- `graph.py` depends only on `ingest.py`; no circular dependency between autopsy modules.
- `bob_client.py` is the only module that shells out or does network I/O.

## `ModuleInfo` fields (non-obvious)

- `module_calls: list[str]` — calls made at **module scope** (outside any function/class). Populated separately from `FunctionInfo.calls`; will not overlap with per-function call lists.
- `ModuleInfo.path` is always **relative** to `repo_root`. Never store absolute paths.

## Known edge cases in `graph.py` `find_cycles()`

1. **Duplicate cycles**: No deduplication. The same cycle (e.g. A→B→A) can appear multiple times if re-entered from different nodes.
2. **Recursion limit**: Uses recursive DFS — will raise `RecursionError` on repos with import chains longer than Python's default recursion limit (~1000).
3. **Phantom nodes**: `find_cycles` only starts DFS from `self.modules` keys. Nodes that appear only as edge *targets* (but not in `modules`) are never DFS roots; cycles that run exclusively through such nodes are silently missed.
4. **`stack.index()` is O(n)**: Called on every back-edge — fine for small repos, degrades on large graphs.
5. **Self-loops cannot be created**: `build_graph` filters `target != m.path`, so self-edges are never added, even though `find_cycles` would detect them correctly.
