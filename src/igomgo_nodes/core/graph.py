"""Versioned graph data, without UI state or domain payloads."""

from collections import Counter
from collections.abc import Iterator
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, JsonValue, model_validator

from .policy import GraphPolicy
from .ports import PortName
from .registry import NodeRegistry


class Position(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    x: FiniteFloat = 0.0
    y: FiniteFloat = 0.0


class NodeInstance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: PortName
    type_id: PortName
    params: dict[str, JsonValue] = Field(default_factory=dict)
    position: Position = Field(default_factory=Position)


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    edge_id: PortName
    src_node: PortName
    src_port: PortName
    dst_node: PortName
    dst_port: PortName


class Graph(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    nodes: tuple[NodeInstance, ...] = ()
    edges: tuple[Edge, ...] = ()
    policy: GraphPolicy = Field(default_factory=GraphPolicy)

    @model_validator(mode="after")
    def validate_structure(self) -> Self:
        node_ids = {node.node_id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("Duplicate node IDs")
        edge_ids = {edge.edge_id for edge in self.edges}
        if len(edge_ids) != len(self.edges):
            raise ValueError("Duplicate edge IDs")
        connections: set[tuple[str, str, str, str]] = set()
        for edge in self.edges:
            if edge.src_node not in node_ids or edge.dst_node not in node_ids:
                raise ValueError(f"Edge {edge.edge_id} references an unknown node")
            connection = (edge.src_node, edge.src_port, edge.dst_node, edge.dst_port)
            if connection in connections:
                raise ValueError(f"Duplicate connection at edge {edge.edge_id}")
            connections.add(connection)
        return self

    def validate_connections(
        self, registry: NodeRegistry, *, require_minimums: bool = True
    ) -> None:
        """Check registered types, directional ports, types, and connection counts."""
        node_types = {node.node_id: registry.resolve(node.type_id) for node in self.nodes}
        specs = {node_id: node_type.spec for node_id, node_type in node_types.items()}
        limits: dict[str, int | None] = {}
        loopback_modes: dict[str, str | None] = {}
        for node in self.nodes:
            node_type = node_types[node.node_id]
            params = node_type.validate_params(node.params)
            limit = node_type.input_connection_limit(params)
            if limit is not None and (type(limit) is not int or limit < 0):
                raise ValueError(f"Node {node.node_id}: input connection limit must be nonnegative")
            limits[node.node_id] = limit
            mode = node_type.direct_loopback_mode(params)
            if mode not in (None, "replace", "add"):
                raise ValueError(f"Node {node.node_id}: invalid direct loopback mode {mode!r}")
            loopback_modes[node.node_id] = mode
        inputs = {
            node_id: {port.name: port for port in spec.inputs} for node_id, spec in specs.items()
        }
        outputs = {
            node_id: {port.name: port for port in spec.outputs} for node_id, spec in specs.items()
        }
        incoming: Counter[tuple[str, str]] = Counter()
        outgoing: Counter[tuple[str, str]] = Counter()
        incoming_nodes: Counter[str] = Counter()
        direct_loopbacks: Counter[tuple[str, str]] = Counter()
        for edge in self.edges:
            source = outputs[edge.src_node].get(edge.src_port)
            target = inputs[edge.dst_node].get(edge.dst_port)
            if source is None:
                raise ValueError(
                    f"Edge {edge.edge_id}: unknown output port {edge.src_node}.{edge.src_port}"
                )
            if target is None:
                raise ValueError(
                    f"Edge {edge.edge_id}: unknown input port {edge.dst_node}.{edge.dst_port}"
                )
            if source.dtype != target.dtype and "any" not in (source.dtype, target.dtype):
                raise ValueError(
                    f"Edge {edge.edge_id}: incompatible data types {source.dtype} -> {target.dtype}"
                )
            outgoing[edge.src_node, edge.src_port] += 1
            incoming[edge.dst_node, edge.dst_port] += 1
            incoming_nodes[edge.dst_node] += 1
            if edge.src_node == edge.dst_node and loopback_modes[edge.dst_node] is not None:
                direct_loopbacks[edge.dst_node, edge.dst_port] += 1

        for node_id, limit in limits.items():
            if limit is not None and incoming_nodes[node_id] > limit:
                raise ValueError(
                    f"Node {node_id}: {incoming_nodes[node_id]} incoming connections, "
                    f"maximum is {limit}"
                )
        for (node_id, port), count in direct_loopbacks.items():
            if count > 1:
                raise ValueError(f"Node {node_id}.{port}: only one direct loopback is supported")

        for direction, ports_by_node, counts in (
            ("input", inputs, incoming),
            ("output", outputs, outgoing),
        ):
            for node_id, ports in ports_by_node.items():
                for port in ports.values():
                    count = counts[node_id, port.name]
                    if require_minimums and count < port.min_connections:
                        raise ValueError(
                            f"{direction} port {node_id}.{port.name}: {count} connections, "
                            f"minimum is {port.min_connections}"
                        )
                    if port.max_connections is not None and count > port.max_connections:
                        raise ValueError(
                            f"{direction} port {node_id}.{port.name}: {count} connections, "
                            f"maximum is {port.max_connections}"
                        )

    def strongly_connected_components(self) -> tuple[tuple[str, ...], ...]:
        """Return all SCCs in condensation order, including acyclic singletons."""
        forward: dict[str, list[str]] = {node.node_id: [] for node in self.nodes}
        reverse: dict[str, list[str]] = {node.node_id: [] for node in self.nodes}
        for edge in self.edges:
            forward[edge.src_node].append(edge.dst_node)
            reverse[edge.dst_node].append(edge.src_node)

        # Iterative Kosaraju avoids recursion limits on long consumer graphs.
        visited: set[str] = set()
        finished: list[str] = []
        for root in forward:
            if root in visited:
                continue
            visited.add(root)
            stack: list[tuple[str, Iterator[str]]] = [(root, iter(forward[root]))]
            while stack:
                node_id, children = stack[-1]
                child = next(children, None)
                if child is None:
                    finished.append(node_id)
                    stack.pop()
                elif child not in visited:
                    visited.add(child)
                    stack.append((child, iter(forward[child])))

        visited.clear()
        components: list[tuple[str, ...]] = []
        for root in reversed(finished):
            if root in visited:
                continue
            visited.add(root)
            pending = [root]
            members: list[str] = []
            while pending:
                node_id = pending.pop()
                members.append(node_id)
                for parent in reverse[node_id]:
                    if parent not in visited:
                        visited.add(parent)
                        pending.append(parent)
            components.append(tuple(members))
        return tuple(components)

    def validate_feedback(self) -> None:
        """Reject any directed cycle unless the graph-wide policy permits it."""
        if self.policy.allow_feedback:
            return
        self_loops = {edge.src_node for edge in self.edges if edge.src_node == edge.dst_node}
        for component in self.strongly_connected_components():
            if len(component) > 1 or self_loops.intersection(component):
                raise ValueError(
                    f"Graph feedback is disabled; cycle contains nodes: {', '.join(component)}"
                )

    def unroll(
        self, n: int | None = None, *, feedback_edge_ids: frozenset[str] = frozenset()
    ) -> "Graph":
        """Expand selected feedback edges into next-pass connections, without running nodes."""
        from .unroll import unroll_graph

        return unroll_graph(self, n, feedback_edge_ids)
