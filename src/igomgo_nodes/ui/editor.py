"""Reusable Streamlit controls around the graph editor adapter."""

import json
from collections.abc import Callable, Mapping
from typing import Literal

import streamlit as st
from streamlit_flow import streamlit_flow

from igomgo_nodes.core import BaseNode, GraphPolicy, LoopPolicy, Position

from .adapter import EditorAdapter


def _action(editor: EditorAdapter, operation: Callable[[], None], message: str) -> None:
    try:
        operation()
    except (ValueError, KeyError) as error:
        editor.notice = ("error", str(error))
        st.rerun()
    else:
        editor.notice = ("success", message)
        st.rerun()


def _parameter_fields(
    node_type: type[BaseNode], values: Mapping[str, object], key: str
) -> tuple[dict[str, object], set[str]]:
    model = node_type.parameter_model
    if model is None:
        return {
            "": st.text_area(
                "Parameters (JSON object)", json.dumps(dict(values), indent=2), key=f"{key}_json"
            )
        }, {""}
    schema = model.model_json_schema()
    properties = schema.get("properties", {})
    fields: dict[str, object] = {}
    json_fields: set[str] = set()
    for name, spec in properties.items():
        label = spec.get("title", name)
        value = values.get(name, spec.get("default"))
        widget_key = f"{key}_{name}"
        help_text = spec.get("description")
        kind = spec.get("type")
        if "enum" in spec:
            choices = spec["enum"]
            fields[name] = st.selectbox(
                label,
                choices,
                index=choices.index(value) if value in choices else 0,
                key=widget_key,
                help=help_text,
            )
        elif kind == "boolean":
            fields[name] = st.checkbox(label, value=bool(value), key=widget_key, help=help_text)
        elif kind in ("integer", "number"):
            # Text preserves exact integers and lets Pydantic report constraints on submit.
            fields[name] = st.text_input(
                label, value="" if value is None else str(value), key=widget_key, help=help_text
            )
            json_fields.add(name)
        elif kind == "string":
            fields[name] = st.text_input(
                label, value="" if value is None else str(value), key=widget_key, help=help_text
            )
        else:
            fields[name] = st.text_area(
                f"{label} (JSON)", json.dumps(value, indent=2), key=widget_key, help=help_text
            )
            json_fields.add(name)
    return fields, json_fields


def _parse_parameters(fields: dict[str, object], json_fields: set[str]) -> dict[str, object]:
    result = dict(fields)
    for name in json_fields:
        value = fields[name]
        if not isinstance(value, str):
            raise ValueError(f"JSON field {name} must be text")
        result[name] = json.loads(value)
    if "" in json_fields:
        whole = result[""]
        if not isinstance(whole, dict):
            raise ValueError("Parameters must be a JSON object")
        return whole
    return result


def _palette(editor: EditorAdapter, key: str) -> None:
    st.subheader("Node palette")
    types = {node_type.spec.type_id: node_type for node_type in editor.registry.node_types()}
    if not types:
        st.info("Register consumer node types to populate the palette.")
        return
    type_id = st.selectbox(
        "Node type",
        tuple(types),
        key=f"{key}_palette",
        format_func=lambda value: f"{types[value].spec.category} / {types[value].spec.title}",
    )
    with st.form(f"{key}_add_{type_id}"):
        fields, json_fields = _parameter_fields(types[type_id], {}, f"{key}_new_{type_id}")
        if st.form_submit_button("Add node"):
            _action(
                editor,
                lambda: editor.add_node(type_id, _parse_parameters(fields, json_fields)),
                "Node added.",
            )


def _policy(editor: EditorAdapter, key: str) -> None:
    st.subheader("Graph policy")
    policy = editor.graph.policy
    loop = policy.loop
    with st.form(f"{key}_policy_{editor.revision}"):
        allowed = st.checkbox("Allow graph feedback", value=policy.allow_feedback)
        iterations = st.number_input(
            "Maximum iterations",
            min_value=1,
            value=loop.max_iterations if loop else 3,
            step=1,
        )
        timeout = st.number_input(
            "Timeout (seconds)",
            min_value=0.0,
            value=loop.timeout_seconds if loop else 10.0,
        )
        capture = st.number_input(
            "Capture every N iterations",
            min_value=1,
            value=loop.capture_every if loop else 1,
            step=1,
        )
        if st.form_submit_button("Apply policy"):

            def apply() -> None:
                editor.set_policy(
                    GraphPolicy(
                        allow_feedback=allowed,
                        loop=LoopPolicy(
                            max_iterations=int(iterations),
                            timeout_seconds=float(timeout),
                            capture_every=int(capture),
                        )
                        if allowed
                        else None,
                    )
                )

            _action(editor, apply, "Graph policy updated.")
    st.caption("Feedback is one graph-wide permission. Runs are always a finite virtual spiral.")


def _inspector(editor: EditorAdapter, key: str) -> None:
    st.subheader("Inspector")
    ids = [node.node_id for node in editor.graph.nodes]
    if not ids:
        st.info("Add a node to begin.")
        return
    initial = ids.index(editor.selected_id) if editor.selected_id in ids else None
    selected = st.selectbox(
        "Selected node",
        ids,
        index=initial,
        placeholder="Tap a node or choose here",
        format_func=lambda value: (
            f"{editor.registry.resolve(editor.node(value).type_id).spec.title} ({value[:8]})"
        ),
        key=f"{key}_selection_{editor.selected_id}",
    )
    if selected != editor.selected_id and selected is not None:
        editor.select_node(selected)
        st.rerun()
    if selected is None:
        return
    node = editor.node(selected)
    node_type = editor.registry.resolve(node.type_id)
    st.caption(f"Type: {node.type_id} | ID: {node.node_id}")
    st.write("Inputs", [port.model_dump() for port in node_type.spec.inputs])
    st.write("Outputs", [port.model_dump() for port in node_type.spec.outputs])
    limit = node_type.input_connection_limit(node_type.validate_params(node.params))
    if limit is not None:
        st.caption(f"Maximum incoming connections: {limit} (including direct loopbacks)")
    with st.form(f"{key}_params_{node.node_id}_{editor.revision}"):
        fields, json_fields = _parameter_fields(
            node_type, node.params, f"{key}_param_{node.node_id}_{editor.revision}"
        )
        if st.form_submit_button("Apply parameters"):
            _action(
                editor,
                lambda: editor.update_params(node.node_id, _parse_parameters(fields, json_fields)),
                "Parameters updated.",
            )
    direct_edges = [
        edge
        for edge in editor.graph.edges
        if edge.src_node == node.node_id and edge.dst_node == node.node_id
    ]
    if direct_edges and editor.graph.policy.allow_feedback:
        edge_ids = {edge.edge_id for edge in direct_edges}
        with st.form(f"{key}_direct_loopbacks_{node.node_id}_{editor.revision}"):
            chosen = st.multiselect(
                "Active direct loopbacks",
                [edge.edge_id for edge in direct_edges],
                default=sorted(editor.feedback_edge_ids & edge_ids),
                format_func=lambda edge_id: next(
                    f"{edge.src_port} -> {edge.dst_port} ({edge.edge_id[:8]})"
                    for edge in direct_edges
                    if edge.edge_id == edge_id
                ),
                help="A selected connection feeds the next graph iteration.",
            )
            if st.form_submit_button("Apply direct loopbacks"):
                _action(
                    editor,
                    lambda: editor.set_feedback_edges(
                        (editor.feedback_edge_ids - edge_ids) | frozenset(chosen)
                    ),
                    "Direct loopbacks validated.",
                )
    st.caption("Touch: select a node, then use coordinates or the move buttons.")
    with st.form(
        f"{key}_move_{node.node_id}_{editor.revision}_{node.position.x}_{node.position.y}"
    ):
        x = st.number_input("X", value=node.position.x)
        y = st.number_input("Y", value=node.position.y)
        if st.form_submit_button("Move to position"):
            _action(
                editor,
                lambda: editor.move_node(node.node_id, Position(x=x, y=y)),
                "Position updated.",
            )
    for column, (label, dx, dy) in zip(
        st.columns(4),
        (("Left", -40, 0), ("Right", 40, 0), ("Up", 0, -40), ("Down", 0, 40)),
        strict=True,
    ):
        if column.button(label, key=f"{key}_move_{label}"):
            _action(
                editor,
                lambda dx=dx, dy=dy: editor.move_node(
                    node.node_id, Position(x=node.position.x + dx, y=node.position.y + dy)
                ),
                "Position updated.",
            )
    if st.button("Delete selected node", key=f"{key}_delete"):
        _action(
            editor, lambda: editor.remove_node(node.node_id), "Node and attached edges deleted."
        )


def _connections(editor: EditorAdapter, key: str) -> None:
    st.subheader("Connections")
    st.caption("Drag between single-port nodes. Use named ports here for multi-port nodes.")
    sources = [
        node.node_id
        for node in editor.graph.nodes
        if editor.registry.resolve(node.type_id).spec.outputs
    ]
    targets = [
        node.node_id
        for node in editor.graph.nodes
        if editor.registry.resolve(node.type_id).spec.inputs
    ]

    def node_label(node_id: str) -> str:
        return f"{editor.registry.resolve(editor.node(node_id).type_id).spec.title} ({node_id[:8]})"

    if sources and targets:
        src = st.selectbox("Source node", sources, format_func=node_label, key=f"{key}_src")
        dst = st.selectbox("Target node", targets, format_func=node_label, key=f"{key}_dst")
        src_ports = editor.registry.resolve(editor.node(src).type_id).spec.outputs
        dst_ports = editor.registry.resolve(editor.node(dst).type_id).spec.inputs
        with st.form(f"{key}_connect_{src}_{dst}"):
            src_port = st.selectbox("Output port", [port.name for port in src_ports])
            dst_port = st.selectbox("Input port", [port.name for port in dst_ports])
            if st.form_submit_button("Connect"):
                _action(
                    editor,
                    lambda: editor.connect(src, src_port, dst, dst_port),
                    "Connection added.",
                )
    else:
        st.info("Add nodes with inputs and outputs to connect them.")
    edges = {edge.edge_id: edge for edge in editor.graph.edges}
    if not edges:
        return

    def edge_label(edge_id: str) -> str:
        edge = edges[edge_id]
        return (
            f"{node_label(edge.src_node)}.{edge.src_port} -> "
            f"{node_label(edge.dst_node)}.{edge.dst_port}"
        )

    selected_edge_id = editor.selected_edge_id
    if selected_edge_id is not None:
        st.caption(f"Selected connection: {edge_label(selected_edge_id)}")
        if st.button("Delete selected connection", key=f"{key}_delete_edge"):
            _action(
                editor,
                lambda: editor.disconnect(selected_edge_id),
                "Connection removed.",
            )
    edge_id = st.selectbox(
        "Connection", tuple(edges), format_func=edge_label, key=f"{key}_edge_{editor.revision}"
    )
    if st.button("Disconnect", key=f"{key}_disconnect"):
        _action(editor, lambda: editor.disconnect(edge_id), "Connection removed.")
    if editor.graph.policy.allow_feedback:
        with st.form(f"{key}_feedback_{editor.revision}"):
            feedback = st.multiselect(
                "Next-iteration feedback connections",
                tuple(edges),
                default=sorted(editor.feedback_edge_ids),
                format_func=edge_label,
            )
            if st.form_submit_button("Apply feedback boundaries"):
                _action(
                    editor,
                    lambda: editor.set_feedback_edges(frozenset(feedback)),
                    "Feedback boundaries validated.",
                )


def _canvas(editor: EditorAdapter, key: str) -> None:
    notice = st.empty()
    st.caption("Select a node or connection, then use its on-screen delete button.")
    revision = editor.revision
    selection = (editor.selected_id, editor.selected_edge_id)
    state = streamlit_flow(
        f"{key}_canvas_{editor.revision}",
        editor.flow_state,
        height=440,
        fit_view=True,
        get_node_on_click=True,
        get_edge_on_click=True,
        allow_new_edges=True,
    )
    try:
        editor.accept_canvas(state)
    except (ValueError, KeyError) as error:
        editor.notice = ("error", str(error))
        editor.refresh_canvas()
        st.rerun()
    if editor.revision != revision or selection != (editor.selected_id, editor.selected_edge_id):
        st.rerun()
    if editor.notice is not None:
        level, message = editor.notice
        if level == "error":
            notice.error(message)
        else:
            notice.success(message)


def _node_controls(editor: EditorAdapter, key: str, *, stacked: bool = False) -> None:
    if stacked:
        _inspector(editor, key)
        _connections(editor, key)
    else:
        inspector, connections = st.columns(2)
        with inspector:
            _inspector(editor, key)
        with connections:
            _connections(editor, key)


def _validation(editor: EditorAdapter, key: str) -> None:
    st.caption(f"{len(editor.graph.nodes)} nodes | {len(editor.graph.edges)} connections")
    if st.button("Validate graph", key=f"{key}_validate"):
        try:
            editor.graph.validate_connections(editor.registry)
            editor.graph.validate_feedback()
            editor.graph.unroll(feedback_edge_ids=editor.feedback_edge_ids)
            for node in editor.graph.nodes:
                editor.registry.resolve(node.type_id).validate_params(node.params)
        except (ValueError, KeyError) as error:
            st.error(str(error))
        else:
            st.success("Graph is valid, including feedback boundaries. No processing was run.")


def _notice(editor: EditorAdapter) -> None:
    if editor.notice is not None:
        level, message = editor.notice
        if level == "error":
            st.error(message)
        else:
            st.success(message)


def render_editor(
    editor: EditorAdapter,
    *,
    key: str = "editor",
    section: Literal["all", "setup", "draft", "node"] = "all",
) -> None:
    """Render the editor or one section; accepted edits update the session-owned graph."""
    if section == "all":
        with st.sidebar:
            _palette(editor, key)
            _policy(editor, key)
        _canvas(editor, key)
        _node_controls(editor, key)
        _validation(editor, key)
    elif section == "setup":
        _palette(editor, key)
        _policy(editor, key)
        _notice(editor)
    elif section == "draft":
        _canvas(editor, key)
        _validation(editor, key)
    elif section == "node":
        _notice(editor)
        _node_controls(editor, key, stacked=True)
    else:
        raise ValueError(f"Unknown editor section: {section}")
