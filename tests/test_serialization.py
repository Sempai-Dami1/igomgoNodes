import json
from collections.abc import Mapping

import pytest
from pydantic import ValidationError

from igomgo_nodes.core import (
    BaseNode,
    Edge,
    Graph,
    GraphPolicy,
    LoopPolicy,
    NodeInstance,
    NodeRegistry,
    NodeSpec,
    PortSpec,
    Position,
    dumps_graph,
    loads_graph,
)
from igomgo_nodes.core.serialization import MAX_GRAPH_BYTES


class SerializableNode(BaseNode):
    spec = NodeSpec(
        type_id="test.serializable",
        title="Serializable",
        inputs=(PortSpec(name="in", dtype="any", min_connections=1),),
        outputs=(PortSpec(name="out", dtype="any"),),
    )

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        raise AssertionError("Import/export must not execute nodes")


def _registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register(SerializableNode)
    return registry


@pytest.mark.parametrize("as_bytes", [False, True])
def test_round_trip_preserves_graph_and_does_not_run_processing(as_bytes: bool) -> None:
    graph = Graph(
        nodes=(
            NodeInstance(
                node_id="node",
                type_id="test.serializable",
                position=Position(x=-10.5, y=42),
                params={"nested": [None, True, {"gain": 0.5}], "label": "\u97f3"},
            ),
        ),
        edges=(
            Edge(
                edge_id="feedback", src_node="node", src_port="out", dst_node="node", dst_port="in"
            ),
        ),
        policy=GraphPolicy(
            allow_feedback=True, loop=LoopPolicy(max_iterations=3, timeout_seconds=2)
        ),
    )
    text = dumps_graph(graph)
    assert json.loads(text)["schema_version"] == 1
    assert loads_graph(text.encode("utf-8") if as_bytes else text, _registry()) == graph


def test_incomplete_editing_state_can_be_saved_and_loaded() -> None:
    graph = Graph(nodes=(NodeInstance(node_id="node", type_id="test.serializable"),))
    restored = loads_graph(dumps_graph(graph), _registry())
    with pytest.raises(ValueError, match="minimum is 1"):
        restored.validate_connections(_registry())


@pytest.mark.parametrize("version", [None, 0, 2, True, 1.0, "1"])
def test_version_is_required_and_must_be_supported_integer(version: object) -> None:
    document = {} if version is None else {"schema_version": version}
    with pytest.raises(ValueError, match="schema_version"):
        loads_graph(json.dumps(document), _registry())


@pytest.mark.parametrize(
    "text",
    [
        "[]",
        "null",
        "{",
        '{"schema_version":1,"schema_version":1}',
        '{"schema_version":1,"nodes":{}}',
        '{"schema_version":1,"unexpected":true}',
        '{"schema_version":1,"nodes":[{"node_id":"x","type_id":"test.serializable","params":{"x":NaN}}]}',
        '{"schema_version":1,"nodes":[{"node_id":"x","type_id":"test.serializable","params":{"x":1e999}}]}',
        '{"schema_version":1,"nodes":[{"node_id":"x","type_id":"test.serializable","params":{"x":1,"x":2}}]}',
    ],
)
def test_malformed_or_ambiguous_documents_are_rejected(text: str) -> None:
    with pytest.raises(ValueError):
        loads_graph(text, _registry())


def test_unknown_types_and_dangling_edges_are_rejected() -> None:
    text = '{"schema_version":1,"nodes":[{"node_id":"x","type_id":"unregistered"}]}'
    with pytest.raises(KeyError, match="Unknown node type"):
        loads_graph(text, _registry())
    with pytest.raises(ValidationError, match="unknown node"):
        loads_graph(
            '{"schema_version":1,"edges":[{"edge_id":"e","src_node":"x","src_port":"out",'
            '"dst_node":"y","dst_port":"in"}]}',
            _registry(),
        )


def test_utf8_is_required() -> None:
    with pytest.raises(UnicodeDecodeError):
        loads_graph(b"\xff", _registry())


def test_import_byte_limit_at_boundary_and_above() -> None:
    prefix = b'{"schema_version":1}'
    at_limit = prefix + b" " * (MAX_GRAPH_BYTES - len(prefix))
    assert loads_graph(at_limit, _registry()) == Graph()
    with pytest.raises(ValueError, match="25 MiB"):
        loads_graph(at_limit + b" ", _registry())


def test_export_size_and_mutated_nonfinite_parameters_are_rejected() -> None:
    graph = Graph(nodes=(NodeInstance(node_id="x", type_id="test.serializable", params={"x": ""}),))
    overhead = len(dumps_graph(graph).encode("utf-8"))
    graph.nodes[0].params["x"] = "a" * (MAX_GRAPH_BYTES - overhead)
    assert len(dumps_graph(graph).encode("utf-8")) == MAX_GRAPH_BYTES
    graph.nodes[0].params["x"] = "a" * (MAX_GRAPH_BYTES - overhead + 1)
    with pytest.raises(ValueError, match="25 MiB"):
        dumps_graph(graph)
    graph.nodes[0].params["x"] = float("nan")
    with pytest.raises(ValueError):
        dumps_graph(graph)


@pytest.mark.parametrize(("collection", "limit"), [("nodes", 10_000), ("edges", 100_000)])
def test_oversized_collections_are_rejected_before_model_validation(
    collection: str, limit: int
) -> None:
    document = {"schema_version": 1, collection: [None] * (limit + 1)}
    with pytest.raises(ValueError, match=f"{limit}-{collection} limit"):
        loads_graph(json.dumps(document), _registry())
