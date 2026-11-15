# Consumer guide

igomgoNodes supplies graph models, port rules, a Streamlit editor, and bounded execution.
Your package defines the domain nodes and owns data acquisition, processing, and output
presentation. Keep domain work in consumer modules; the framework core has no media or
numeric-processing dependencies.

## Install

For a deployed consumer, use a tagged release instead of the mutable `main` branch:

```powershell
pip install "igomgonodes[ui] @ git+https://github.com/Sempai-Dami1/igomgoNodes.git@v0.1.0"
```

For development, install the current branch instead:

```powershell
pip install "igomgonodes[ui] @ git+https://github.com/Sempai-Dami1/igomgoNodes.git@main"
```

The repository is private: installation requires GitHub access for the account and
environment running Git. Never put credentials in the URL or commit them to a dependency
file. The `ui` extra installs Streamlit and the ready-made editor. Add your own processing
libraries in the consumer's dependency manifest.

## Write and run a node

Place consumer classes in an importable Python module. This small node doubles an external
numeric input; its optional single-capacity port can receive a runtime value without
putting that value in graph JSON.

```python
from collections.abc import Mapping

from igomgo_nodes.core import BaseNode, Executor, Graph, NodeInstance, NodeRegistry
from igomgo_nodes.core import NodeSpec, PortSpec


class Double(BaseNode):
    spec = NodeSpec(
        type_id="example.double",
        title="Double",
        category="Example",
        inputs=(PortSpec(name="value", dtype="float"),),
        outputs=(PortSpec(name="result", dtype="float"),),
    )

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        value = inputs["value"]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("Expected a numeric input")
        return {"result": float(value) * 2}


def main() -> None:
    registry = NodeRegistry()
    registry.register(Double)
    graph = Graph(nodes=(NodeInstance(node_id="double", type_id="example.double"),))
    result = Executor().run(graph, registry, inputs={"double": {"value": 21}})
    print(result.outputs["double"]["result"])  # 42.0


if __name__ == "__main__":
    main()
```

`BaseNode.process()` receives a mapping and must return exactly the declared output-port
names. A port with `max_connections=1` receives one value or `None`; multi-connection
ports receive ordered lists. Core validates graph connectivity and data types, while the
consumer validates domain values and implements processing.

Run files with the `__main__` guard shown above. The executor uses a spawned worker;
consumer classes must be defined at module scope so Windows and other spawn-based systems
can import them. Consumer classes and runtime payloads must support process transfer.
Consumer processing should raise an explicit error for invalid values rather than return
an empty or success-shaped result.

## Build a connected graph

Create one `NodeInstance` for each step, then connect declared output and input port names
with `Edge` objects:

```python
from igomgo_nodes.core import Edge

graph = Graph(
    nodes=(
        NodeInstance(node_id="first", type_id="example.source"),
        NodeInstance(node_id="second", type_id="example.transform"),
    ),
    edges=(
        Edge(
            edge_id="source-transform",
            src_node="first",
            src_port="value",
            dst_node="second",
            dst_port="value",
        ),
    ),
)
graph.validate_connections(registry)
graph.validate_feedback()
```

Each registered type ID is a stable identifier in saved files. Register every consumer
class explicitly; imported JSON never performs dynamic imports or instantiates a class
by itself. Graph files can contain incomplete editor state, so call both validation
methods before executing a graph.

For JSON-safe parameters, put defaults and constraints in a Pydantic `parameter_model`.
The editor and node construction validate these values. Keep large payloads, decoded media,
and runtime-only values out of `NodeInstance.params`; pass runtime values through
`Executor.run(..., inputs={node_id: {port_name: value}})` instead.

## Feedback

Cycles are disabled by default. To enable them, set one graph-level `GraphPolicy` with a
bounded `LoopPolicy`, then explicitly identify feedback edges. Removing the selected edges
must break every cycle:

```python
from igomgo_nodes.core import GraphPolicy, LoopPolicy

graph = graph.model_copy(
    update={
        "policy": GraphPolicy(
            allow_feedback=True,
            loop=LoopPolicy(max_iterations=5, timeout_seconds=10),
        )
    }
)
feedback_edge_ids = frozenset({"edge-that-closes-the-cycle"})
graph.validate_connections(registry)
graph.unroll(feedback_edge_ids=feedback_edge_ids)
result = Executor().run(graph, registry, feedback_edge_ids=feedback_edge_ids)
```

Feedback is executed as a finite virtual spiral, not a live cycle. External inputs enter
the first pass and the last completed pass supplies downstream outputs. The executor
enforces iteration, timeout, expansion, snapshot, and transfer limits. Audio sample-level
feedback mixing, if used, belongs in the consumer node and is separate from graph passes.

## Use the Streamlit editor and graph files

Install the `ui` extra and register the same consumer classes used by the executor:

```python
import streamlit as st
from igomgo_nodes.ui import EditorAdapter, render_editor

if "editor" not in st.session_state:
    st.session_state.editor = EditorAdapter(graph, registry)
render_editor(st.session_state.editor)
edited_graph = st.session_state.editor.graph
```

The demo gallery includes browser download/upload controls that preserve feedback-edge
selections. For a local application, `LocalJsonStore` writes validated `.igomgo.json`
files to a configured directory. Community Cloud has temporary shared server storage, so
use browser download/upload for a user's own files; do not treat the server disk as private
per-user storage.

For more API details and the ready-made examples, see the [README](../README.md) and
[concept](../CONCEPT.md). For security requirements, including graph-file limits and
trusted worker assumptions, see [SECURITY.md](../SECURITY.md).
