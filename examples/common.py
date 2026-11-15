"""Small graph-builder shared by the proof-of-concept consumers."""

from igomgo_nodes.core import BaseNode, Edge, Graph, NodeInstance, NodeRegistry, Position


def chain(node_types: tuple[type[BaseNode], ...]) -> tuple[Graph, NodeRegistry]:
    registry = NodeRegistry()
    nodes: list[NodeInstance] = []
    edges: list[Edge] = []
    for index, node_type in enumerate(node_types):
        registry.register(node_type)
        node_id = node_type.spec.type_id.rsplit(".", 1)[-1]
        nodes.append(
            NodeInstance(
                node_id=node_id,
                type_id=node_type.spec.type_id,
                params=node_type.validate_params({}),
                position=Position(x=index * 220),
            )
        )
        if index:
            previous = node_types[index - 1]
            edges.append(
                Edge(
                    edge_id=f"{nodes[-2].node_id}-{node_id}",
                    src_node=nodes[-2].node_id,
                    src_port=previous.spec.outputs[0].name,
                    dst_node=node_id,
                    dst_port=node_type.spec.inputs[0].name,
                )
            )
    return Graph(nodes=tuple(nodes), edges=tuple(edges)), registry
