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

class Edge:   src_node, src_port, dst_node, dst_port
class Graph:  nodes, edges, positions, policy: GraphPolicy, schema_version

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

### Execution
- No cycles → topological sort, run each node once.
- Cycles (feedback allowed) → find strongly connected components (SCCs), unroll each into
  the spiral above, then run the resulting acyclic graph in topological order.
- Results cached per node by hash of (params + input hashes) to keep Streamlit reruns fast.

## 4. Streamlit UI design

Streamlit has no native draggable-canvas widget. Recommendation:

- **Phase 1 (decided):** use [`streamlit-flow-component`](https://github.com/dkapur17/streamlit-flow)
  (React Flow wrapper) — supports drag, select, connect, node positions, and returns the
  updated graph state to Python. Wrap it behind an `EditorAdapter` interface so it can be
  swapped later. Known limitation: one source and one target handle per node (no
  per-port handles), so multi-port nodes map ports via edge metadata / the inspector panel.
- **Phase 2 (if needed):** custom Streamlit component (React Flow / Rete.js) for
  per-port handles, icons, port-limit enforcement on the client, and tap-to-select-then-tap-to-place
  on touch devices.

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

Interaction: mouse drag to reposition; on touch, **tap to select, tap empty canvas to
move** the selected node there. Positions are stored in the graph.

## 5. Visualization (proof-of-concept level)
- Audio: waveform via Plotly (downsampled for large files), `st.audio` playback, WAV export
  via `st.download_button`.
- Image: `st.image` for input and final output; optional per-stage thumbnails.
- Loop runs: chart of a chosen value over captured iterations.

## 6. Storage

### Decided: anonymous use, local saving
- No login. Every user is anonymous.
- On Streamlit Community Cloud the server disk is **temporary and shared by all users**,
  so "local" means **the user's own computer**:
  - **Save** → `st.download_button` downloads `my_graph.igomgo.json`.
  - **Load** → `st.file_uploader` reads that file back (validated before use).
  - Work in progress lives in `st.session_state` for the browser session only.
- When running locally (`streamlit run app.py`), `LocalJsonStore` can also save to a
  folder on disk.
- Package exposes a `GraphStore` interface; `BrowserFileStore` (download/upload) and
  `LocalJsonStore` (disk) ship in v0.1.

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
│  ├─ storage/     # GraphStore interface, local JSON store, Supabase store
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
