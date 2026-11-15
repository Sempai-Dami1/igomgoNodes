"""Transactional graph editing and conversion to the ready-made canvas."""

from collections.abc import Mapping
from html import escape
from uuid import uuid4

from streamlit_flow.elements import StreamlitFlowEdge, StreamlitFlowNode
from streamlit_flow.state import StreamlitFlowState

from igomgo_nodes.core import Edge, Graph, GraphPolicy, NodeInstance, NodeRegistry, Position
from igomgo_nodes.core.unroll import MAX_EXPANDED_EDGES, MAX_EXPANDED_NODES


class EditorAdapter:
    def __init__(self, graph: Graph, registry: NodeRegistry) -> None:
        self.registry = registry
        self.graph = graph
        self.selected_id: str | None = None
        self.feedback_edge_ids: frozenset[str] = frozenset()
        self.revision = 0
        self.notice: tuple[str, str] | None = None
        self._validate(graph)
        self.flow_state = self._to_flow()

    def _validate(self, graph: Graph) -> None:
        if len(graph.nodes) > MAX_EXPANDED_NODES or len(graph.edges) > MAX_EXPANDED_EDGES:
            raise ValueError("Editor graph exceeds the node or edge limit")
        graph.validate_connections(self.registry, require_minimums=False)
        graph.validate_feedback()

    def _to_flow(self) -> StreamlitFlowState:
        nodes: list[StreamlitFlowNode] = []
        for node in self.graph.nodes:
            spec = self.registry.resolve(node.type_id).spec
            nodes.append(
                StreamlitFlowNode(
                    node.node_id,
                    (node.position.x, node.position.y),
                    {"content": escape(f"{spec.icon} {spec.title}".strip())},
                    node_type="default"
                    if spec.inputs and spec.outputs
                    else ("input" if spec.outputs else "output"),
                    source_position="right",
                    target_position="left",
                    selectable=True,
                    selected=node.node_id == self.selected_id,
                    connectable=bool(spec.inputs or spec.outputs),
                    deletable=True,
                    style={},
                )
            )
        edges = [
            StreamlitFlowEdge(
                edge.edge_id,
                edge.src_node,
                edge.dst_node,
                label=f"{edge.src_port} -> {edge.dst_port}",
                animated=edge.edge_id in self.feedback_edge_ids,
                deletable=True,
            )
            for edge in self.graph.edges
        ]
        state = StreamlitFlowState(nodes, edges)
        if self.selected_id is not None:
            state.selected_id = self.selected_id
        return state

    def refresh_canvas(self) -> None:
        self.revision += 1
        self.flow_state = self._to_flow()

    def _commit(
        self,
        nodes: tuple[NodeInstance, ...],
        edges: tuple[Edge, ...],
        policy: GraphPolicy | None = None,
    ) -> None:
        candidate = Graph(nodes=nodes, edges=edges, policy=policy or self.graph.policy)
        self._validate(candidate)
        self.graph = candidate
        existing = {node.node_id for node in nodes} | {edge.edge_id for edge in edges}
        if self.selected_id not in existing:
            self.selected_id = None
        self.feedback_edge_ids &= frozenset(edge.edge_id for edge in edges)
        self.refresh_canvas()

    def add_node(self, type_id: str, params: Mapping[str, object] | None = None) -> None:
        node_type = self.registry.resolve(type_id)
        params = node_type.validate_params(params if params is not None else {})
        node = NodeInstance(
            node_id=uuid4().hex,
            type_id=type_id,
            params=params,
            position=Position(x=80 + len(self.graph.nodes) * 40, y=180),
        )
        self._commit((*self.graph.nodes, node), self.graph.edges)
        self.select_node(node.node_id)

    def select_node(self, node_id: str | None) -> None:
        if node_id is not None and node_id not in {node.node_id for node in self.graph.nodes}:
            raise ValueError(f"Unknown node: {node_id}")
        self.selected_id = node_id
        self.refresh_canvas()

    def remove_node(self, node_id: str) -> None:
        self.node(node_id)
        self._commit(
            tuple(node for node in self.graph.nodes if node.node_id != node_id),
            tuple(
                edge for edge in self.graph.edges if node_id not in (edge.src_node, edge.dst_node)
            ),
        )

    def node(self, node_id: str) -> NodeInstance:
        for node in self.graph.nodes:
            if node.node_id == node_id:
                return node
        raise ValueError(f"Unknown node: {node_id}")

    def move_node(self, node_id: str, position: Position) -> None:
        self.node(node_id)
        self._commit(
            tuple(
                node.model_copy(update={"position": position}) if node.node_id == node_id else node
                for node in self.graph.nodes
            ),
            self.graph.edges,
        )

    def update_params(self, node_id: str, params: Mapping[str, object]) -> None:
        node = self.node(node_id)
        validated = self.registry.resolve(node.type_id).validate_params(params)
        self._commit(
            tuple(
                item.model_copy(deep=True, update={"params": validated})
                if item.node_id == node_id
                else item
                for item in self.graph.nodes
            ),
            self.graph.edges,
        )

    def connect(self, src_node: str, src_port: str, dst_node: str, dst_port: str) -> None:
        edge = Edge(
            edge_id=uuid4().hex,
            src_node=src_node,
            src_port=src_port,
            dst_node=dst_node,
            dst_port=dst_port,
        )
        self._commit(self.graph.nodes, (*self.graph.edges, edge))

    def disconnect(self, edge_id: str) -> None:
        if edge_id not in {edge.edge_id for edge in self.graph.edges}:
            raise ValueError(f"Unknown edge: {edge_id}")
        self._commit(
            self.graph.nodes, tuple(edge for edge in self.graph.edges if edge.edge_id != edge_id)
        )

    def set_policy(self, policy: GraphPolicy) -> None:
        self._commit(self.graph.nodes, self.graph.edges, policy)

    def set_feedback_edges(self, edge_ids: frozenset[str]) -> None:
        self.graph.unroll(feedback_edge_ids=edge_ids)
        self.feedback_edge_ids = edge_ids
        self.refresh_canvas()

    def accept_canvas(self, state: StreamlitFlowState) -> None:
        originals = {node.node_id: node for node in self.graph.nodes}
        if any(node.id not in originals for node in state.nodes):
            raise ValueError("Add nodes from the palette, not the canvas menu")
        nodes = tuple(
            originals[node.id].model_copy(
                update={"position": Position.model_validate(node.position)}
            )
            for node in state.nodes
        )
        existing_edges = {edge.edge_id: edge for edge in self.graph.edges}
        edges: list[Edge] = []
        for edge in state.edges:
            if edge.id in existing_edges:
                original = existing_edges[edge.id]
                if (original.src_node, original.dst_node) != (edge.source, edge.target):
                    raise ValueError("Reconnect named ports using the Connections panel")
                edges.append(original)
            else:
                if edge.source not in originals or edge.target not in originals:
                    raise ValueError("Connection references an unknown node")
                source = self.registry.resolve(originals[edge.source].type_id).spec
                target = self.registry.resolve(originals[edge.target].type_id).spec
                if len(source.outputs) != 1 or len(target.inputs) != 1:
                    raise ValueError("Choose named ports in Connections for multi-port nodes")
                edges.append(
                    Edge(
                        edge_id=edge.id,
                        src_node=edge.source,
                        src_port=source.outputs[0].name,
                        dst_node=edge.target,
                        dst_port=target.inputs[0].name,
                    )
                )
        candidate = Graph(nodes=nodes, edges=tuple(edges), policy=self.graph.policy)
        self._validate(candidate)
        structure_changed = candidate.edges != self.graph.edges or (
            tuple(node.node_id for node in candidate.nodes)
            != tuple(node.node_id for node in self.graph.nodes)
        )
        if candidate != self.graph:
            self.notice = None
        self.graph = candidate
        node_ids = {node.node_id for node in nodes}
        # Drag-stop and pane-click both return selectedId=None in this component.
        if state.selected_id in node_ids:
            self.selected_id = state.selected_id
        elif self.selected_id not in node_ids:
            self.selected_id = None
        self.feedback_edge_ids &= frozenset(edge.edge_id for edge in edges)
        self.flow_state = state
        if structure_changed:
            self.refresh_canvas()
