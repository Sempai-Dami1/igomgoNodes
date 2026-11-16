# Future / Deferred Ideas

Ideas parked here are **out of scope** until promoted into [PROGRESS.md](./PROGRESS.md).

## Editor
- Literal tap-select-then-tap-empty-canvas placement: deferred by agreement because the
  ready-made Python API does not expose pane-tap coordinates. Phase 3 uses inspector
  coordinates and directional touch buttons instead.
- Custom Streamlit component (React Flow / Rete.js) with per-port handles and client-side
  rule enforcement
- Edge rewiring gestures for a future custom canvas: double-click or double-tap a path and
  release without dragging to delete it. Hold the second press and drag to detach the
  destination while extending a new path from the original source to the pointer. Dropping
  on an empty area or invalid destination deletes the original connection; report invalid
  destinations to the user. Valid connections must still pass graph rules.
- Delete-key removal of a selected node or connection: the current canvas does not
  immediately report keyboard deletions to Streamlit. Until that is supported, use the
  on-screen delete controls.
- Sub-graphs / grouped nodes ("macro" nodes) with exposed ports
- Undo/redo, copy/paste, multi-select, snap-to-grid, minimap, auto-layout
- Comments/annotations on canvas; themes and icon packs
- Keyboard shortcuts; improved touch gestures (pinch zoom, long-press menu)

## Execution
- Manual global feedback stepping: one tap/click advances every feedback loop in the
  graph by one iteration, then pauses for inspection. This requires resumable execution
  state, a defined synchronization rule for connected cyclic groups, and reset/invalidation
  when the graph or inputs change. Iteration/time/resource caps still apply; advancing
  must not replay all earlier passes. Separate from audio sample-level feedback.
- Async / background execution with progress reporting and cancellation
- Partial re-execution (only dirty downstream nodes)
- Real-time / streaming audio (block-based) and live mic input
- Convergence-based loop termination (stop when change < epsilon)
- Per-edge delay semantics for feedback edges
- Worker offload for heavy consumers (Celery/RQ, Supabase Edge Functions, GPU)

## Domains
- Electronic circuit simulation (e.g. PySpice/ngspice integration)
- Video frame chains; 3D/shader nodes
- Consumer-defined mapping of spiral iterations to successive image/video frames,
  including AVI import/export (no video codec or frame acquisition in core)
- Optional MP4 capture/export for the image-feedback preview, after validating feedback
  and browser playback (no video encoding in the framework core).
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
