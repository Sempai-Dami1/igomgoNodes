import pytest

from igomgo_nodes.core import Edge, Graph, GraphPolicy, LoopPolicy, NodeInstance


def _graph(
    node_ids: tuple[str, ...],
    connections: tuple[tuple[str, str, str], ...],
    iterations: int = 3,
) -> Graph:
    return Graph(
        nodes=tuple(
            NodeInstance(node_id=node_id, type_id="test", params={"settings": {"gain": 1}})
            for node_id in node_ids
        ),
        edges=tuple(
            Edge(edge_id=edge_id, src_node=src, src_port="out", dst_node=dst, dst_port="in")
            for edge_id, src, dst in connections
        ),
        policy=GraphPolicy(
            allow_feedback=True,
            loop=LoopPolicy(max_iterations=iterations, timeout_seconds=1),
        ),
    )


def test_spiral_has_exact_pass_count_and_first_input_last_output() -> None:
    graph = _graph(
        ("input", "b", "c", "output"),
        (
            ("entry", "input", "b"),
            ("stage", "b", "c"),
            ("feedback", "c", "b"),
            ("exit", "c", "output"),
        ),
    )
    expanded = graph.unroll(feedback_edge_ids=frozenset({"feedback"}))
    assert {node.node_id for node in expanded.nodes} == {
        "input",
        "b",
        "b@2",
        "b@3",
        "c",
        "c@2",
        "c@3",
        "output",
    }
    assert {(edge.src_node, edge.dst_node) for edge in expanded.edges} == {
        ("input", "b"),
        ("b", "c"),
        ("c", "b@2"),
        ("b@2", "c@2"),
        ("c@2", "b@3"),
        ("b@3", "c@3"),
        ("c@3", "output"),
    }
    assert not expanded.policy.allow_feedback
    expanded.validate_feedback()
    assert Graph.model_validate_json(expanded.model_dump_json()) == expanded


def test_one_pass_omits_feedback_and_copies_are_independent() -> None:
    graph = _graph(("a",), (("feedback", "a", "a"),))
    single = graph.unroll(1, feedback_edge_ids=frozenset({"feedback"}))
    assert len(single.nodes) == 1
    assert single.edges == ()
    expanded = graph.unroll(feedback_edge_ids=frozenset({"feedback"}))
    assert [(edge.src_node, edge.dst_node) for edge in expanded.edges] == [
        ("a", "a@2"),
        ("a@2", "a@3"),
    ]
    settings = expanded.nodes[1].params["settings"]
    assert isinstance(settings, dict)
    settings["gain"] = 2
    assert expanded.nodes[0].params == {"settings": {"gain": 1}}
    assert graph.nodes[0].params == {"settings": {"gain": 1}}


def test_explicit_boundary_is_independent_of_node_declaration_order() -> None:
    connections = (("forward", "a", "b"), ("feedback", "b", "a"))
    first = _graph(("a", "b"), connections).unroll(feedback_edge_ids=frozenset({"feedback"}))
    reordered = _graph(("b", "a"), connections).unroll(feedback_edge_ids=frozenset({"feedback"}))
    assert set(first.edges) == set(reordered.edges)


def test_each_cyclic_group_is_unrolled_and_connected_in_sequence() -> None:
    graph = _graph(
        ("a", "b", "c", "d", "isolated"),
        (("ab", "a", "b"), ("ba", "b", "a"), ("bc", "b", "c"), ("cd", "c", "d"), ("dc", "d", "c")),
    )
    expanded = graph.unroll(feedback_edge_ids=frozenset({"ba", "dc"}))
    assert len(expanded.nodes) == 13
    bridge = next(edge for edge in expanded.edges if edge.edge_id == "bc")
    assert (bridge.src_node, bridge.dst_node) == ("b@3", "c")
    expanded.validate_feedback()


def test_missing_or_incomplete_cuts_are_rejected() -> None:
    graph = _graph(
        ("a", "b", "c"),
        (("ab", "a", "b"), ("ba", "b", "a"), ("bc", "b", "c"), ("cb", "c", "b")),
    )
    with pytest.raises(ValueError, match="do not break every cycle"):
        graph.unroll()
    with pytest.raises(ValueError, match="do not break every cycle"):
        graph.unroll(feedback_edge_ids=frozenset({"ba"}))
    graph.unroll(feedback_edge_ids=frozenset({"ba", "cb"})).validate_feedback()


def test_unknown_or_noncyclic_feedback_edges_are_rejected() -> None:
    graph = _graph(("a", "b"), (("edge", "a", "b"),))
    with pytest.raises(ValueError, match="Unknown feedback edge IDs"):
        graph.unroll(feedback_edge_ids=frozenset({"missing"}))
    with pytest.raises(ValueError, match="inside a cyclic component"):
        graph.unroll(feedback_edge_ids=frozenset({"edge"}))
    assert graph.unroll().edges == graph.edges


def test_graph_permission_is_not_overridden_by_selected_boundaries() -> None:
    allowed = _graph(("a",), (("feedback", "a", "a"),))
    denied = Graph(nodes=allowed.nodes, edges=allowed.edges)
    with pytest.raises(ValueError, match="feedback is disabled"):
        denied.unroll(feedback_edge_ids=frozenset({"feedback"}))


@pytest.mark.parametrize("iterations", [0, -1, True, 1.5, 4])
def test_invalid_iteration_overrides_are_rejected(iterations: object) -> None:
    graph = _graph(("a",), (("feedback", "a", "a"),))
    with pytest.raises(ValueError, match="iterations"):
        graph.unroll(iterations, feedback_edge_ids=frozenset({"feedback"}))  # type: ignore[arg-type]


def test_generated_ids_do_not_collide_with_original_ids() -> None:
    graph = _graph(("a", "a@2"), (("feedback", "a", "a"), ("feedback@2", "a@2", "a@2")))
    expanded = graph.unroll(feedback_edge_ids=frozenset({"feedback", "feedback@2"}))
    assert len({node.node_id for node in expanded.nodes}) == 6
    assert len({edge.edge_id for edge in expanded.edges}) == 4
    expanded.validate_feedback()


def test_node_expansion_cap_at_boundary_and_above() -> None:
    graph = _graph(("a",), (("feedback", "a", "a"),), iterations=10_001)
    expanded = graph.unroll(10_000, feedback_edge_ids=frozenset({"feedback"}))
    assert len(expanded.nodes) == 10_000
    with pytest.raises(ValueError, match="10000-node limit"):
        graph.unroll(feedback_edge_ids=frozenset({"feedback"}))


def test_edge_expansion_cap_at_boundary_and_above() -> None:
    graph = _graph(
        ("a",),
        (),
        iterations=5002,
    )
    edges = tuple(
        Edge(edge_id=str(index), src_node="a", src_port=str(index), dst_node="a", dst_port="in")
        for index in range(20)
    )
    graph = Graph(nodes=graph.nodes, edges=edges, policy=graph.policy)
    feedback = frozenset(edge.edge_id for edge in edges)
    expanded = graph.unroll(5001, feedback_edge_ids=feedback)
    assert len(expanded.edges) == 100_000
    with pytest.raises(ValueError, match="100000-edge limit"):
        graph.unroll(feedback_edge_ids=feedback)


def test_override_is_dormant_in_a_multi_node_cycle() -> None:
    graph = _graph(
        ("a", "b"),
        (("self", "a", "a"), ("forward", "a", "b"), ("feedback", "b", "a")),
    )
    overridden = graph.nodes[0].model_copy(update={"feedback_max_iterations": 1})
    graph = graph.model_copy(update={"nodes": (overridden, graph.nodes[1])})
    expanded = graph.unroll(feedback_edge_ids=frozenset({"self", "feedback"}))
    assert {node.node_id for node in expanded.nodes} == {"a", "a@2", "a@3", "b", "b@2", "b@3"}
