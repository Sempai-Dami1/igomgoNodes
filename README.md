# igomgoNodes
Graphical nodes that can represent a process, logical flow, input-output system, script/code blocks. The user can allow multiple inputs and outputs and also allow/deny a feedback loop. Initial usage will be for sound filters chain, 2D chain effect , electronic components.

## Install (consumers)
Installed directly from GitHub (no PyPI release yet). Pin the release tag:

```
pip install "igomgonodes @ git+https://github.com/Sempai-Dami1/igomgoNodes.git@v0.1.0"
```

The repository is private, so Git must have authorized access in the installing
environment. Never put credentials in the URL or commit them to a dependency file.

## Documentation
- [CONCEPT.md](./CONCEPT.md) — vision, architecture, core model, UI and storage design
- [PROGRESS.md](./PROGRESS.md) — roadmap and status
- [Consumer guide](./docs/consumer-guide.md) — install, implement a node, build and run a graph
- [AGENTS.md](./AGENTS.md) — rules for contributors and AI agents
- [SECURITY.md](./SECURITY.md) — security policy and requirements
- [FUTURE.md](./FUTURE.md) — deferred features and ideas

## Define a consumer node

The core does not import Streamlit or processing libraries. Consumers implement processing:

```python
from collections.abc import Mapping

from igomgo_nodes.core import BaseNode, NodeRegistry, NodeSpec, PortSpec


class NotNode(BaseNode):
    spec = NodeSpec(
        type_id="logic.not",
        title="NOT",
        inputs=(PortSpec(name="value", dtype="bool"),),
        outputs=(PortSpec(name="result", dtype="bool", max_connections=None),),
    )

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        return {"result": not inputs["value"]}


registry = NodeRegistry()
registry.register(NotNode)
node = registry.resolve("logic.not")("my-node")
assert node.process({"value": True}) == {"result": False}
```

`None` means unlimited connections; `0` means none. Invalid declarations and duplicate
type registrations raise errors.

For a `Graph`, call `graph.validate_connections(registry)` before running it to check
registered node types, input/output port names, data-type compatibility, and minimum/maximum
connections. `any` is the wildcard data type. Node-level `max_inputs`/`max_outputs` limit the
number of declared ports, not edges. Validation raises explicit errors and never runs
consumer processing.

Also call `graph.validate_feedback()` to reject cycles (including self-loops) when the
graph-wide feedback permission is disabled. Enabling feedback requires a `LoopPolicy`
with iteration and timeout limits. `graph.strongly_connected_components()` identifies
cyclic groups and acyclic singletons.

Expand permitted cycles using `graph.unroll(feedback_edge_ids=frozenset({"feedback-edge"}))`.
Consumers explicitly choose the connections that feed the next pass. All cycles must be
broken by those choices. The default pass count is `LoopPolicy.max_iterations`; supplying
`n` can reduce but not exceed it. External inputs feed the first pass, and outputs come from
the final pass. Expansion caps are 10,000 nodes and 100,000 edges.

Expansion alone does not run processing or enforce a timeout. Keep the original loop
policy when using your own engine.

## Execute a graph

```python
from igomgo_nodes.core import Executor

result = Executor().run(graph, registry, feedback_edge_ids=frozenset({"feedback-edge"}))
if result.timed_out:
    print("Stopped at timeout; only completed passes are available.")
print(result.outputs)
```

Define consumer classes in importable modules; spawned workers cannot use local classes.
For CLI scripts, guard execution with `if __name__ == "__main__":`. Streamlit entry scripts
should import consumer classes rather than define them. Inputs with capacity one receive a
scalar (or `None`); multi-connection inputs receive an ordered list. Mixing belongs to the
consumer. Audio feedback adds to the next sample inside the audio node.

Pass decoded media separately from graph JSON using
`Executor().run(graph, registry, inputs={"input": {"data": payload}})`.
Runtime inputs target original node IDs and unconnected, optional, single-capacity input
ports only. They are independently copied and supplied on the first pass, never persisted
in graph parameters. Consumer classes and payloads are checked for process transfer before
worker startup.

`self.context` exposes original node ID and iteration. Outputs use original node IDs;
snapshots include only complete component passes. Timeouts terminate the worker and set
`timed_out=True`. The server caps runs at 60 seconds, 1,000 snapshots and 16 MiB of retained
results. Consumer errors raise `ExecutionError`. See [CONCEPT.md](./CONCEPT.md) for details.

## Import and export graph JSON

```python
from igomgo_nodes.core import dumps_graph, loads_graph

text = dumps_graph(graph)  # download/save this as my_graph.igomgo.json
restored = loads_graph(text, registry)  # also accepts UTF-8 bytes from an upload
```

Documents require `schema_version: 1` and registered node types. Import/export enforce
25 MiB, 10,000 nodes, and 100,000 edges. Duplicate JSON keys, non-finite numbers, unknown
versions, and invalid graph structure raise errors. No processing runs during import.
Incomplete graphs remain saveable; call connection/feedback validation before executing.
Schema v1 has no older migrations; future breaking formats require explicit migrators.

## Streamlit editor

Run the demo from the repository root:

```powershell
.\.venv\Scripts\streamlit.exe run app.py
```

The sidebar palette adds nodes; the inspector edits parameters and moves/deletes the
selected node. Click or tap a node or connection to highlight it red, then use the
on-screen delete control to remove it. Deleting a node also removes its connections.
Drag single-port connections on the canvas or select named ports in Connections.
Keyboard Delete is not supported; use the on-screen controls. Invalid connections show
errors without changing the graph. Feedback must
be enabled in Graph policy before closing a cycle; explicitly select the next-iteration
connections afterward. Validate graph checks readiness without executing it.

Use **Download graph** and **Load graph** in the sidebar to save or restore the editor
state on your own computer. The versioned editor file contains the core graph JSON and
its selected feedback boundaries. Loading is validated against the current consumer
registry and applied transactionally; an invalid file leaves the current graph untouched.
Core `dumps_graph` / `loads_graph` JSON files can also be loaded.

For your own Streamlit consumer:

```python
import streamlit as st
from igomgo_nodes.ui import EditorAdapter, render_editor

if "graph_editor" not in st.session_state:
    st.session_state.graph_editor = EditorAdapter(graph, registry)
render_editor(st.session_state.graph_editor)
edited_graph = st.session_state.graph_editor.graph
```

Install the `ui` extra for this optional interface. Consumers can declare a Pydantic
`parameter_model` on their `BaseNode` subclass to generate inspector/palette fields and
validate parameters during processing construction. Without it, parameters use a JSON form.

Touch movement uses tap-to-select followed by X/Y or directional inspector controls.
Tap-on-empty-canvas placement needs a custom component and is deferred. The gallery's
browser file controls download/upload graph documents; there is no server-side per-user
save on Community Cloud.

For applications that run locally, the optional `LocalJsonStore` writes validated files
inside one configured directory using atomic replacement and rejects path separators,
symlinks, and oversized files:

```python
from igomgo_nodes.storage import LocalJsonStore

store = LocalJsonStore("saved_graphs")
store.save(graph, feedback_edge_ids=editor.feedback_edge_ids)
document = store.load(registry)
```

`BrowserFileStore.serialize(graph, feedback_edge_ids)` returns download-ready bytes;
`deserialize(data, registry)` returns a `GraphDocument`. This file wrapper preserves
feedback-edge selections without changing the core graph schema. The local store's
default directory is `saved_graphs/` and is ignored by Git.

## Small runnable examples

Select **Logic**, **Audio**, **Audio feedback**, **Image**, **Image feedback**, or **Electronics** in the sidebar,
edit the chain, then click **Run graph**. Audio and image examples start with generated samples;
upload your own WAV or PNG/JPEG to replace them.

- Audio: gain, low-pass and additive sample delay; input/output waveform and playback;
  WAV download. Delay follows `y[n] = x[n] + feedback * y[n - delay_samples]`, preserves
  the original length, and does not append an echo tail. Playback/export clips to [-1, 1]
  with a warning if needed.
- Audio feedback: a generated short tone passes through an additive direct graph self-loop.
  Eight graph passes produce up to seven echoes, 300 ms apart and halving in amplitude
  by default. Delay and feedback can be adjusted on the echo node. Output preserves the
  input duration, so later echoes are truncated, including for uploaded audio. Only the
  final pass is captured to limit memory use.
- Image: grayscale, blur and invert; input/final RGB previews and PNG download.
- Image feedback: generated 64×64 image → feedback blur → PNG output. The blur feeds its
  previous result back for 32 graph passes. Review captured passes using Previous/Next,
  the iteration slider, or browser playback (32 frames per second by default). Uploaded
  images are reduced to fit within 64×64, preserving aspect ratio. Preview frames are
  held in memory for the completed run and sent to the browser; no frame or video files
  are saved. PNG download contains the final pass.
- Logic: Boolean constants, NOT, AND, OR and XOR; inspect node output values.
- Electronics: supply/resistor/LED labels only, not a circuit simulator.

Uploads are limited to 5 MiB. WAVs must be nonempty, at most 5 seconds, mono/stereo,
and 8–48 kHz; images are limited to 262,144 pixels. Waveform charts display at most
2,000 points per channel. The gallery caches decoded inputs and complete runs, not
individual processing stages; changing the graph or input hides stale output until rerun.
Keep the media demo's original `input` and `output` nodes for its preview/export wiring.
Processing and rendering live in [examples/](./examples/), not the framework core.

Captured feedback passes can be listed after a run. One-click advancement of **all**
feedback loops is recorded in [FUTURE.md](./FUTURE.md); it needs resumable execution and
is not implemented as replaying earlier passes.
