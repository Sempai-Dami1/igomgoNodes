"""Explicit registration of trusted consumer node classes."""

from inspect import isabstract

from .node import BaseNode, NodeSpec


class NodeRegistry:
    def __init__(self) -> None:
        self._types: dict[str, type[BaseNode]] = {}

    def register(self, node_type: type[BaseNode]) -> None:
        if not issubclass(node_type, BaseNode) or isabstract(node_type):
            raise TypeError("Only concrete BaseNode subclasses can be registered")
        spec = getattr(node_type, "spec", None)
        if not isinstance(spec, NodeSpec):
            raise TypeError("Node class must declare a NodeSpec")
        if spec.type_id in self._types:
            raise ValueError(f"Node type already registered: {spec.type_id}")
        self._types[spec.type_id] = node_type

    def resolve(self, type_id: str) -> type[BaseNode]:
        try:
            return self._types[type_id]
        except KeyError:
            raise KeyError(f"Unknown node type: {type_id}") from None

    def node_types(self) -> tuple[type[BaseNode], ...]:
        return tuple(self._types.values())
