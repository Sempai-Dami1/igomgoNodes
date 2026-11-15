# AGENTS.md — Guidance for AI coding agents and contributors

Read [CONCEPT.md](./CONCEPT.md) first, then check [PROGRESS.md](./PROGRESS.md) for the
current phase. Deferred ideas go in [FUTURE.md](./FUTURE.md), not into code.
Security rules in [SECURITY.md](./SECURITY.md) are mandatory.

## Project nature
- igomgoNodes is a **framework/base-class package**: node icon, ports, connection rules,
  feedback-loop policy, execution, editor UI, storage.
- Domain processing (audio DSP, image effects, circuits) belongs to **consumers**.
  Samples in `examples/` must stay small, readable proof-of-concepts.

## Architecture rules
- `src/igomgo_nodes/core/` has **no Streamlit, Supabase, or heavy numeric imports**.
- `ui/` depends on `core/`; `core/` never depends on `ui/` or `storage/`.
- Supabase is an **optional** dependency; the package must work without it. Default
  saving is anonymous and local (browser download/upload of graph JSON).
- Node `type_id`s are stable public identifiers — never rename without a migration.
- Saved graph JSON carries `schema_version`; bump it and add a migrator on breaking changes.
- Any feedback-enabled run **must** be executed as the unrolled "virtual spiral" and honor
  `LoopPolicy.max_iterations` and `timeout_seconds`. Never add an unbounded loop.

## Code conventions
- Python 3.11+, type hints everywhere, Pydantic v2 models for serializable data.
- Format/lint with `ruff`; type-check with Pyright/mypy; test with `pytest`.
- Keep Streamlit reruns cheap: cache via `st.cache_data`/`st.cache_resource` and the
  executor's result cache; keep large data out of `st.session_state` when possible.
- Comments only where logic is non-obvious.

## Testing
- Unit-test `core/` thoroughly: port limits, type checks, cycle detection, loop limits,
  serialization round-trips.
- Examples get smoke tests (graph builds, runs, produces output of expected shape).
- Never hit a real Supabase project in tests; mock the client or use a local store.

## Workflow
- Update [PROGRESS.md](./PROGRESS.md) when a milestone item changes status.
- Put new ideas or out-of-scope requests in [FUTURE.md](./FUTURE.md).
- Never commit secrets (`.streamlit/secrets.toml`, `.env`, service-role keys).

## Commands (Windows, from repo root)
Dev interpreter is Python 3.14 in a project venv; the package supports Python ≥ 3.11.
```powershell
py -3.14 -m venv .venv                      # once
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\ruff.exe check . ; .\.venv\Scripts\ruff.exe format .
.\.venv\Scripts\pyright.exe --pythonpath .\.venv\Scripts\python.exe
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\streamlit.exe run app.py
```
