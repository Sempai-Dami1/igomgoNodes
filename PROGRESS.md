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
- ⬜ First deploy to Streamlit Community Cloud (needs repo push + your Streamlit account)

## Phase 2 — Core model (`core/`)
- ⬜ `PortSpec`, `NodeSpec`, `BaseNode`, node registry
- ⬜ `Graph`, `Edge`, positions, `GraphPolicy`, `LoopPolicy`
- ⬜ Validation: port connection limits, node input/output limits, dtype compatibility
- ⬜ Cycle detection (SCC) + single graph-level feedback permission check
- ⬜ Virtual spiral: `Graph.unroll(n)` expands cycles into an acyclic chain
- ⬜ Executor: topological run of unrolled graph, timeout, snapshot capture
- ⬜ Versioned JSON serialization + round-trip tests

## Phase 3 — Streamlit editor (`ui/`)
- ⬜ `EditorAdapter` over `streamlit-flow-component`
- ⬜ Palette, drag/reposition, tap-select-move, connect/disconnect
- ⬜ Inspector panel (params form generated from node schema)
- ⬜ Rule feedback in UI (rejected connections, loop policy prompts)

## Phase 4 — Proof-of-concept examples
- ⬜ Logic gates demo
- ⬜ Audio: WAV upload → gain / low-pass / delay → waveform (in/out) + player + WAV export
- ⬜ Image: upload → grayscale / blur / invert → input + final display + PNG export
- ⬜ Electronic components: symbolic nodes (no simulation)

## Phase 5 — Storage (anonymous, local)
- ⬜ `GraphStore` interface
- ⬜ `BrowserFileStore`: save via download, load via upload (validated JSON)
- ⬜ `LocalJsonStore` for local `streamlit run` use
- ⏸ Supabase (`SupabaseStore`, anonymous sign-ins, RLS, private buckets) — see FUTURE.md

## Phase 6 — Release
- ⬜ Docs: consumer guide ("write your own node in 20 lines")
- ⬜ Deploy demo to Streamlit Community Cloud
- ⬜ Tag v0.1.0 (consumers install via `git+https://github.com/Sempai-Dami1/igomgoNodes.git@v0.1.0`)
