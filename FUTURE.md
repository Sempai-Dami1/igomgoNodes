# Future / Deferred Ideas

Ideas parked here are **out of scope** until promoted into [PROGRESS.md](./PROGRESS.md).

## Editor
- Literal tap-select-then-tap-empty-canvas placement: deferred by agreement because the
  ready-made Python API does not expose pane-tap coordinates. Phase 3 uses inspector
  coordinates and directional touch buttons instead.
- Custom Streamlit component (React Flow / Rete.js) with per-port handles and client-side
  rule enforcement
- Focus-mode node navigation: double-click a node in Canvas to select it and open the
  Node tab. The current canvas component does not expose a double-click event; evaluate
  double-tap support separately when the canvas is replaced.
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

### Per-node iteration limits for direct feedback loops

Implemented. See [PROGRESS.md](./PROGRESS.md) for verification.

Requested by ImageLab on 2026-11-26. The owner verified that Setup controls
the graph-wide feedback count and the node inspector controls blur strength.
The request puts the loop count alongside the active loop in the inspector.

- Offer **Use graph default** or a custom **Maximum iterations** for an active
  direct self-loop. Independent self-loops can use different counts and each
  sends its last completed result downstream.
- Proposed storage is an optional framework-owned field on the node instance.
  Older saved graphs without the field use the graph-wide count. ImageLab's
  blur strength remains a consumer parameter.
- Keep multi-node cycles, capture frequency, timeout, and memory limits under
  the graph-wide policy.
- The graph maximum is both the inherited count and the ceiling. A custom
  count must be an integer from 1 through that maximum. Reject a graph
  maximum below an existing override and identify the affected node.
- Acceptance: run two independent loops with 3 and 8 passes, verify their
  downstream outputs, and save and reopen the graph to verify both overrides.
  Open a pre-override graph and verify the graph default still applies.
  Smoke-test the inspector control in ImageLab with Feedback blur.

AudioLab can add a use case here when one is identified.

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
