from collections.abc import Mapping

import pytest
from pydantic import BaseModel, Field, JsonValue

from examples.editor_demo import FeedbackNot
from igomgo_nodes.core import BaseNode, Edge, Graph, NodeInstance, NodeRegistry, NodeSpec, PortSpec


def _graph(
    source: PortSpec,
    target: PortSpec,
    pairs: tuple[tuple[str, str], ...] = (("s", "t"),),
    src_port: str = "out",
    dst_port: str = "in",
) -> tuple[Graph, NodeRegistry]:
    class Source(BaseNode):
        spec = NodeSpec(type_id="test.source", title="Source", outputs=(source,), max_inputs=0)

        def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
            raise AssertionError("Validation must not execute processing")

    class Target(BaseNode):
        spec = NodeSpec(type_id="test.target", title="Target", inputs=(target,), max_outputs=0)

        def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
            raise AssertionError("Validation must not execute processing")

    registry = NodeRegistry()
    registry.register(Source)
    registry.register(Target)
    source_ids = sorted({pair[0] for pair in pairs} or {"s"})
    target_ids = sorted({pair[1] for pair in pairs} or {"t"})
    nodes = tuple(NodeInstance(node_id=node_id, type_id="test.source") for node_id in source_ids)
    nodes += tuple(NodeInstance(node_id=node_id, type_id="test.target") for node_id in target_ids)
    edges = tuple(
        Edge(
            edge_id=f"edge-{index}",
            src_node=src,
            src_port=src_port,
            dst_node=dst,
            dst_port=dst_port,
        )
        for index, (src, dst) in enumerate(pairs)
    )
    return Graph(nodes=nodes, edges=edges), registry


@pytest.mark.parametrize(
    ("source_type", "target_type"),
    [("audio", "audio"), ("any", "image"), ("bool", "any")],
)
def test_matching_and_wildcard_types(source_type: str, target_type: str) -> None:
    graph, registry = _graph(
        PortSpec(name="out", dtype=source_type), PortSpec(name="in", dtype=target_type)
    )
    graph.validate_connections(registry)


def test_incompatible_types_are_rejected() -> None:
    graph, registry = _graph(
        PortSpec(name="out", dtype="audio"), PortSpec(name="in", dtype="image")
    )
    with pytest.raises(ValueError, match="edge-0.*incompatible.*audio -> image"):
        graph.validate_connections(registry)


@pytest.mark.parametrize(
    ("src_port", "dst_port", "error"),
    [("in", "in", "unknown output port s.in"), ("out", "out", "unknown input port t.out")],
)
def test_ports_must_exist_in_the_correct_direction(
    src_port: str, dst_port: str, error: str
) -> None:
    graph, registry = _graph(
        PortSpec(name="out", dtype="bool"),
        PortSpec(name="in", dtype="bool"),
        src_port=src_port,
        dst_port=dst_port,
    )
    with pytest.raises(ValueError, match=error):
        graph.validate_connections(registry)


@pytest.mark.parametrize("direction", ["input", "output"])
def test_connection_limit_at_boundary_and_above(direction: str) -> None:
    pairs = (("s1", "t"), ("s2", "t")) if direction == "input" else (("s", "t1"), ("s", "t2"))
    source = PortSpec(name="out", dtype="bool", max_connections=2)
    target = PortSpec(name="in", dtype="bool", max_connections=2)
    graph, registry = _graph(source, target, pairs)
    graph.validate_connections(registry)
    if direction == "input":
        target = PortSpec(name="in", dtype="bool", max_connections=1)
    else:
        source = PortSpec(name="out", dtype="bool", max_connections=1)
    graph, registry = _graph(source, target, pairs)
    with pytest.raises(ValueError, match=f"{direction} port .*2 connections, maximum is 1"):
        graph.validate_connections(registry)


def test_unlimited_fan_in_and_fan_out() -> None:
    pairs = (("s1", "t1"), ("s1", "t2"), ("s2", "t1"), ("s2", "t2"))
    graph, registry = _graph(
        PortSpec(name="out", dtype="bool", max_connections=None),
        PortSpec(name="in", dtype="bool", max_connections=None),
        pairs,
    )
    graph.validate_connections(registry)


@pytest.mark.parametrize("direction", ["input", "output"])
def test_zero_connection_limit(direction: str) -> None:
    source = PortSpec(name="out", dtype="bool", max_connections=0 if direction == "output" else 1)
    target = PortSpec(name="in", dtype="bool", max_connections=0 if direction == "input" else 1)
    graph, registry = _graph(source, target, ())
    graph.validate_connections(registry)
    graph, registry = _graph(source, target)
    with pytest.raises(ValueError, match=f"{direction} port .*maximum is 0"):
        graph.validate_connections(registry)


@pytest.mark.parametrize("direction", ["input", "output"])
def test_minimum_connections_include_unconnected_ports(direction: str) -> None:
    source = PortSpec(name="out", dtype="bool", min_connections=1 if direction == "output" else 0)
    target = PortSpec(name="in", dtype="bool", min_connections=1 if direction == "input" else 0)
    graph, registry = _graph(source, target)
    graph.validate_connections(registry)
    graph, registry = _graph(source, target, ())
    with pytest.raises(ValueError, match=f"{direction} port .*0 connections, minimum is 1"):
        graph.validate_connections(registry)


def test_counts_are_separate_for_each_node_instance() -> None:
    graph, registry = _graph(
        PortSpec(name="out", dtype="bool"),
        PortSpec(name="in", dtype="bool"),
        (("s1", "t1"), ("s2", "t2")),
    )
    graph.validate_connections(registry)


def test_unknown_node_type_is_rejected_even_without_edges() -> None:
    graph = Graph(nodes=(NodeInstance(node_id="unknown", type_id="unregistered"),))
    with pytest.raises(KeyError, match="Unknown node type: unregistered"):
        graph.validate_connections(NodeRegistry())


def test_named_ports_are_counted_independently_within_a_node() -> None:
    class Relay(BaseNode):
        spec = NodeSpec(
            type_id="test.relay",
            title="Relay",
            inputs=(PortSpec(name="a", dtype="bool"), PortSpec(name="b", dtype="bool")),
            outputs=(PortSpec(name="a", dtype="bool"), PortSpec(name="b", dtype="bool")),
            max_inputs=2,
            max_outputs=2,
        )

        def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
            raise AssertionError("Validation must not execute processing")

    registry = NodeRegistry()
    registry.register(Relay)
    graph = Graph(
        nodes=(
            NodeInstance(node_id="first", type_id="test.relay"),
            NodeInstance(node_id="second", type_id="test.relay"),
        ),
        edges=tuple(
            Edge(edge_id=name, src_node="first", src_port=name, dst_node="second", dst_port=name)
            for name in ("a", "b")
        ),
    )
    graph.validate_connections(registry)


def test_instance_input_limit_counts_connections_across_ports() -> None:
    class Params(BaseModel):
        limit: int = Field(default=2, ge=0, le=2, strict=True)

    class Relay(BaseNode):
        parameter_model = Params
        spec = NodeSpec(
            type_id="test.limited",
            title="Limited",
            inputs=(PortSpec(name="a", dtype="bool"), PortSpec(name="b", dtype="bool")),
            outputs=(PortSpec(name="out", dtype="bool", max_connections=None),),
        )

        @classmethod
        def input_connection_limit(cls, params: Mapping[str, JsonValue]) -> int:
            return Params.model_validate(params).limit

        def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
            raise AssertionError("Validation must not execute processing")

    registry = NodeRegistry()
    registry.register(Relay)
    graph = Graph(
        nodes=(
            NodeInstance(node_id="source", type_id="test.limited"),
            NodeInstance(node_id="target", type_id="test.limited", params={"limit": 2}),
        ),
        edges=tuple(
            Edge(edge_id=name, src_node="source", src_port="out", dst_node="target", dst_port=name)
            for name in ("a", "b")
        ),
    )
    graph.validate_connections(registry)
    target = graph.nodes[1].model_copy(update={"params": {"limit": 1}})
    limited = Graph(nodes=(graph.nodes[0], target), edges=graph.edges)
    with pytest.raises(ValueError, match="2 incoming connections, maximum is 1"):
        limited.validate_connections(registry)
    invalid = target.model_copy(update={"params": {"limit": 3}})
    with pytest.raises(ValueError, match="less than or equal to 2"):
        Graph(nodes=(graph.nodes[0], invalid), edges=graph.edges).validate_connections(registry)


def test_configured_direct_loopbacks_reject_two_feedback_values_to_one_port() -> None:
    class MultiOutput(FeedbackNot):
        spec = FeedbackNot.spec.model_copy(
            update={
                "type_id": "test.multi_output",
                "outputs": (
                    PortSpec(name="first", dtype="bool"),
                    PortSpec(name="second", dtype="bool"),
                ),
            }
        )

    registry = NodeRegistry()
    registry.register(MultiOutput)
    graph = Graph(
        nodes=(NodeInstance(node_id="stage", type_id="test.multi_output"),),
        edges=tuple(
            Edge(
                edge_id=port,
                src_node="stage",
                src_port=port,
                dst_node="stage",
                dst_port="value",
            )
            for port in ("first", "second")
        ),
    )
    with pytest.raises(ValueError, match="only one direct loopback"):
        graph.validate_connections(registry)
