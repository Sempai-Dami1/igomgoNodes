import pytest

from igomgo_nodes.core import Edge, Graph, GraphPolicy, LoopPolicy, NodeInstance


def _graph(
    node_ids: tuple[str, ...],
    connections: tuple[tuple[str, str], ...],
    allow_feedback: bool = False,
) -> Graph:
    policy = (
        GraphPolicy(allow_feedback=True, loop=LoopPolicy(max_iterations=3, timeout_seconds=1))
        if allow_feedback
        else GraphPolicy()
    )
    return Graph(
        nodes=tuple(NodeInstance(node_id=node_id, type_id="test") for node_id in node_ids),
        edges=tuple(
            Edge(edge_id=f"edge-{index}", src_node=src, src_port="out", dst_node=dst, dst_port="in")
            for index, (src, dst) in enumerate(connections)
        ),
        policy=policy,
    )


def test_empty_graph_has_no_components_or_cycles() -> None:
    graph = Graph()
    assert graph.strongly_connected_components() == ()
    graph.validate_feedback()


def test_diamond_and_isolated_node_are_acyclic() -> None:
    graph = _graph(
        ("a", "b", "c", "d", "isolated"),
        (("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")),
    )
    components = graph.strongly_connected_components()
    assert {frozenset(component) for component in components} == {
        frozenset({node_id}) for node_id in ("a", "b", "c", "d", "isolated")
    }
    order = {node_id: index for index, component in enumerate(components) for node_id in component}
    assert all(order[edge.src_node] < order[edge.dst_node] for edge in graph.edges)
    graph.validate_feedback()


def test_distinct_cycles_are_not_merged_with_acyclic_neighbors() -> None:
    graph = _graph(
        ("input", "a", "b", "c", "d", "output", "isolated"),
        (
            ("input", "a"),
            ("a", "b"),
            ("b", "a"),
            ("b", "c"),
            ("c", "d"),
            ("d", "c"),
            ("d", "output"),
        ),
    )
    components = graph.strongly_connected_components()
    assert {frozenset(component) for component in components} == {
        frozenset({"input"}),
        frozenset({"a", "b"}),
        frozenset({"c", "d"}),
        frozenset({"output"}),
        frozenset({"isolated"}),
    }
    order = {node_id: index for index, component in enumerate(components) for node_id in component}
    assert order["input"] < order["a"] < order["c"] < order["output"]
    with pytest.raises(ValueError, match="feedback is disabled.*a"):
        graph.validate_feedback()


@pytest.mark.parametrize("connections", [(("a", "a"),), (("a", "b"), ("b", "a"))])
@pytest.mark.parametrize("allow_feedback", [False, True])
def test_cycles_follow_the_graph_wide_permission(
    connections: tuple[tuple[str, str], ...], allow_feedback: bool
) -> None:
    graph = _graph(("a", "b"), connections, allow_feedback)
    if allow_feedback:
        graph.validate_feedback()
    else:
        with pytest.raises(ValueError, match="feedback is disabled.*a"):
            graph.validate_feedback()


def test_long_chain_and_cycle_do_not_depend_on_python_recursion_limit() -> None:
    node_ids = tuple(f"node-{index}" for index in range(2000))
    connections = tuple(zip(node_ids[:-1], node_ids[1:], strict=True))
    graph = _graph(node_ids, connections)
    assert graph.strongly_connected_components() == tuple((node_id,) for node_id in node_ids)
    graph.validate_feedback()
    cycle = _graph(node_ids, (*connections, (node_ids[-1], node_ids[0])), allow_feedback=True)
    components = cycle.strongly_connected_components()
    assert len(components) == 1
    assert set(components[0]) == set(node_ids)
