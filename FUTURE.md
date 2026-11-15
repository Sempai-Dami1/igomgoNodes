# Future / Deferred Ideas

Ideas parked here are **out of scope** until promoted into [PROGRESS.md](./PROGRESS.md).

## Editor
- Custom Streamlit component (React Flow / Rete.js) with per-port handles and client-side
  rule enforcement
- Sub-graphs / grouped nodes ("macro" nodes) with exposed ports
- Undo/redo, copy/paste, multi-select, snap-to-grid, minimap, auto-layout
- Comments/annotations on canvas; themes and icon packs
- Keyboard shortcuts; improved touch gestures (pinch zoom, long-press menu)

## Execution
- Async / background execution with progress reporting and cancellation
- Partial re-execution (only dirty downstream nodes)
- Real-time / streaming audio (block-based) and live mic input
- Convergence-based loop termination (stop when change < epsilon)
- Per-edge delay semantics for feedback edges
- Worker offload for heavy consumers (Celery/RQ, Supabase Edge Functions, GPU)

## Domains
- Electronic circuit simulation (e.g. PySpice/ngspice integration)
- Video frame chains; 3D/shader nodes
- Data-pipeline / ETL nodes; ML inference nodes
- Sandboxed user-scripted code nodes

## Collaboration & storage
- Supabase cloud storage: `SupabaseStore`, anonymous sign-ins, RLS, private
  `inputs`/`outputs` buckets (deferred in favor of anonymous local saving)
- Sharing graphs (public links, read-only), versions/history, templates gallery
- Realtime multi-user editing via Supabase Realtime
- Export/import graph files; export to Python script

## Packaging
- Publish to PyPI once the API is stable (currently installed from GitHub tags)
- Plugin discovery via entry points (`igomgo_nodes.plugins`)
- Docs site (MkDocs) with consumer tutorials
