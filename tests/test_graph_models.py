import pytest
from pydantic import ValidationError

from igomgo_nodes.core import Edge, Graph, GraphPolicy, LoopPolicy, NodeInstance, Position


def test_graph_round_trip_preserves_positions_parameters_and_feedback() -> None:
    node = NodeInstance(
        node_id="gain",
        type_id="audio.gain",
        params={"gain": 0.5, "options": {"enabled": True}},
        position=Position(x=-120.5, y=240),
    )
    graph = Graph(
        nodes=(node,),
        edges=(
            Edge(
                edge_id="feedback",
                src_node="gain",
                src_port="out",
                dst_node="gain",
                dst_port="in",
            ),
        ),
        policy=GraphPolicy(
            allow_feedback=True,
            loop=LoopPolicy(max_iterations=3, timeout_seconds=2.5, capture_every=2),
        ),
    )
    restored = Graph.model_validate_json(graph.model_dump_json())
    assert restored == graph
    assert restored.schema_version == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_iterations", 0),
        ("max_iterations", -1),
        ("max_iterations", 1.5),
        ("max_iterations", True),
        ("capture_every", 0),
        ("capture_every", False),
        ("timeout_seconds", 0),
        ("timeout_seconds", -1),
        ("timeout_seconds", float("inf")),
        ("timeout_seconds", float("nan")),
        ("timeout_seconds", True),
    ],
)
def test_invalid_loop_limits(field: str, value: object) -> None:
    data: dict[str, object] = {"max_iterations": 3, "timeout_seconds": 1.0}
    data[field] = value
    with pytest.raises(ValidationError):
        LoopPolicy.model_validate(data)


def test_feedback_requires_both_permission_and_limits() -> None:
    with pytest.raises(ValidationError, match="requires a LoopPolicy"):
        GraphPolicy(allow_feedback=True)
    with pytest.raises(ValidationError, match="requires feedback permission"):
        GraphPolicy(loop=LoopPolicy(max_iterations=1, timeout_seconds=1))
    with pytest.raises(ValidationError):
        GraphPolicy.model_validate({"allow_feedback": "false"})


@pytest.mark.parametrize("coordinate", [float("inf"), float("-inf"), float("nan")])
def test_positions_must_be_finite(coordinate: float) -> None:
    with pytest.raises(ValidationError):
        Position(x=coordinate)


@pytest.mark.parametrize("version", [0, 2, "1"])
def test_unknown_schema_versions_are_rejected(version: object) -> None:
    with pytest.raises(ValidationError):
        Graph.model_validate({"schema_version": version})


def test_duplicate_node_ids_are_rejected() -> None:
    node = NodeInstance(node_id="same", type_id="test")
    with pytest.raises(ValidationError, match="Duplicate node IDs"):
        Graph(nodes=(node, node))


def test_dangling_and_duplicate_edges_are_rejected() -> None:
    first = NodeInstance(node_id="first", type_id="test")
    second = NodeInstance(node_id="second", type_id="test")
    edge = Edge(edge_id="edge", src_node="first", src_port="out", dst_node="second", dst_port="in")
    with pytest.raises(ValidationError, match="unknown node"):
        Graph(nodes=(first,), edges=(edge,))
    with pytest.raises(ValidationError, match="Duplicate edge IDs"):
        Graph(nodes=(first, second), edges=(edge, edge))
    duplicate = Edge(
        edge_id="another", src_node="first", src_port="out", dst_node="second", dst_port="in"
    )
    with pytest.raises(ValidationError, match="Duplicate connection"):
        Graph(nodes=(first, second), edges=(edge, duplicate))


def test_instance_parameter_defaults_are_independent() -> None:
    first = NodeInstance(node_id="first", type_id="test")
    second = NodeInstance(node_id="second", type_id="test")
    first.params["gain"] = 2
    assert second.params == {}


def test_graph_data_rejects_unknown_fields_and_non_json_parameters() -> None:
    with pytest.raises(ValidationError):
        Graph.model_validate({"execute_code": "print('untrusted')"})
    with pytest.raises(ValidationError):
        NodeInstance.model_validate(
            {"node_id": "invalid", "type_id": "test", "params": {"data": object()}}
        )
