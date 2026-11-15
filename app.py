"""Streamlit entry point: placeholder demo for igomgoNodes."""

import streamlit as st
from streamlit_flow import streamlit_flow
from streamlit_flow.elements import StreamlitFlowEdge, StreamlitFlowNode
from streamlit_flow.state import StreamlitFlowState

import igomgo_nodes

st.set_page_config(page_title="igomgoNodes", page_icon="🧩", layout="wide")


def _demo_state() -> StreamlitFlowState:
    nodes = [
        StreamlitFlowNode(
            "in", (0, 80), {"content": "🎵 Input"}, "input", "right", selectable=True
        ),
        StreamlitFlowNode(
            "stage",
            (220, 80),
            {"content": "🎚️ Stage"},
            "default",
            "right",
            "left",
            selectable=True,
            connectable=True,
        ),
        StreamlitFlowNode(
            "out",
            (440, 80),
            {"content": "📈 Output"},
            "output",
            target_position="left",
            selectable=True,
        ),
    ]
    edges = [
        StreamlitFlowEdge("in-stage", "in", "stage", animated=True),
        StreamlitFlowEdge("stage-out", "stage", "out", animated=True),
    ]
    return StreamlitFlowState(nodes, edges)


if "flow_state" not in st.session_state:
    st.session_state.flow_state = _demo_state()

st.title("🧩 igomgoNodes")
st.caption(f"v{igomgo_nodes.__version__} · placeholder canvas — drag nodes, click to select")

st.session_state.flow_state = streamlit_flow(
    "demo_flow",
    st.session_state.flow_state,
    height=400,
    fit_view=True,
    get_node_on_click=True,
)

selected = st.session_state.flow_state.selected_id
st.write(f"Selected node: `{selected}`" if selected else "No node selected.")
