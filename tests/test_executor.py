import multiprocessing
import time
from collections.abc import Mapping

import pytest

from igomgo_nodes.core import (
    BaseNode,
    Edge,
    ExecutionError,
    Executor,
    Graph,
    GraphPolicy,
    LoopPolicy,
    NodeInstance,
    NodeRegistry,
    NodeSpec,
    PortSpec,
)


class Constant(BaseNode):
    spec = NodeSpec(
        type_id="test.constant",
        title="Constant",
        outputs=(PortSpec(name="out", dtype="number", max_connections=None),),
    )

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        return {"out": self.params["value"]}


class Add(BaseNode):
    spec = NodeSpec(
        type_id="test.add",
        title="Add",
        inputs=(PortSpec(name="in", dtype="number", max_connections=None),),
        outputs=(PortSpec(name="out", dtype="number", max_connections=None),),
    )

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        values = inputs["in"]
        assert isinstance(values, list)
        assert all(isinstance(value, int) for value in values)
        return {"out": sum(value for value in values if isinstance(value, int)) + 1}


class Scalar(BaseNode):
    spec = NodeSpec(
        type_id="test.scalar",
        title="Scalar",
        inputs=(PortSpec(name="in", dtype="number"),),
        outputs=(PortSpec(name="out", dtype="number", max_connections=None),),
    )

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        return {"out": inputs["in"]}


class Ordered(BaseNode):
    spec = NodeSpec(
        type_id="test.ordered",
        title="Ordered",
        inputs=(PortSpec(name="in", dtype="number", max_connections=None),),
        outputs=(PortSpec(name="out", dtype="any"),),
    )

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        return {"out": inputs["in"]}


class Stuck(BaseNode):
    spec = NodeSpec(
        type_id="test.stuck", title="Stuck", inputs=(PortSpec(name="in", dtype="number"),)
    )

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        time.sleep(30)
        return {}


class Broken(BaseNode):
    spec = NodeSpec(type_id="test.broken", title="Broken")

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        raise ValueError("consumer failure")


class WrongOutput(BaseNode):
    spec = NodeSpec(type_id="test.wrong", title="Wrong")

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        return {"unknown": 1}


class Iteration(BaseNode):
    spec = NodeSpec(
        type_id="test.iteration",
        title="Iteration",
        inputs=(PortSpec(name="in", dtype="number"),),
        outputs=(PortSpec(name="out", dtype="number"),),
    )

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        assert self.context is not None
        assert self.context.original_node_id == "iteration"
        return {"out": self.context.iteration}


class LargeOutput(BaseNode):
    spec = NodeSpec(
        type_id="test.large", title="Large", outputs=(PortSpec(name="out", dtype="any"),)
    )

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        size = self.params.get("size", 17 * 1024 * 1024)
        assert isinstance(size, int)
        return {"out": bytes(size)}


class PauseIteration(Iteration):
    spec = NodeSpec(
        type_id="test.pause",
        title="Pause",
        inputs=(PortSpec(name="in", dtype="number"),),
        outputs=(PortSpec(name="out", dtype="number"),),
    )

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        assert self.context is not None
        if self.context.iteration == 2:
            time.sleep(30)
        return super().process(inputs)


def _registry() -> NodeRegistry:
    registry = NodeRegistry()
    for node_type in (
        Constant,
        Add,
        Scalar,
        Ordered,
        Stuck,
        Broken,
        WrongOutput,
        Iteration,
        LargeOutput,
        PauseIteration,
    ):
        registry.register(node_type)
    return registry


def _edge(edge_id: str, src: str, dst: str) -> Edge:
    return Edge(edge_id=edge_id, src_node=src, src_port="out", dst_node=dst, dst_port="in")


def test_topological_execution_and_ordered_fan_in() -> None:
    graph = Graph(
        nodes=(
            NodeInstance(node_id="target", type_id="test.ordered"),
            NodeInstance(node_id="first", type_id="test.constant", params={"value": 2}),
            NodeInstance(node_id="second", type_id="test.constant", params={"value": 3}),
        ),
        edges=(
            _edge("second-target", "second", "target"),
            _edge("first-target", "first", "target"),
        ),
    )
    result = Executor().run(graph, _registry())
    assert not result.timed_out
    assert result.outputs["target"] == {"out": [3, 2]}
    assert result.snapshots == []


def test_feedback_is_additive_in_consumer_with_complete_pass_snapshots() -> None:
    graph = Graph(
        nodes=(
            NodeInstance(node_id="source", type_id="test.constant", params={"value": 5}),
            NodeInstance(node_id="add", type_id="test.add"),
            NodeInstance(node_id="relay", type_id="test.scalar"),
            NodeInstance(node_id="target", type_id="test.scalar"),
        ),
        edges=(
            _edge("entry", "source", "add"),
            _edge("stage", "add", "relay"),
            _edge("feedback", "relay", "add"),
            _edge("exit", "relay", "target"),
        ),
        policy=GraphPolicy(
            allow_feedback=True,
            loop=LoopPolicy(max_iterations=4, timeout_seconds=10, capture_every=2),
        ),
    )
    result = Executor().run(graph, _registry(), feedback_edge_ids=frozenset({"feedback"}))
    assert not result.timed_out
    assert result.outputs["target"] == {"out": 9}
    assert [snapshot.iteration for snapshot in result.snapshots] == [2, 4]
    assert result.snapshots[0].outputs == {"add": {"out": 7}, "relay": {"out": 7}}
    assert result.snapshots[1].outputs == {"add": {"out": 9}, "relay": {"out": 9}}


def test_context_and_missing_first_feedback_value() -> None:
    graph = Graph(
        nodes=(NodeInstance(node_id="iteration", type_id="test.iteration"),),
        edges=(_edge("feedback", "iteration", "iteration"),),
        policy=GraphPolicy(
            allow_feedback=True, loop=LoopPolicy(max_iterations=3, timeout_seconds=10)
        ),
    )
    result = Executor().run(graph, _registry(), feedback_edge_ids=frozenset({"feedback"}))
    assert [snapshot.outputs["iteration"]["out"] for snapshot in result.snapshots] == [1, 2, 3]
    missing = Graph(nodes=(NodeInstance(node_id="empty", type_id="test.scalar"),))
    assert Executor().run(missing, _registry()).outputs["empty"] == {"out": None}


@pytest.mark.parametrize(
    ("type_id", "error"),
    [("test.broken", "consumer failure"), ("test.wrong", "exactly output ports")],
)
def test_consumer_errors_are_explicit(type_id: str, error: str) -> None:
    graph = Graph(nodes=(NodeInstance(node_id="bad", type_id=type_id),))
    with pytest.raises(ExecutionError, match=error):
        Executor().run(graph, _registry())


def test_timeout_terminates_stuck_worker_and_preserves_completed_outputs() -> None:
    graph = Graph(
        nodes=(
            NodeInstance(node_id="constant", type_id="test.constant", params={"value": 2}),
            NodeInstance(node_id="stuck", type_id="test.stuck"),
        ),
        edges=(_edge("dependency", "constant", "stuck"),),
        policy=GraphPolicy(
            allow_feedback=True, loop=LoopPolicy(max_iterations=1, timeout_seconds=3)
        ),
    )
    before = {child.pid for child in multiprocessing.active_children()}
    started = time.monotonic()
    result = Executor().run(graph, _registry())
    assert result.timed_out
    assert time.monotonic() - started < 8
    assert result.outputs["constant"] == {"out": 2}
    assert {child.pid for child in multiprocessing.active_children()} == before


def test_oversized_worker_results_fail_explicitly() -> None:
    graph = Graph(nodes=(NodeInstance(node_id="large", type_id="test.large"),))
    with pytest.raises(ExecutionError, match="16 MiB"):
        Executor().run(graph, _registry())


def test_snapshot_count_is_bounded_before_processing() -> None:
    graph = Graph(
        nodes=(NodeInstance(node_id="iteration", type_id="test.iteration"),),
        edges=(_edge("feedback", "iteration", "iteration"),),
        policy=GraphPolicy(
            allow_feedback=True, loop=LoopPolicy(max_iterations=1001, timeout_seconds=10)
        ),
    )
    with pytest.raises(ExecutionError, match="1000-snapshot limit"):
        Executor().run(graph, _registry(), feedback_edge_ids=frozenset({"feedback"}))


def test_snapshot_count_at_exact_limit() -> None:
    graph = Graph(
        nodes=(NodeInstance(node_id="iteration", type_id="test.iteration"),),
        edges=(_edge("feedback", "iteration", "iteration"),),
        policy=GraphPolicy(
            allow_feedback=True, loop=LoopPolicy(max_iterations=1000, timeout_seconds=30)
        ),
    )
    result = Executor().run(graph, _registry(), feedback_edge_ids=frozenset({"feedback"}))
    assert not result.timed_out
    assert len(result.snapshots) == 1000
    assert result.outputs["iteration"] == {"out": 1000}


def test_combined_retained_results_are_bounded() -> None:
    graph = Graph(
        nodes=tuple(
            NodeInstance(
                node_id=f"large-{index}", type_id="test.large", params={"size": 9 * 1024 * 1024}
            )
            for index in range(2)
        )
    )
    with pytest.raises(ExecutionError, match="retained result limit"):
        Executor().run(graph, _registry())


def test_timeout_does_not_publish_partial_feedback_pass() -> None:
    graph = Graph(
        nodes=(NodeInstance(node_id="iteration", type_id="test.pause"),),
        edges=(_edge("feedback", "iteration", "iteration"),),
        policy=GraphPolicy(
            allow_feedback=True, loop=LoopPolicy(max_iterations=3, timeout_seconds=3)
        ),
    )
    result = Executor().run(graph, _registry(), feedback_edge_ids=frozenset({"feedback"}))
    assert result.timed_out
    assert result.outputs["iteration"] == {"out": 1}
    assert [snapshot.iteration for snapshot in result.snapshots] == [1]


def test_empty_graph_completes() -> None:
    result = Executor().run(Graph(), NodeRegistry())
    assert not result.timed_out
    assert result.outputs == {}


def test_local_consumer_classes_report_process_transfer_requirement() -> None:
    class Local(BaseNode):
        spec = NodeSpec(type_id="test.local", title="Local")

        def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
            return {}

    registry = NodeRegistry()
    registry.register(Local)
    with pytest.raises(ExecutionError, match="module-level"):
        Executor().run(
            Graph(nodes=(NodeInstance(node_id="local", type_id="test.local"),)), registry
        )
    result = Executor().run(
        Graph(nodes=(NodeInstance(node_id="scalar", type_id="test.scalar"),)),
        _registry(),
        inputs={"scalar": {"in": 7}},
    )
    assert not result.timed_out
    assert result.outputs == {"scalar": {"out": 7}}


def test_runtime_inputs_are_separate_from_graph_parameters() -> None:
    graph = Graph(nodes=(NodeInstance(node_id="scalar", type_id="test.scalar"),))
    result = Executor().run(graph, _registry(), inputs={"scalar": {"in": 42}})
    assert not result.timed_out
    assert result.outputs == {"scalar": {"out": 42}}
    assert graph.nodes[0].params == {}


@pytest.mark.parametrize("inputs", [{"unknown": {"in": 1}}, {"scalar": {"unknown": 1}}])
def test_invalid_runtime_input_targets_are_rejected(
    inputs: dict[str, dict[str, object]],
) -> None:
    graph = Graph(nodes=(NodeInstance(node_id="scalar", type_id="test.scalar"),))
    with pytest.raises(ValueError, match="runtime input|Runtime input"):
        Executor().run(graph, _registry(), inputs=inputs)


def test_runtime_inputs_cannot_override_edges_or_multi_connection_ports() -> None:
    graph = Graph(
        nodes=(
            NodeInstance(node_id="constant", type_id="test.constant", params={"value": 2}),
            NodeInstance(node_id="scalar", type_id="test.scalar"),
        ),
        edges=(_edge("edge", "constant", "scalar"),),
    )
    with pytest.raises(ValueError, match="already has a graph connection"):
        Executor().run(graph, _registry(), inputs={"scalar": {"in": 99}})
    multi = Graph(nodes=(NodeInstance(node_id="add", type_id="test.add"),))
    with pytest.raises(ValueError, match="optional scalar port"):
        Executor().run(multi, _registry(), inputs={"add": {"in": [1]}})
