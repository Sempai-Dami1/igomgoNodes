"""Browser-local persistence for the example gallery workspace."""

from typing import Literal

import streamlit as st
from pydantic import BaseModel, ConfigDict, StrictBool, ValidationError
from streamlit.components.v2 import component as component_v2

from igomgo_nodes.storage.graph_store import MAX_EDITOR_FILE_BYTES
from igomgo_nodes.ui import EditorAdapter

from .gallery import BROWSER_STORE, EXAMPLES, editor_key_for, example_graph

_READER = component_v2(
    "igomgo_workspace_reader",
    js="""
        export default function({data, setStateValue}) {
          if (!data.load) return;
          try {
            const enabled = localStorage.getItem("igomgo.workspace.disabled") !== "true";
            const workspace = enabled ? localStorage.getItem("igomgo.workspace.v1") : null;
            setStateValue("loaded", {enabled, workspace, error: null});
          } catch (error) {
            setStateValue("loaded", {enabled: true, workspace: null, error: String(error)});
          }
        }
    """,
)

_WRITER = component_v2(
    "igomgo_workspace_writer",
    js="""
        export default function({data, setStateValue}) {
          let status = "ok";
          try {
            if (data.enabled) {
              localStorage.setItem("igomgo.workspace.v1", data.workspace);
              localStorage.removeItem("igomgo.workspace.disabled");
            } else {
              localStorage.setItem("igomgo.workspace.disabled", "true");
              localStorage.removeItem("igomgo.workspace.v1");
            }
          } catch (error) {
            status = String(error);
          }
          if (status !== data.lastStatus) setStateValue("status", status);
        }
    """,
)


class Workspace(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[1] = 1
    focus: StrictBool
    example: str
    tab: Literal["Setup", "Canvas", "Draft", "Node", "Graph"] = "Setup"
    graphs: dict[str, str]


def _restore(payload: str) -> tuple[Workspace, dict[str, EditorAdapter]]:
    if len(payload.encode("utf-8")) > MAX_EDITOR_FILE_BYTES:
        raise ValueError("Saved workspace exceeds the 25 MiB limit")
    workspace = Workspace.model_validate_json(payload)
    if workspace.example not in EXAMPLES or any(name not in EXAMPLES for name in workspace.graphs):
        raise ValueError("Saved workspace contains an unknown example")
    editors: dict[str, EditorAdapter] = {}
    for name, graph_json in workspace.graphs.items():
        graph, registry = example_graph(name)
        document = BROWSER_STORE.deserialize(graph_json.encode("utf-8"), registry)
        editor = EditorAdapter(graph, registry)
        editor.replace_graph(document.graph, frozenset(document.feedback_edge_ids))
        editors[editor_key_for(name)] = editor
    return workspace, editors


def restore_workspace() -> None:
    initialized = st.session_state.get("_workspace_initialized", False)
    result = _READER(
        key="workspace_reader",
        data={"load": not initialized},
        on_loaded_change=lambda: None,
    )
    if initialized:
        return
    loaded = result.get("loaded")
    if loaded is None:
        st.info("Loading the workspace saved in this browser...")
        st.stop()
    st.session_state["_workspace_initialized"] = True
    st.session_state["remember_workspace"] = loaded["enabled"]
    if loaded["error"] is not None:
        st.session_state["_workspace_error"] = f"Browser storage is unavailable: {loaded['error']}"
        return
    if loaded["workspace"] is None:
        return
    try:
        workspace, editors = _restore(loaded["workspace"])
    except (ValueError, KeyError, ValidationError) as error:
        st.session_state["_workspace_error"] = f"Saved workspace could not be restored: {error}"
        return
    st.session_state.update(editors)
    st.session_state["focus_mode"] = workspace.focus
    st.session_state["gallery_example"] = workspace.example
    st.session_state["focus_tab"] = "Canvas" if workspace.tab == "Draft" else workspace.tab


def save_workspace() -> None:
    error = st.session_state.get("_workspace_error")
    enabled = st.session_state.get("remember_workspace", True)
    if error and enabled:
        st.error(f"{error} Turn off Remember workspace to remove the saved workspace.")
        return
    if not enabled:
        st.session_state.pop("_workspace_error", None)
    try:
        graphs: dict[str, str] = {}
        if enabled:
            for name in EXAMPLES:
                editor = st.session_state.get(editor_key_for(name))
                if isinstance(editor, EditorAdapter):
                    graphs[name] = BROWSER_STORE.serialize(
                        editor.graph, editor.feedback_edge_ids
                    ).decode("utf-8")
        workspace = Workspace(
            focus=st.session_state.get("focus_mode", False),
            example=st.session_state.get("gallery_example", "Logic"),
            tab=st.session_state.get("focus_tab", "Setup"),
            graphs=graphs,
        ).model_dump_json()
        if len(workspace.encode("utf-8")) > MAX_EDITOR_FILE_BYTES:
            raise ValueError("Workspace exceeds the 25 MiB limit")
    except (ValueError, KeyError, ValidationError) as error:
        st.error(f"Workspace not saved: {error}")
        return
    last_status = st.session_state.get("workspace_writer", {}).get("status")
    result = _WRITER(
        key="workspace_writer",
        data={"enabled": enabled, "workspace": workspace, "lastStatus": last_status},
        on_status_change=lambda: None,
    )
    status = result.get("status")
    if status not in (None, "ok"):
        st.error(f"Browser workspace could not be saved or removed: {status}")
