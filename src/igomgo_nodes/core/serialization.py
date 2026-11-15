"""Bounded JSON interchange for graph data; never imports or executes node code."""

import json
import math
from typing import cast

from .graph import Graph
from .registry import NodeRegistry
from .unroll import MAX_EXPANDED_EDGES, MAX_EXPANDED_NODES

SCHEMA_VERSION = 1
MAX_GRAPH_BYTES = 25 * 1024 * 1024


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise ValueError(f"Non-finite JSON number: {value}")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Non-finite JSON number: {value}")
    return number


def _check_collections(data: dict[str, object]) -> None:
    for name, limit in (("nodes", MAX_EXPANDED_NODES), ("edges", MAX_EXPANDED_EDGES)):
        collection = data.get(name, [])
        if not isinstance(collection, list):
            raise ValueError(f"Graph {name} must be a JSON array")
        if len(collection) > limit:
            raise ValueError(f"Graph exceeds the {limit}-{name} limit")


def dumps_graph(graph: Graph) -> str:
    """Export a structurally valid graph, including incomplete editing states."""
    data = graph.model_dump(mode="json", warnings="error")
    _check_collections(data)
    # Mutable parameter dictionaries must be revalidated at the export boundary.
    Graph.model_validate(data)
    try:
        text = json.dumps(data, ensure_ascii=True, allow_nan=False, indent=2)
    except RecursionError as error:
        raise ValueError("Graph JSON nesting is too deep") from error
    if len(text.encode("utf-8")) > MAX_GRAPH_BYTES:
        raise ValueError("Graph JSON exceeds the 25 MiB limit")
    return text


def loads_graph(data: str | bytes, registry: NodeRegistry) -> Graph:
    """Import UTF-8 schema-v1 graph JSON using only explicitly registered node types."""
    if len(data) > MAX_GRAPH_BYTES:
        raise ValueError("Graph JSON exceeds the 25 MiB limit")
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    if len(data.encode("utf-8")) > MAX_GRAPH_BYTES:
        raise ValueError("Graph JSON exceeds the 25 MiB limit")
    try:
        parsed: object = json.loads(
            data,
            object_pairs_hook=_object,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except RecursionError as error:
        raise ValueError("Graph JSON nesting is too deep") from error
    if not isinstance(parsed, dict):
        raise ValueError("Graph JSON must be an object")
    document = cast(dict[str, object], parsed)
    version = document.get("schema_version")
    if type(version) is not int or version != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported or missing schema_version: {version!r}; expected {SCHEMA_VERSION}"
        )
    _check_collections(document)
    graph = Graph.model_validate(document)
    for node in graph.nodes:
        registry.resolve(node.type_id)
    return graph
