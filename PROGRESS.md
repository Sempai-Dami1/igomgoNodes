# Progress

Status legend: ⬜ not started · 🟨 in progress · ✅ done · ⏸ deferred

## Phase 0 — Planning
- ✅ Repository created and published
- ✅ Planning docs: AGENTS, CONCEPT, PROGRESS, SECURITY, FUTURE
- ✅ Decisions in [CONCEPT.md §9](./CONCEPT.md#9-decisions) — editor, feedback, users/saving,
  distribution (GitHub), and audio delay/echo inside the node
- ✅ Python 3.14 project venv (`.venv`) with dependencies installed

## Phase 1 — Scaffolding
- ✅ `pyproject.toml` (package `igomgo_nodes`, extras: `ui`, `examples`, `dev`);
  `supabase` extra deferred
- ✅ `.gitignore` (venv, `__pycache__`, `.streamlit/secrets.toml`, `.env`)
- ✅ `ruff`, `pytest`, Pyright config; CI workflow `.github/workflows/ci.yml`
  (lint, format check, Pyright, pytest on Python 3.11 + 3.14)
- ✅ `app.py` placeholder canvas (3 draggable nodes, click-to-select) + `AppTest` smoke test
- ✅ `.streamlit/config.toml` (25 MB upload cap) and `requirements.txt` for Community Cloud
- ✅ First deploy to Streamlit Community Cloud (confirmed by project owner)

## Phase 2 — Core model (`core/`)
- ✅ `PortSpec`, `NodeSpec`, `BaseNode`, node registry (validated specs, consumer processing,
  explicit registration, focused unit tests)
- ✅ `Graph`, `Edge`, `NodeInstance`, positions, `GraphPolicy`, `LoopPolicy`
  (structural validation, finite positive loop limits, JSON round-trip tests)
- ✅ Validation: port connection limits, node input/output limits, dtype compatibility
  (`Graph.validate_connections(registry)`, directional ports, fan-in/out, minimums, wildcard types)
- ✅ Cycle detection (SCC) + single graph-level feedback permission check
  (iterative traversal, self-loops, component ordering, long-chain/cycle tests)
- ✅ Virtual spiral: `Graph.unroll(n)` expands cycles into an acyclic chain
  (explicit feedback boundaries, first-pass external inputs, final-pass outputs,
  independent copies, exact node/edge cap tests)
- ✅ Executor: topological run of unrolled graph, timeout, snapshot capture
  (spawned worker termination, ordered fan-in, iteration context, complete-pass snapshots,
  explicit consumer errors, snapshot-count and retained-result limits)
- ✅ Versioned JSON serialization + round-trip tests (`loads_graph`/`dumps_graph`,
  strict schema-v1 import, registry resolution, size/count limits, explicit migration policy)

## Phase 3 — Streamlit editor (`ui/`)
- ✅ `EditorAdapter` over `streamlit-flow-component` (session-owned core graph)
- ✅ Palette, drag/reposition, tap-select + inspector movement, connect/disconnect
  (literal tap-on-canvas placement deferred by agreement; see FUTURE.md)
- ✅ Inspector panel (Pydantic parameter-schema forms, port details, validated edits)
- ✅ Rule feedback in UI (transactional rejected connections, loop policy and boundary controls,
  explicit run-readiness validation; incomplete graphs allowed during editing)

## Phase 4 — Proof-of-concept examples
- ✅ Logic gates demo (constant, NOT, AND, OR, XOR; run and inspect outputs)
- ✅ Audio: WAV upload → gain / low-pass / delay → waveform (in/out) + player + WAV export
  (generated sample, bounded decoding, additive sample feedback, explicit clipping warning)
- ✅ Image: upload → grayscale / blur / invert → input + final display + PNG export
  (generated sample, bounded PNG/JPEG decode to RGB)
- ✅ Electronic components: symbolic nodes (no simulation)
- ✅ Gallery execution and decoded-input caching; runtime payloads separate from graph JSON;
  graph/input changes invalidate displayed results; consumer/media errors shown explicitly
- ⏸ Manual graph-wide tap/click iteration stepping recorded in FUTURE.md
  (requires resumable state and synchronization without replaying prior passes)

## Phase 5 — Storage (anonymous, local)
- ⬜ `GraphStore` interface
- ⬜ `BrowserFileStore`: save via download, load via upload (validated JSON)
- ⬜ `LocalJsonStore` for local `streamlit run` use
- ⏸ Supabase (`SupabaseStore`, anonymous sign-ins, RLS, private buckets) — see FUTURE.md

## Phase 6 — Release
- ⬜ Docs: consumer guide ("write your own node in 20 lines")
- ⬜ Deploy demo to Streamlit Community Cloud
- ⬜ Tag v0.1.0 (consumers install via `git+https://github.com/Sempai-Dami1/igomgoNodes.git@v0.1.0`)
