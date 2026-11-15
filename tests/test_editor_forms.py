from streamlit.testing.v1 import AppTest

SCHEMA_APP = """
from collections.abc import Mapping
from typing import Literal
import streamlit as st
from pydantic import BaseModel, ConfigDict, Field
from igomgo_nodes.core import BaseNode, Graph, NodeRegistry, NodeSpec
from igomgo_nodes.ui import EditorAdapter, render_editor

class Parameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    count: int = Field(default=2, gt=0, strict=True)
    title: str = "Example"
    mode: Literal["first", "second"] = "first"
    options: list[int] = [1]

class Configured(BaseNode):
    spec = NodeSpec(type_id="test.configured", title="Configured")
    parameter_model = Parameters
    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        return {}

if "editor" not in st.session_state:
    registry = NodeRegistry()
    registry.register(Configured)
    st.session_state.editor = EditorAdapter(Graph(), registry)
render_editor(st.session_state.editor)
"""


def test_schema_fields_preserve_types_and_report_invalid_parameters() -> None:
    at = AppTest.from_string(SCHEMA_APP, default_timeout=30).run()
    next(field for field in at.text_input if field.label == "Count").set_value("4")
    next(field for field in at.text_input if field.label == "Title").set_value("Custom")
    next(field for field in at.selectbox if field.label == "Mode").select("second")
    next(field for field in at.text_area if field.label == "Options (JSON)").set_value("[2, 3]")
    next(button for button in at.button if button.label == "Add node").click().run()
    assert not at.exception
    editor = at.session_state["editor"]
    node_id = editor.selected_id
    assert editor.node(node_id).params == {
        "count": 4,
        "title": "Custom",
        "mode": "second",
        "options": [2, 3],
    }
    count = next(
        field
        for field in at.text_input
        if field.label == "Count" and field.key is not None and "_param_" in field.key
    )
    count.set_value("-1")
    next(button for button in at.button if button.label == "Apply parameters").click().run()
    assert not at.exception
    assert editor.node(node_id).params["count"] == 4
    assert any("greater than 0" in error.value for error in at.error)
    at.run()
    assert any("greater than 0" in error.value for error in at.error)


def test_malformed_nested_json_is_rejected_without_adding_node() -> None:
    at = AppTest.from_string(SCHEMA_APP, default_timeout=30).run()
    next(field for field in at.text_area if field.label == "Options (JSON)").set_value("{")
    next(button for button in at.button if button.label == "Add node").click().run()
    assert not at.exception
    assert at.session_state["editor"].graph.nodes == ()
    assert len(at.error) == 1
