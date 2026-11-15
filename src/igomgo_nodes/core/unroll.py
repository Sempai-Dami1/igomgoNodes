"""Finite expansion of explicitly selected feedback boundaries."""

from dataclasses import dataclass

from .graph import Edge, Graph, NodeInstance
from .policy import GraphPolicy

MAX_EXPANDED_NODES = 10_000
MAX_EXPANDED_EDGES = 100_000


@dataclass(frozen=True)
class StepInfo:
    original_node_id: str
    component: int
    iteration: int
    cyclic: bool


@dataclass(frozen=True)
class ExpansionPlan:
    graph: Graph
    steps: dict[str, StepInfo]


def _unique_id(base: str, used: set[str]) -> str:
    candidate = base
    suffix = 1
    while candidate in used:
        candidate = f"{base}.{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def unroll_graph(graph: Graph, iterations: int | None, feedback_edge_ids: frozenset[str]) -> Graph:
    return plan_graph(graph, iterations, feedback_edge_ids).graph


def plan_graph(
    graph: Graph, iterations: int | None, feedback_edge_ids: frozenset[str]
) -> ExpansionPlan:
    graph.validate_feedback()
    if iterations is not None and (type(iterations) is not int or iterations < 1):
        raise ValueError("iterations must be a positive integer")
    loop = graph.policy.loop
    if loop is not None and iterations is not None and iterations > loop.max_iterations:
        raise ValueError("iterations cannot exceed LoopPolicy.max_iterations")
    count = iterations if iterations is not None else (loop.max_iterations if loop else 1)
    edge_ids = {edge.edge_id for edge in graph.edges}
    unknown = feedback_edge_ids - edge_ids
    if unknown:
        raise ValueError(f"Unknown feedback edge IDs: {', '.join(sorted(unknown))}")

    components = graph.strongly_connected_components()
    component_by_node = {
        node_id: index for index, component in enumerate(components) for node_id in component
    }
    self_loops = {edge.src_node for edge in graph.edges if edge.src_node == edge.dst_node}
    cyclic_components = {
        index
        for index, component in enumerate(components)
        if len(component) > 1 or self_loops.intersection(component)
    }
    cyclic_nodes = {
        node_id for node_id, index in component_by_node.items() if index in cyclic_components
    }
    for edge in graph.edges:
        if edge.edge_id in feedback_edge_ids and (
            edge.src_node not in cyclic_nodes
            or component_by_node[edge.src_node] != component_by_node[edge.dst_node]
        ):
            raise ValueError(f"Feedback edge {edge.edge_id} must be inside a cyclic component")

    # The consumer's chosen cuts, rather than node declaration order, define each pass.
    remaining = Graph(
        nodes=graph.nodes,
        edges=tuple(edge for edge in graph.edges if edge.edge_id not in feedback_edge_ids),
    )
    try:
        remaining.validate_feedback()
    except ValueError as error:
        raise ValueError("Selected feedback edges do not break every cycle") from error

    expanded_node_count = len(graph.nodes) + len(cyclic_nodes) * (count - 1)
    expanded_edge_count = 0
    for edge in graph.edges:
        same_cycle = (
            edge.src_node in cyclic_nodes
            and component_by_node[edge.src_node] == component_by_node[edge.dst_node]
        )
        expanded_edge_count += (
            count - 1 if edge.edge_id in feedback_edge_ids else count if same_cycle else 1
        )
    if expanded_node_count > MAX_EXPANDED_NODES:
        raise ValueError(f"Expanded graph exceeds the {MAX_EXPANDED_NODES}-node limit")
    if expanded_edge_count > MAX_EXPANDED_EDGES:
        raise ValueError(f"Expanded graph exceeds the {MAX_EXPANDED_EDGES}-edge limit")

    used_node_ids = {node.node_id for node in graph.nodes}
    copies: dict[tuple[str, int], str] = {}
    steps: dict[str, StepInfo] = {}
    nodes: list[NodeInstance] = []
    for node in graph.nodes:
        passes = count if node.node_id in cyclic_nodes else 1
        for iteration in range(passes):
            node_id = (
                node.node_id
                if iteration == 0
                else _unique_id(f"{node.node_id}@{iteration + 1}", used_node_ids)
            )
            copies[node.node_id, iteration] = node_id
            steps[node_id] = StepInfo(
                node.node_id,
                component_by_node[node.node_id],
                iteration + 1,
                node.node_id in cyclic_nodes,
            )
            nodes.append(node.model_copy(deep=True, update={"node_id": node_id}))

    used_edge_ids = set(edge_ids)
    edges: list[Edge] = []
    for edge in graph.edges:
        same_cycle = (
            edge.src_node in cyclic_nodes
            and component_by_node[edge.src_node] == component_by_node[edge.dst_node]
        )
        if same_cycle:
            feedback = edge.edge_id in feedback_edge_ids
            for iteration in range(count - 1 if feedback else count):
                edge_id = (
                    edge.edge_id
                    if iteration == 0
                    else _unique_id(f"{edge.edge_id}@{iteration + 1}", used_edge_ids)
                )
                edges.append(
                    edge.model_copy(
                        update={
                            "edge_id": edge_id,
                            "src_node": copies[edge.src_node, iteration],
                            "dst_node": copies[edge.dst_node, iteration + int(feedback)],
                        }
                    )
                )
        else:
            source_pass = count - 1 if edge.src_node in cyclic_nodes else 0
            edges.append(
                edge.model_copy(
                    update={
                        "src_node": copies[edge.src_node, source_pass],
                        "dst_node": copies[edge.dst_node, 0],
                    }
                )
            )

    expanded = Graph(nodes=tuple(nodes), edges=tuple(edges), policy=GraphPolicy())
    expanded.validate_feedback()
    return ExpansionPlan(expanded, steps)
