from copy import deepcopy

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Button, FileUploader, Selectbox

from examples import audio_poc, image_poc
from examples.editor_demo import demo_graph
from igomgo_nodes.core import Graph
from igomgo_nodes.storage import BrowserFileStore


def test_app_renders_without_errors() -> None:
    at = AppTest.from_file("../app.py", default_timeout=30).run()

    assert not at.exception
    assert at.title[0].value.endswith("igomgoNodes")


def _button(at: AppTest, label: str) -> Button:
    return next(button for button in at.button if button.label == label)


def _selectbox(at: AppTest, label: str) -> Selectbox:
    return next(selectbox for selectbox in at.selectbox if selectbox.label == label)


def _file_uploader(at: AppTest, label: str) -> FileUploader:
    return next(uploader for uploader in at.file_uploader if uploader.label == label)


def test_palette_parameters_and_touch_movement_persist_across_reruns() -> None:
    at = AppTest.from_file("../app.py", default_timeout=30).run()
    _button(at, "Add node").click().run()
    assert not at.exception
    editor = at.session_state["editor"]
    assert len(editor.graph.nodes) == 4
    node_id = editor.selected_id
    value = next(
        checkbox
        for checkbox in at.checkbox
        if checkbox.label == "Value" and checkbox.key is not None and "_param_" in checkbox.key
    )
    value.uncheck()
    _button(at, "Apply parameters").click().run()
    assert not at.exception
    assert at.session_state["editor"].node(node_id).params == {"value": False}
    before = at.session_state["editor"].node(node_id).position.x
    _button(at, "Right").click().run()
    assert not at.exception
    assert at.session_state["editor"].node(node_id).position.x == before + 40
    at.run()
    assert at.session_state["editor"].node(node_id).params == {"value": False}
    _button(at, "Delete selected node").click().run()
    assert not at.exception
    assert len(at.session_state["editor"].graph.nodes) == 3


def test_ui_displays_rejected_connection_and_missing_required_input() -> None:
    at = AppTest.from_file("../app.py", default_timeout=30).run()
    _button(at, "Connect").click().run()
    assert not at.exception
    assert any("Duplicate connection" in error.value for error in at.error)
    assert len(at.session_state["editor"].graph.edges) == 2
    _button(at, "Disconnect").click().run()
    _button(at, "Validate graph").click().run()
    assert not at.exception
    assert any("minimum is 1" in error.value for error in at.error)


def test_ui_deletes_the_canvas_selected_connection() -> None:
    at = AppTest.from_file("../app.py", default_timeout=30).run()
    editor = at.session_state["editor"]
    state = deepcopy(editor.flow_state)
    state.selected_id = state.edges[1].id
    editor.accept_canvas(state)
    at.run()
    assert not at.exception
    assert any("Selected connection:" in caption.value for caption in at.caption)
    _button(at, "Delete selected connection").click().run()
    assert not at.exception
    assert {edge.edge_id for edge in editor.graph.edges} == {"in-stage"}
    assert editor.selected_edge_id is None


def test_ui_named_ports_support_multi_input_nodes_and_policy() -> None:
    at = AppTest.from_file("../app.py", default_timeout=30).run()
    _selectbox(at, "Node type").select("logic.and").run()
    _button(at, "Add node").click().run()
    assert not at.exception
    target_id = at.session_state["editor"].selected_id
    _selectbox(at, "Target node").select(target_id).run()
    _selectbox(at, "Input port").select("b")
    _button(at, "Connect").click().run()
    assert not at.exception
    assert at.session_state["editor"].graph.edges[-1].dst_port == "b"
    next(checkbox for checkbox in at.checkbox if checkbox.label == "Allow graph feedback").check()
    _button(at, "Apply policy").click().run()
    assert not at.exception
    assert at.session_state["editor"].graph.policy.loop.max_iterations == 3


def test_node_settings_activate_a_drawn_direct_loopback() -> None:
    at = AppTest.from_file("../app.py", default_timeout=30).run()
    _selectbox(at, "Node type").select("logic.feedback_not").run()
    _button(at, "Add node").click().run()
    editor = at.session_state["editor"]
    node_id = editor.selected_id
    next(checkbox for checkbox in at.checkbox if checkbox.label == "Allow graph feedback").check()
    _button(at, "Apply policy").click().run()
    editor.connect("in", "value", node_id, "value")
    editor.connect(node_id, "value", node_id, "value")
    loop = editor.graph.edges[-1].edge_id
    at.run()
    next(widget for widget in at.multiselect if widget.label == "Active direct loopbacks").select(
        loop
    )
    _button(at, "Apply direct loopbacks").click().run()
    assert not at.exception
    assert editor.feedback_edge_ids == frozenset({loop})
    mode = next(
        widget
        for widget in at.selectbox
        if widget.label == "Graph Loopback" and widget.key is not None and "_param_" in widget.key
    )
    mode.select("add")
    _button(at, "Apply parameters").click().run()
    assert not at.exception
    assert editor.node(node_id).params["graph_loopback"] == "add"
    assert any("Maximum incoming connections: 2" in caption.value for caption in at.caption)


@pytest.mark.parametrize(
    ("name", "element", "count"),
    [
        ("Logic", "json", 1),
        ("Audio", "plotly_chart", 2),
        ("Image", "image", 2),
        ("Electronics", "code", 1),
    ],
)
def test_gallery_runs_generated_examples(name: str, element: str, count: int) -> None:
    at = AppTest.from_file("../app.py", default_timeout=30).run()
    _selectbox(at, "Example").select(name).run()
    _button(at, "Run graph").click().run()
    assert not at.exception
    assert not at.error
    assert any(message.value == "Run complete." for message in at.success)
    assert len(at.get(element)) == count
    if name in ("Audio", "Image"):
        assert len(at.get("download_button")) == 2
    else:
        assert len(at.get("download_button")) == 1
    if name == "Audio":
        assert len(at.get("audio")) == 2
    _button(at, "Add node").click().run()
    assert not at.exception
    assert any("Run again" in message.value for message in at.info)
    assert not any(message.value == "Run complete." for message in at.success)


def test_gallery_surfaces_consumer_errors_without_a_completed_result() -> None:
    at = AppTest.from_file("../app.py", default_timeout=30).run()
    _selectbox(at, "Example").select("Audio").run()
    editor = at.session_state["editor_audio"]
    editor.update_params("lowpass", {"cutoff_hz": 10000})
    _button(at, "Run graph").click().run()
    assert not at.exception
    assert any("half the sample rate" in message.value for message in at.error)
    assert len(at.get("download_button")) == 1
    assert not any(message.value == "Run complete." for message in at.success)


def test_image_feedback_gallery_starts_configured_and_runs() -> None:
    at = AppTest.from_file("../app.py", default_timeout=30).run()
    _selectbox(at, "Example").select("Image feedback").run()
    editor = at.session_state["editor_image_feedback"]
    assert editor.feedback_edge_ids == frozenset({image_poc.FEEDBACK_EDGE_ID})
    assert editor.graph.policy.loop.max_iterations == 32
    _button(at, "Run graph").click().run()
    assert not at.exception
    assert not at.error
    assert any(message.value == "Run complete." for message in at.success)
    assert any(button.label == "Download output PNG" for button in at.download_button)
    assert len(at.dataframe) == 1
    assert len(at.dataframe[0].value) == 32


@pytest.mark.parametrize("name", ["Audio", "Image"])
def test_upload_changes_invalidate_output_and_decode_errors_are_visible(name: str) -> None:
    if name == "Audio":
        data = audio_poc.encode_wav(
            audio_poc.AudioBuffer(np.zeros((32, 1), dtype=np.float32), 16000)
        )
        filename, mime = "input.wav", "audio/wav"
    else:
        data = image_poc.encode_png(np.zeros((4, 6, 3), dtype=np.uint8))
        filename, mime = "input.png", "image/png"
    at = AppTest.from_file("../app.py", default_timeout=30).run()
    _selectbox(at, "Example").select(name).run()
    _button(at, "Run graph").click().run()
    media_uploader = _file_uploader(at, "WAV input" if name == "Audio" else "Image input")
    media_uploader.set_value((filename, data, mime)).run()
    assert not at.exception
    assert any("Run again" in message.value for message in at.info)
    assert len(at.get("download_button")) == 1
    _button(at, "Run graph").click().run()
    assert not at.exception
    assert not at.error
    assert len(at.get("download_button")) == 2
    _file_uploader(at, "WAV input" if name == "Audio" else "Image input").set_value(
        (filename, b"corrupt media", mime)
    ).run()
    assert not at.exception
    assert at.error
    assert len(at.get("download_button")) == 1


def test_graph_file_download_and_import_restore_graph_transactionally() -> None:
    at = AppTest.from_file("../app.py", default_timeout=30).run()
    assert any(button.label == "Download graph" for button in at.download_button)
    graph = demo_graph()
    imported_graph = Graph(
        nodes=(
            graph.nodes[0].model_copy(update={"params": {"value": False}}),
            *graph.nodes[1:],
        ),
        edges=graph.edges,
        policy=graph.policy,
    )
    payload = BrowserFileStore().serialize(imported_graph)
    graph_uploader = _file_uploader(at, "Load graph")
    graph_uploader.set_value(("custom.igomgo.json", payload, "application/json")).run()
    assert not at.exception
    assert at.session_state["editor"].graph == imported_graph
    assert any(message.value == "Graph loaded." for message in at.success)

    at.session_state["editor"].update_params("in", {"value": True})
    at.run()
    assert not at.exception
    assert at.session_state["editor"].node("in").params == {"value": True}

    current_graph = at.session_state["editor"].graph
    _file_uploader(at, "Load graph").set_value(
        ("invalid.json", b"not-json", "application/json")
    ).run()
    assert not at.exception
    assert at.session_state["editor"].graph == current_graph
    assert any("Graph not loaded" in message.value for message in at.error)
