from copy import deepcopy

import pytest
from pydantic import ValidationError
from streamlit_flow.elements import StreamlitFlowEdge
from streamlit_flow.state import StreamlitFlowState

from examples.editor_demo import demo_graph, demo_registry
from igomgo_nodes.core import Edge, Graph, GraphPolicy, LoopPolicy, NodeInstance, Position
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


def test_feedback_blur_builtin_icon_is_rendered_without_trusting_arbitrary_icon_markup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from examples import image_poc

    graph, registry = image_poc.feedback_demo()
    editor = EditorAdapter(graph, registry)
    blur = next(node for node in editor.flow_state.nodes if node.id == "blur")
    assert blur.data["content"] == "Feedback blur"
    assert blur.style["backgroundImage"].startswith('url("data:image/svg+xml,')
    editor.select_node("blur")
    blur = next(node for node in editor.flow_state.nodes if node.id == "blur")
    assert blur.style["border"] == "2px solid red"
    assert "backgroundImage" in blur.style

    monkeypatch.setattr(
        image_poc.FeedbackBlur,
        "spec",
        image_poc.FeedbackBlur.spec.model_copy(update={"icon": '<svg onload="alert(1)">'}),
    )
    editor.refresh_canvas()
    blur = next(node for node in editor.flow_state.nodes if node.id == "blur")
    assert "backgroundImage" not in blur.style
    assert "&lt;svg" in blur.data["content"]


def test_audio_feedback_icon_is_rendered_and_remains_visible_when_selected() -> None:
    from examples import audio_poc, image_poc

    graph, registry = audio_poc.feedback_demo()
    editor = EditorAdapter(graph, registry)
    echo = next(node for node in editor.flow_state.nodes if node.id == "echo")
    assert echo.data["content"] == "Feedback echo"
    icon = echo.style["backgroundImage"]
    assert icon.startswith('url("data:image/svg+xml,')
    image_graph, image_registry = image_poc.feedback_demo()
    blur = next(
        node
        for node in EditorAdapter(image_graph, image_registry).flow_state.nodes
        if node.id == "blur"
    )
    assert icon != blur.style["backgroundImage"]
    editor.select_node("echo")
    echo = next(node for node in editor.flow_state.nodes if node.id == "echo")
    assert echo.style["backgroundImage"] == icon
    assert echo.style["border"] == "2px solid red"


@pytest.mark.parametrize("feedback", [False, True])
def test_audio_wav_nodes_render_distinct_icons(feedback: bool) -> None:
    from examples import audio_poc

    graph, registry = audio_poc.feedback_demo() if feedback else audio_poc.demo()
    editor = EditorAdapter(graph, registry)
    nodes = {node.id: node for node in editor.flow_state.nodes}
    icons = [nodes[node_id].style["backgroundImage"] for node_id in ("input", "output")]
    assert all(icon.startswith('url("data:image/svg+xml,') for icon in icons)
    assert icons[0] != icons[1]
    assert nodes["input"].data["content"] == "WAV input"
    assert nodes["output"].data["content"] == "WAV output"
    editor.select_node("output")
    selected = next(node for node in editor.flow_state.nodes if node.id == "output")
    assert selected.style["backgroundImage"] == icons[1]
    assert selected.style["border"] == "2px solid red"


@pytest.mark.parametrize("feedback", [False, True])
def test_image_input_and_output_nodes_render_distinct_icons(feedback: bool) -> None:
    from examples import image_poc

    graph, registry = image_poc.feedback_demo() if feedback else image_poc.demo()
    editor = EditorAdapter(graph, registry)
    nodes = {node.id: node for node in editor.flow_state.nodes}
    icons = [nodes[node_id].style["backgroundImage"] for node_id in ("input", "output")]
    assert all(icon.startswith('url("data:image/svg+xml,') for icon in icons)
    assert icons[0] != icons[1]
    assert nodes["input"].data["content"] == "Image input"
    assert nodes["output"].data["content"] == "PNG output"
    editor.select_node("output")
    selected = next(node for node in editor.flow_state.nodes if node.id == "output")
    assert selected.style["backgroundImage"] == icons[1]
    assert selected.style["border"] == "2px solid red"


def test_square_root_feedback_icon_remains_visible_when_selected() -> None:
    from examples import electronics_poc

    graph, registry = electronics_poc.feedback_demo()
    editor = EditorAdapter(graph, registry)
    node = next(node for node in editor.flow_state.nodes if node.id == "sqrt")
    assert node.data["content"] == "Square-root estimator"
    icon = node.style["backgroundImage"]
    assert icon.startswith('url("data:image/svg+xml,')
    editor.select_node("sqrt")
    node = next(node for node in editor.flow_state.nodes if node.id == "sqrt")
    assert node.style["backgroundImage"] == icon
    assert node.style["border"] == "2px solid red"


def test_symbolic_electronics_supply_and_led_icons_render_and_preserve_selection() -> None:
    from examples import electronics_poc

    graph, registry = electronics_poc.demo()
    editor = EditorAdapter(graph, registry)
    nodes = {node.id: node for node in editor.flow_state.nodes}
    icons = [nodes[node_id].style["backgroundImage"] for node_id in ("input", "output")]
    assert all(icon.startswith('url("data:image/svg+xml,') for icon in icons)
    assert icons[0] != icons[1]
    assert nodes["input"].data["content"] == "Supply"
    assert nodes["output"].data["content"] == "LED"
    editor.select_node("output")
    selected = next(node for node in editor.flow_state.nodes if node.id == "output")
    assert selected.style["backgroundImage"] == icons[1]
    assert selected.style["border"] == "2px solid red"


def test_canvas_selection_highlights_one_item_and_deletion_clears_selection() -> None:
    editor = EditorAdapter(demo_graph(), demo_registry())
    state = deepcopy(editor.flow_state)
    state.selected_id = "stage"
    editor.accept_canvas(state)
    assert editor.selected_id == "stage"
    assert editor.flow_state.nodes[1].style["border"] == "2px solid red"

    state = deepcopy(editor.flow_state)
    state.selected_id = state.edges[0].id
    editor.accept_canvas(state)
    assert editor.selected_id is None
    assert editor.selected_edge_id == "in-stage"
    assert editor.flow_state.edges[0].style["stroke"] == "red"
    assert "border" not in editor.flow_state.nodes[1].style
    assert not editor.flow_state.nodes[1].deletable
    assert not editor.flow_state.edges[0].deletable
    assert editor.graph == demo_graph()

    state = StreamlitFlowState(deepcopy(editor.flow_state.nodes), deepcopy(editor.flow_state.edges))
    editor.accept_canvas(state)
    assert editor.selected_edge_id == "in-stage"

    editor.disconnect("in-stage")
    assert editor.selected_edge_id is None
    assert len(editor.graph.edges) == 1


def test_canvas_distinguishes_node_and_edge_with_the_same_id() -> None:
    graph = demo_graph()
    edge = graph.edges[0].model_copy(update={"edge_id": "stage"})
    editor = EditorAdapter(Graph(nodes=graph.nodes, edges=(edge, graph.edges[1])), demo_registry())
    state = deepcopy(editor.flow_state)
    assert state.edges[0].id != "stage"
    state.selected_id = state.edges[0].id
    editor.accept_canvas(state)
    assert editor.selected_edge_id == "stage"
    assert editor.selected_id is None
    assert editor.graph.edges[0] == edge

    state = deepcopy(editor.flow_state)
    state.selected_id = "stage"
    editor.accept_canvas(state)
    assert editor.selected_id == "stage"
    assert editor.selected_edge_id is None


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


def test_configured_connection_limit_and_loopback_save_round_trip() -> None:
    from igomgo_nodes.storage import BrowserFileStore

    editor = EditorAdapter(
        Graph(
            nodes=(
                NodeInstance(node_id="source", type_id="logic.constant"),
                NodeInstance(node_id="stage", type_id="logic.feedback_not"),
            ),
            policy=GraphPolicy(
                allow_feedback=True, loop=LoopPolicy(max_iterations=3, timeout_seconds=10)
            ),
        ),
        demo_registry(),
    )
    editor.connect("source", "value", "stage", "value")
    editor.connect("stage", "value", "stage", "value")
    loop = editor.graph.edges[-1].edge_id
    editor.set_feedback_edges(frozenset({loop}))
    editor.update_params("stage", {"max_incoming": 2, "graph_loopback": "add"})
    before = editor.graph
    with pytest.raises(ValueError, match="2 incoming connections, maximum is 1"):
        editor.update_params("stage", {"max_incoming": 1})
    assert editor.graph == before
    store = BrowserFileStore()
    loaded = store.deserialize(
        store.serialize(editor.graph, editor.feedback_edge_ids), editor.registry
    )
    assert loaded.graph == editor.graph
    assert loaded.feedback_edge_ids == (loop,)


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


def test_replace_graph_restores_feedback_boundaries_and_is_transactional() -> None:
    base = demo_graph()
    graph = Graph(
        nodes=base.nodes,
        edges=(
            base.edges[1],
            Edge(
                edge_id="feedback",
                src_node="out",
                src_port="value",
                dst_node="stage",
                dst_port="value",
            ),
        ),
        policy=GraphPolicy(
            allow_feedback=True, loop=LoopPolicy(max_iterations=2, timeout_seconds=1)
        ),
    )
    editor = EditorAdapter(demo_graph(), demo_registry())
    editor.replace_graph(graph, frozenset({"feedback"}))
    assert editor.graph == graph
    assert editor.feedback_edge_ids == frozenset({"feedback"})
    assert editor.selected_id is None

    original = editor.graph
    with pytest.raises(ValueError, match="reference edges"):
        editor.replace_graph(graph, frozenset({"missing"}))
    assert editor.graph is original
    assert editor.feedback_edge_ids == frozenset({"feedback"})

    invalid_node = original.nodes[0].model_copy(update={"params": {"value": "not a boolean"}})
    invalid_graph = Graph(
        nodes=(invalid_node, *original.nodes[1:]),
        edges=original.edges,
        policy=original.policy,
    )
    with pytest.raises(ValidationError):
        editor.replace_graph(invalid_graph, frozenset({"feedback"}))
    assert editor.graph is original
