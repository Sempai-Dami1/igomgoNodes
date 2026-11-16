# igomgoNodes — Concept

## 1. Vision

igomgoNodes is a **Python package (framework / base classes)** for building node-based
editors that run in **Streamlit**. It defines *what a node is* (icon, ports, rules) and
*how nodes connect and execute*. It does **not** do heavy domain processing — the
package consumer (derived classes) does that.

```
 [Input node] ──► [Stage node] ──► [Stage node] ──► [Output node]
   gather data      process          process          display / play / export
```

Example domains (shipped only as light proof-of-concept samples):

| Domain | Input node | Stage nodes | Output node |
|---|---|---|---|
| Logic | constants, toggles | AND / OR / NOT / XOR | truth display |
| Audio (filter chain) | WAV upload | gain, low-pass, delay (feedback) | waveform graph + audio player + WAV export |
| 2D image (effect chain) | image upload | grayscale, blur, invert | image display + PNG export |
| Electronic components | source | resistor, LED (symbolic) | readout |

## 2. Responsibilities split

| Package (igomgoNodes) | Consumer (derived classes) |
|---|---|
| Node base class: id, title, icon, category, color | Concrete node types |
| Port definitions: name, data type, min/max connections | Port data types meaningful to the domain |
| Graph model: nodes, edges, positions | Input gathering (upload, mic, sensor, DB…) |
| Validation: port limits, type compatibility, cycle rules | `process()` implementation (the heavy lifting) |
| Executor: topological order, feedback-loop handling | Output rendering (chart, image, audio, file) |
| Serialization (versioned JSON) | Domain presets |
| Streamlit editor adapter (drag, select, connect) | Custom icons/themes |
| Storage interface + Supabase adapter | Their own Supabase project/credentials |

## 3. Core model (proposed)

The first implemented API is available from `igomgo_nodes.core`:
`PortSpec`, `NodeSpec`, `BaseNode`, and `NodeRegistry`.

Graph data is also implemented:

- `NodeInstance(node_id, type_id, params, position)` stores serializable instance data,
  separate from the consumer's processing class. `Position(x, y)` uses finite coordinates;
  each node stores its own position rather than using a separate position map.
- `Edge(edge_id, src_node, src_port, dst_node, dst_port)` identifies a directed connection.
- `Graph(nodes, edges, policy)` carries `schema_version=1` and rejects duplicate node IDs,
  duplicate edge IDs, identical connections, and endpoints referencing missing nodes.
  `graph.validate_connections(registry)` checks node types and directional port names
  against explicitly registered specs, exact data-type matches (`any` matches either side),
  and minimum/maximum connection counts on every input and output port.
  It raises `KeyError` for unknown node types and `ValueError` for invalid connections,
  without instantiating or executing consumer nodes. Minimums include unconnected ports.
  Graph construction still permits incomplete editing states; call validation before a run.
  Call `graph.validate_feedback()` separately to reject cycles when feedback is disabled.
  Both checks are required before execution; neither executes consumer processing.
- `graph.strongly_connected_components()` returns all components as tuples of node IDs,
  including isolated/acyclic singletons, in topological order between components.
  Multi-node components and self-loops are cycles. Detection uses iterative traversal so
  long graphs do not depend on Python's recursion limit.
- `GraphPolicy` defaults to feedback disabled. Enabling it requires `LoopPolicy`;
  providing loop settings while feedback is disabled is rejected.
- `LoopPolicy` requires a positive integer iteration limit, a finite positive timeout,
  and a positive integer capture interval (default 1). `Executor` enforces runtime and
  capture limits after virtual-spiral expansion; policy declarations alone do not run nodes.
- Graph models support Pydantic JSON round-trips. Unknown schema versions and unknown
  model fields are rejected. Raw audio/images do not belong in graph parameters.
  `params` dictionaries remain editable; frozen model fields and tuples prevent structural
  reassignment but do not deeply freeze parameter values.

- Specs reject unknown fields, empty identifiers, negative/non-integer limits, inverted
  connection ranges, duplicate port names within a direction, and declared ports exceeding
  node limits. `None` means unlimited; zero means none. Specs are immutable, with port tuples.
- `max_inputs`/`max_outputs` count declared ports, not connected edges; `NodeSpec` enforces
  these limits. Connection counts are checked separately per named port and node instance.
- Consumers can additionally implement `input_connection_limit(params)` to limit the total
  incoming edges across all ports on an instance. A direct self-loop counts as an incoming edge.
  The consumer's parameter model defines and validates any adjustable bounds.
- Consumers subclass `BaseNode`, declare a class-level `spec`, and implement
  `process(inputs: Mapping[str, object]) -> dict[str, object]`.
  Each instance has `node_id` and independently copied, JSON-compatible `params`.
  An optional class-level `parameter_model: type[BaseModel]` validates/defaults parameters
  both in the inspector and during node construction. The editor generates fields from its
  JSON schema; nodes without a parameter model use a JSON-object form.
- `NodeRegistry.register(MyNode)` accepts concrete classes with valid specs.
  `resolve(type_id)` returns only an explicitly registered class; duplicate and unknown
  identifiers raise errors. Registry state belongs to the consumer, not a global singleton.
- Execution context is implemented as `self.context`. The core has no rendering dependency.
- A consumer can opt into per-node direct self-loop behavior with
  `direct_loopback_mode(params)`: `replace` feeds the previous output into the target input;
  `add` delegates combining the first-pass input with that output to `combine_loopback`.
  The latter returns the input in the port's normal scalar/list shape. Other inputs still
  follow graph edges normally. Existing nodes that do not opt in retain the original behavior.
  Drawn self-loops still require graph-wide permission and selection as feedback boundaries.

### JSON interchange and versioning

- `dumps_graph(graph)` returns formatted JSON text. `loads_graph(text_or_utf8_bytes, registry)`
  returns a structurally validated graph and resolves all node type IDs through the registry,
  without instantiating or executing consumers.
- Imported documents must explicitly contain integer `schema_version: 1`; missing versions,
  booleans, floats, and unknown versions are rejected, rather than silently assumed/migrated.
  Programmatically constructed `Graph()` objects still default to version 1.
- Import/export enforce a 25 MiB UTF-8 limit, 10,000 nodes, and 100,000 edges.
  Imports reject duplicate JSON keys, non-finite numbers (including exponent overflow),
  malformed JSON, unknown model fields, invalid structure, and unsupported encodings.
  Exports revalidate mutable parameters and reject non-finite values.
- Incomplete editing states can be saved: minimum connections, port compatibility, and cycle
  permission are not run-readiness guarantees at import time. The executor checks these
  before processing. Unknown node types require the consumer to register its trusted module;
  JSON can never request a dynamic import.
- Version 1 is the first format, so there are no historical migrations. A future breaking
  change must bump the version and introduce an explicit, tested JSON-data migrator for each
  supported older version before accepting it. Unknown newer versions must remain rejected.

```python
class PortSpec:            # declared on node classes
    name: str
    dtype: str             # e.g. "audio", "image", "bool", "any"
    min_connections: int = 0
    max_connections: int | None = 1   # None = unlimited

class NodeSpec:            # class-level metadata
    type_id: str           # stable id used in saved graphs, e.g. "audio.lowpass"
    title: str
    icon: str              # emoji, material icon name, or SVG/data-URI
    category: str
    inputs: list[PortSpec]
    outputs: list[PortSpec]
    max_inputs: int | None # total input ports allowed (dynamic ports), None = unlimited
    max_outputs: int | None
    params: dict           # user-editable parameters (schema for UI form)

class BaseNode:            # consumers subclass this
    spec: ClassVar[NodeSpec]
    def process(self, inputs: dict[str, Any], ctx: RunContext) -> dict[str, Any]: ...
    def render(self, outputs, ctx) -> None: ...   # optional, for output/display nodes

class Position: x, y
class NodeInstance: node_id, type_id, params, position: Position
class Edge:   edge_id, src_node, src_port, dst_node, dst_port
class Graph:  nodes, edges, policy: GraphPolicy, schema_version

class GraphPolicy:              # one feedback permission for the whole graph
    allow_feedback: bool = False
    loop: LoopPolicy | None     # required when allow_feedback is True

class LoopPolicy:
    max_iterations: int        # number of spiral turns (unrolled passes)
    timeout_seconds: float     # wall-clock "timer" safety cap
    capture_every: int = 1     # snapshot every N iterations for inspection
```

### Rules the *system* defines
1. **Input limits** — per port (`max_connections`) and per node (`max_inputs`).
2. **Output limits** — per port fan-out and per node (`max_outputs`).
3. **Feedback loops** — a **single graph-level permission** (`allow_feedback`). No
   per-node or per-edge permissions. If `False`, any edge that would close a cycle is
   rejected. If `True`, a `LoopPolicy` is **mandatory**: iteration count + timeout.
4. **Type compatibility** — edges only between compatible `dtype`s (`any` matches all).

### Feedback as a "virtual spiral"
A consumer's processing API may not support true cycles. igomgoNodes therefore never
executes a real loop: a cycle is **unrolled into a finite chain** of `max_iterations`
passes. Each pass ("turn" of the spiral) runs the cyclic nodes once, and the edge that
closes the cycle feeds pass *k*'s output into pass *k+1*'s input.

```
 drawn graph:   A ──► B ──► C            executed (max_iterations = 3):
                      ▲     │            A ─► B₁ ─► C₁ ─► B₂ ─► C₂ ─► B₃ ─► C₃ ─► out
                      └─────┘
```

- The executed graph is always acyclic, so consumers only ever see a plain chain.
- The first pass receives the node's default / `None` on the feedback input.
- The run stops at `max_iterations` or `timeout_seconds`, whichever comes first; the
  result is the last completed pass and captured snapshots (every `capture_every` passes).
- Optional helper `Graph.unroll(n)` returns the expanded acyclic graph so a consumer can
  hand it to its own engine instead of using the built-in executor.

#### Implemented expansion contract

`graph.unroll(n=None, feedback_edge_ids=frozenset({...}))` returns a new acyclic graph.
It does not execute processing or enforce an elapsed-time budget.

- The consumer explicitly selects feedback edge IDs. This identifies iteration boundaries,
  not per-edge permission: the graph-wide feedback permission is still required.
  Selections must be inside cyclic components and their removal must break every cycle.
  There is no inference from node declaration order or visual position.
- Each cyclic component gets `n` copies of every member (default: `max_iterations`).
  `n` must be a positive integer and cannot exceed the original loop policy.
  Ordinary internal edges stay within a pass; selected edges connect pass k to pass k+1.
  Feedback is absent on the first pass and never wraps around from the final pass.
- External inputs enter only the first pass. Outputs leave only the last pass.
  Consecutive cyclic components therefore connect the first group's final pass to the
  second group's first pass. Acyclic nodes run only once.
- The first copy retains the original node ID; later copies use collision-safe IDs such
  as `node@2`. Parameters are deep-copied, type IDs and positions are preserved, and the
  original graph is unchanged. The returned graph has feedback disabled.
- Expansion is rejected before materializing copies above the default hard caps of
  10,000 nodes or 100,000 edges; it is never silently shortened.
- Connection validation belongs on the original graph. Missing inputs at pass boundaries
  need executor initialization handling; an expanded graph can intentionally lack the
  original required feedback input or external inputs on later passes.
- Retain the original graph's loop policy for execution timeout/capture enforcement;
  handing just the expanded graph to an external engine does not enforce those budgets.
- A consumer may interpret passes as successive 2D/video frames. Frame acquisition,
  time-dependent processing, and AVI encoding remain consumer responsibilities; iteration
  context for consumer processing will be addressed in the executor milestone.

### Execution
- Audio sample-level feedback is additive: the feedback contribution is added to the
  next input sample, not substituted for it. Delay/echo state, feedback gain, and sample
  mixing belong inside the consumer's audio node, not in the domain-neutral graph executor.
  Graph spiral iterations remain distinct from audio sample timing.
- No cycles → topological sort, run each node once.
- Cycles (feedback allowed) → find strongly connected components (SCCs), unroll each into
  the spiral above, then run the resulting acyclic graph in topological order.
- Planned: cache results per node by hash of (params + input hashes) to keep reruns fast.

#### Implemented executor contract

`Executor().run(graph, registry, feedback_edge_ids=..., inputs=...)` validates the original graph,
expands it, and processes the acyclic plan in a spawned worker process. Execution is
synchronous from the caller's perspective; this is not a background-job service.

- Consumer node classes must be importable module-level definitions (not local classes).
  Put them in a consumer module, rather than a Streamlit entry script or notebook cell.
  CLI callers must protect invocation with `if __name__ == "__main__":`.
  Registry classes and processing values must support multiprocessing transfer.
  Transfer is preflighted before allocating worker pipes or starting a process.
- Each expanded step gets a fresh node instance. Feedback state travels through edges,
  not mutable node-instance fields. `self.context` supplies `original_node_id`, one-based
  `iteration`, and configured `max_iterations` without changing the `process(inputs)` API.
- Ports with `max_connections=1` receive a scalar or `None` when disconnected.
  Other input ports receive ordered lists (empty when disconnected), following original
  edge order. Values are independently copied for consumers; core never sums/mixes them.
- Optional runtime `inputs` maps original node IDs to port/value mappings, keeping decoded
  media out of graph JSON. Only unconnected optional scalar ports can be supplied;
  unknown targets, connected ports and multi-connection ports are rejected. Values enter
  only the first pass and are copied independently before processing.
- Consumers must return exactly the declared output port keys. Processing/transfer failures
  raise explicit errors, not success-shaped empty results.
- `RunResult.outputs` maps original node IDs to the latest *completed component pass*.
  Partial passes are not published. `snapshots` captures full cyclic-component passes on
  multiples of `capture_every`. Acyclic nodes are executed once and are not loop snapshots.
- Timeout covers validation/planning, worker startup, and execution. Runtime is capped at
  the smaller of `LoopPolicy.timeout_seconds` and the 60-second server cap; acyclic runs
  also have the 60-second cap. On timeout, the worker is terminated and joined, and the
  result has `timed_out=True` with previously completed outputs/snapshots.
  Worker startup and shutdown have scheduling/cleanup overhead; this is not a real-time timer.
- Runs reject more than 1,000 scheduled snapshots, messages above 16 MiB, or retained
  outputs/snapshots above 16 MiB. These are transfer/retention bounds, not a sandbox or
  a hard operating-system memory limit on trusted consumer processing.
- Core per-node result caching is not implemented yet; consumer purity/hash semantics must
  be defined first. The example gallery separately caches decoded uploads and complete runs.

## 4. Streamlit UI design

Streamlit has no native draggable-canvas widget. Recommendation:

- **Phase 1 (decided):** use [`streamlit-flow-component`](https://github.com/dkapur17/streamlit-flow)
  (React Flow wrapper) — supports drag, select, connect, node positions, and returns the
  updated graph state to Python. Wrap it behind an `EditorAdapter` interface so it can be
  swapped later. Known limitation: one source and one target handle per node (no
  per-port handles), so multi-port nodes map ports via edge metadata / the inspector panel.
- **Phase 2 (if needed):** custom Streamlit component (React Flow / Rete.js) for
  per-port handles, icons, port-limit enforcement on the client, and tap-to-select-then-tap-to-place
  on touch devices (deferred; inspector movement is the accepted initial touch workflow).

Page layout:

```
┌ Sidebar ──────────┐┌ Canvas (node editor) ─────────────────────────────┐
│ Node palette      ││  drag / tap-select-move / connect                  │
│ Graph policy      ││                                                    │
│ (feedback, loops) │└────────────────────────────────────────────────────┘
│ Save / Load       │┌ Inspector (selected node) ┐┌ Preview ──────────────┐
│ (JSON file)       ││ params form, port info     ││ input image / waveform │
└───────────────────┘└────────────────────────────┘│ output image / waveform│
                                                    │ audio player, export   │
                                                    └────────────────────────┘
```

Interaction: mouse drag to reposition; on touch, **tap to select, then use inspector
X/Y or Left/Right/Up/Down controls**. Positions are stored in the graph. The ready-made
component does not expose empty-canvas tap coordinates through its Python API; literal
tap-select-then-tap-canvas placement is deferred to a custom component.

### Implemented editor

- `EditorAdapter(graph, registry)` owns the current graph, selection, canvas state and
  explicitly chosen feedback edge IDs. Store one per Streamlit session, then call
  `render_editor(adapter)`. Read accepted edits from `adapter.graph`.
- The palette lists `registry.node_types()` in registration order, grouped in labels by
  category. Add nodes with validated defaults or supplied parameters; deleting a node
  removes its attached edges.
- Drag connections directly only when both endpoint directions have exactly one named
  port. Multi-port connections use the Connections panel's node and port selectors.
  Existing named-port mappings survive canvas round-trips. Disconnect through the panel
  or delete an edge on the canvas.
- Edits are transactional: unknown ports, incompatible types, capacity overflow, duplicate
  connections and forbidden cycles show errors and leave the last valid graph untouched.
  Edit-time validation uses `validate_connections(..., require_minimums=False)` so users
  can build incomplete graphs. Default/core execution validation still enforces minimums.
- Feedback is toggled once per graph, with iteration, timeout and capture settings.
  Disabling feedback is rejected while cycles remain. Choose next-iteration edges
  explicitly in Connections; Apply feedback boundaries verifies every cycle is broken.
  These choices are session editor metadata, not yet persisted in graph JSON.
- The inspector displays port types and limits and generates boolean, numeric, text and
  inline-enum fields from a consumer parameter model. Nested/nullable/reference-based
  fields use JSON text; Pydantic validates the submitted values and constraints.
  Required parameters can be supplied in the palette before adding the node.
- `Validate graph` checks run readiness, parameter schemas and spiral boundaries without
  executing processing. The Phase 4 consumer gallery adds its own Run button and renderers.
- Selection and graph data persist across ordinary Streamlit reruns, not browser-session
  loss. Reload/download persistence belongs to the storage milestone.

## 5. Visualization (proof-of-concept level)
- Implemented in `examples/`, selected through the demo sidebar; processing stays outside
  the framework core. Each example has independent session editor state.
- Audio: generated sample or WAV upload, gain / low-pass / additive delay, input and
  output Plotly waveforms (maximum 2,000 points/channel), playback and PCM16 WAV export.
  Delay follows `y[n] = x[n] + feedback * y[n - delay_samples]` independently per channel.
  Length/sample rate are preserved with no appended tail; export/playback clip to [-1, 1],
  warning on overflow. Defaults feed the preceding output into the next sample.
- Image: generated sample or PNG/JPEG upload; grayscale / blur / invert with input and
  final RGB display, plus PNG export. EXIF orientation is applied; alpha is discarded.
- Logic: constant / NOT chain initially, with AND / OR / XOR available in the palette;
  output values shown as JSON. Electronics is a symbolic supply / resistor / LED readout.
- Upload limits: 5 MiB; audio nonempty and at most 5 seconds, mono/stereo, 8–48 kHz;
  images at most 262,144 pixels. Decoders check metadata limits before full decoding.
- Gallery previews/exports target the original media `input` and `output` node IDs.
  Missing/replaced originals fail explicitly. Uploads and complete executions use bounded
  Streamlit caches; session state keeps only editor data and the last-run fingerprint.
  Graph/input changes hide stale results until Run is clicked again.
- Captured loop passes are listed by component and iteration after execution. Manual
  graph-wide one-click iteration advancement is deferred in FUTURE.md; it requires
  resumable state and synchronization, not replay. Per-pass value charts and stage
  thumbnails remain future consumer enhancements.

## 6. Storage

### Decided: anonymous use, local saving
- No login. Every user is anonymous.
- On Streamlit Community Cloud the server disk is **temporary and shared by all users**,
  so "local" means **the user's own computer**:
  - **Save** → `st.download_button` downloads `my_graph.igomgo.json`.
  - **Load** → `st.file_uploader` reads that file back (validated before use).
  - Work in progress lives in `st.session_state` for the browser session only.
- When running locally (`streamlit run app.py`), `LocalJsonStore` can also save to a
  configured folder on disk, using an atomic file replacement.
- Implemented in `igomgo_nodes.storage`: the byte-oriented `GraphStore` interface,
  `BrowserFileStore` for download/upload bytes, and `LocalJsonStore` for local disk.
- The versioned editor document wraps unchanged schema-v1 graph JSON with the editor's
  selected feedback-edge IDs. It also imports core graph JSON documents without editor
  metadata. Both document forms use strict UTF-8/JSON, duplicate-key and non-finite-number
  checks, registry-only node types, and a 25 MiB whole-file cap.
- The gallery exposes browser download/upload. Import validates the complete document and
  candidate editor graph before replacing current state; failures leave it untouched.
  Community Cloud never writes graphs to its temporary shared server disk.
- `LocalJsonStore` confines names to simple `.igomgo.json` files inside its configured
  directory, rejects symbolic links, bounds reads, and replaces saves atomically. It is
  for local applications with a trusted directory, not shared-hosting persistence.

### Supabase (optional, later)
- `SupabaseStore` stays behind the same interface as an optional extra
  (`pip install "igomgonodes[supabase]"`).
- Anonymous-compatible option: Supabase **anonymous sign-ins** give each browser a
  temporary user id, so RLS still isolates data without asking for a login.
- Tables: `graphs` (id, owner_id, name, json, schema_version, timestamps); private buckets
  `inputs/` and `outputs/` with paths prefixed by `owner_id/`.

## 7. Proposed repository layout

```
igomgoNodes/
├─ src/igomgo_nodes/
│  ├─ core/        # ports, node, graph, policy, validation, executor, registry, serialization
│  ├─ ui/          # Streamlit editor adapter, inspector, preview helpers
│  ├─ storage/     # graph-file interface, browser transfer codec, local JSON store
│  └─ viz/         # small helpers: waveform plot, image panels
├─ examples/
│  ├─ logic/       # tiny logic gates demo
│  ├─ audio_poc/   # WAV in → gain/lowpass/delay → waveform + player + export
│  └─ image_poc/   # image in → grayscale/blur → display + export
├─ app.py          # Streamlit entry point (demo gallery)
├─ supabase/migrations/
├─ tests/
├─ pyproject.toml
└─ .streamlit/ (config.toml committed; secrets.toml NEVER committed)
```

`core/` must not import Streamlit, so it is testable and reusable outside the UI.

## 8. Tech stack (recommended)
- Python 3.11+ supported (developed on 3.14), Streamlit, `streamlit-flow-component`, Pydantic v2 (models + JSON schema),
  NumPy, SciPy (POC filters), Pillow, Plotly, `soundfile`.
- Tooling: `pip` + `pyproject.toml` (hatchling), `pytest`, `ruff`, Pyright.
- Deploy: Streamlit Community Cloud; secrets via Streamlit secrets manager.

## 9. Decisions

| # | Topic | Decision |
|---|---|---|
| 1 | Editor component | ✅ Start with `streamlit-flow-component` behind `EditorAdapter` |
| 2 | Feedback scope | ✅ Single graph-level permission; loops run as a bounded "virtual spiral" |
| 3 | Audio sample-level feedback (e.g. delay/echo) | ✅ Implemented inside the node; graph spiral is for whole-chain repeats |
| 4 | Users / saving | ✅ Anonymous use, save/load graph JSON to the user's computer |
| 5 | Distribution | ✅ Install from GitHub (`pip install "git+https://github.com/Sempai-Dami1/igomgoNodes.git@<tag>"`); PyPI deferred |
