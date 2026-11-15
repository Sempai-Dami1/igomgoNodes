from copy import deepcopy

import pytest
from pydantic import ValidationError
from streamlit_flow.elements import StreamlitFlowEdge
from streamlit_flow.state import StreamlitFlowState

from examples.editor_demo import demo_graph, demo_registry
from igomgo_nodes.core import Graph, GraphPolicy, LoopPolicy, NodeInstance, Position
from igomgo_nodes.ui import EditorAdapter


def test_canvas_round_trip_preserves_named_ports_parameters_and_positions() -> None:
    editor = EditorAdapter(demo_graph(), demo_registry())
    state = deepcopy(editor.flow_state)
    state.nodes[1].position = {"x": -40.5, "y": 120}
    state.selected_id = "stage"
    editor.accept_canvas(state)
    assert editor.node("stage").position == Position(x=-40.5, y=120)
    assert editor.selected_id == "stage"
    assert editor.graph.edges == demo_graph().edges
    assert editor.node("in").params == {"value": True}
    dragged = StreamlitFlowState(deepcopy(state.nodes), deepcopy(state.edges))
    dragged.nodes[1].position = {"x": 180.0, "y": 260.0}
    editor.accept_canvas(dragged)
    assert editor.selected_id == "stage"
    assert editor.node("stage").position == Position(x=180, y=260)


def test_palette_parameters_movement_and_delete_use_the_core_graph() -> None:
    editor = EditorAdapter(demo_graph(), demo_registry())
    editor.add_node("logic.constant", {"value": False})
    selected = editor.selected_id
    assert selected is not None
    assert editor.node(selected).params == {"value": False}
    editor.move_node(selected, Position(x=42, y=-12))
    assert editor.node(selected).position == Position(x=42, y=-12)
    editor.update_params(selected, {"value": True})
    assert editor.node(selected).params == {"value": True}
    editor.remove_node("stage")
    assert editor.graph.edges == ()
    editor.remove_node(selected)
    assert editor.selected_id is None


def test_rejected_parameters_and_connections_leave_graph_unchanged() -> None:
    editor = EditorAdapter(demo_graph(), demo_registry())
    original = editor.graph.model_copy(deep=True)
    with pytest.raises(ValidationError):
        editor.update_params("in", {"value": "not a boolean"})
    with pytest.raises(ValueError, match="Duplicate connection"):
        editor.connect("in", "value", "stage", "value")
    with pytest.raises(ValueError, match="maximum is 1"):
        editor.connect("stage", "value", "stage", "value")
    assert editor.graph == original


def test_editing_allows_incomplete_nodes_but_not_invalid_existing_edges() -> None:
    editor = EditorAdapter(demo_graph(), demo_registry())
    editor.disconnect("in-stage")
    with pytest.raises(ValueError, match="minimum is 1"):
        editor.graph.validate_connections(editor.registry)
    editor.connect("in", "value", "stage", "value")
    editor.graph.validate_connections(editor.registry)
    with pytest.raises(ValueError, match="unknown output port"):
        editor.connect("in", "wrong", "stage", "value")


def test_canvas_drag_connections_reject_cycles_without_permission_and_can_be_repaired() -> None:
    editor = EditorAdapter(
        Graph(nodes=(NodeInstance(node_id="not", type_id="logic.not"),)), demo_registry()
    )
    proposed = deepcopy(editor.flow_state)
    proposed.edges.append(StreamlitFlowEdge("loop", "not", "not"))
    with pytest.raises(ValueError, match="feedback is disabled"):
        editor.accept_canvas(proposed)
    assert editor.graph.edges == ()
    editor.set_policy(
        GraphPolicy(allow_feedback=True, loop=LoopPolicy(max_iterations=3, timeout_seconds=2))
    )
    proposed = deepcopy(editor.flow_state)
    proposed.edges.append(StreamlitFlowEdge("loop", "not", "not"))
    editor.accept_canvas(proposed)
    assert editor.graph.edges[0].src_port == "value"
    assert editor.flow_state.edges[0].label == "value -> value"
    editor.set_feedback_edges(frozenset({"loop"}))
    assert editor.feedback_edge_ids == frozenset({"loop"})
    with pytest.raises(ValueError, match="feedback is disabled"):
        editor.set_policy(GraphPolicy())
    editor.disconnect("loop")
    assert editor.feedback_edge_ids == frozenset()
    editor.set_policy(GraphPolicy())


def test_canvas_connections_with_multiple_ports_require_explicit_selection() -> None:
    editor = EditorAdapter(
        Graph(
            nodes=(
                NodeInstance(node_id="source", type_id="logic.constant"),
                NodeInstance(node_id="and", type_id="logic.and"),
            )
        ),
        demo_registry(),
    )
    state = deepcopy(editor.flow_state)
    state.edges.append(StreamlitFlowEdge("ambiguous", "source", "and"))
    with pytest.raises(ValueError, match="named ports"):
        editor.accept_canvas(state)
    assert editor.graph.edges == ()
    editor.connect("source", "value", "and", "b")
    assert editor.graph.edges[0].dst_port == "b"
    state = deepcopy(editor.flow_state)
    state.nodes.reverse()
    editor.accept_canvas(state)
    assert editor.graph.edges[0].dst_port == "b"


def test_canvas_deletion_removes_attached_edges_and_rejects_unknown_nodes() -> None:
    editor = EditorAdapter(demo_graph(), demo_registry())
    state = deepcopy(editor.flow_state)
    state.nodes = [node for node in state.nodes if node.id != "stage"]
    state.edges = []
    editor.accept_canvas(state)
    assert {node.node_id for node in editor.graph.nodes} == {"in", "out"}
    assert editor.graph.edges == ()
    state.nodes[0].id = "unregistered-canvas-node"
    with pytest.raises(ValueError, match="palette"):
        editor.accept_canvas(state)


def test_parameter_model_is_validated_when_nodes_are_executed_not_only_in_ui() -> None:
    constant = demo_registry().resolve("logic.constant")
    assert constant("default").params == {"value": True}
    with pytest.raises(ValidationError):
        constant("invalid", {"value": "not a boolean"})
