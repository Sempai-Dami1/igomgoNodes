"""Browser-transfer and local-disk stores for validated editor graph documents."""

import json
import math
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal, Protocol, cast, runtime_checkable

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from igomgo_nodes.core import Graph, NodeRegistry, dumps_graph, loads_graph
from igomgo_nodes.core.serialization import SCHEMA_VERSION, validate_graph_document

MAX_EDITOR_FILE_BYTES = 25 * 1024 * 1024
EDITOR_FILE_FORMAT = "igomgo.editor-graph"
EDITOR_FILE_VERSION = 1
DEFAULT_GRAPH_FILENAME = "graph.igomgo.json"


class GraphDocument(BaseModel):
    """A graph plus editor-only feedback boundaries, separate from core graph JSON."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format: Literal["igomgo.editor-graph"]
    format_version: Literal[1]
    graph: Graph
    feedback_edge_ids: tuple[str, ...] = ()

    @field_validator("format_version", mode="before")
    @classmethod
    def require_integer_version(cls, value: object) -> object:
        if type(value) is not int or value != EDITOR_FILE_VERSION:
            raise ValueError(f"Unsupported editor file version: {value!r}")
        return value

    @field_validator("feedback_edge_ids", mode="before")
    @classmethod
    def require_string_edge_ids(cls, value: object) -> object:
        if not isinstance(value, (tuple, list)) or any(not isinstance(item, str) for item in value):
            raise ValueError("Feedback edge IDs must be an array of strings")
        return value

    @model_validator(mode="before")
    @classmethod
    def migrate_graph_schema(cls, value: object) -> object:
        if isinstance(value, dict):
            graph = value.get("graph")
            if isinstance(graph, dict):
                return {**value, "graph": validate_graph_document(graph)}
        return value

    @model_validator(mode="after")
    def validate_feedback_edges(self) -> "GraphDocument":
        if (
            type(self.graph.schema_version) is not int
            or self.graph.schema_version != SCHEMA_VERSION
        ):
            raise ValueError(f"Graph schema_version must be integer {SCHEMA_VERSION}")
        if len(set(self.feedback_edge_ids)) != len(self.feedback_edge_ids):
            raise ValueError("Feedback edge IDs must be unique")
        known_ids = {edge.edge_id for edge in self.graph.edges}
        if not set(self.feedback_edge_ids) <= known_ids:
            raise ValueError("Feedback edge IDs must reference edges in the graph")
        if self.feedback_edge_ids:
            self.graph.unroll(feedback_edge_ids=frozenset(self.feedback_edge_ids))
        return self


@runtime_checkable
class GraphStore(Protocol):
    """Byte-oriented interface for importing and exporting editor graph documents."""

    def serialize(self, graph: Graph, feedback_edge_ids: frozenset[str] = frozenset()) -> bytes: ...

    def deserialize(self, data: bytes, registry: NodeRegistry) -> GraphDocument: ...


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


class BrowserFileStore:
    """Convert editor documents to and from bytes for Streamlit download/upload widgets."""

    def serialize(self, graph: Graph, feedback_edge_ids: frozenset[str] = frozenset()) -> bytes:
        graph_json = dumps_graph(graph)
        document = GraphDocument(
            format=EDITOR_FILE_FORMAT,
            format_version=EDITOR_FILE_VERSION,
            graph=graph,
            feedback_edge_ids=tuple(sorted(feedback_edge_ids)),
        )
        value = document.model_dump(mode="json", warnings="error")
        value["graph"] = json.loads(graph_json)
        try:
            payload = json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2).encode(
                "utf-8"
            )
        except RecursionError as error:
            raise ValueError("Editor graph JSON nesting is too deep") from error
        if len(payload) > MAX_EDITOR_FILE_BYTES:
            raise ValueError("Editor graph file exceeds the 25 MiB limit")
        return payload

    def deserialize(self, data: bytes, registry: NodeRegistry) -> GraphDocument:
        if len(data) > MAX_EDITOR_FILE_BYTES:
            raise ValueError("Editor graph file exceeds the 25 MiB limit")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("Editor graph file must be UTF-8 JSON") from error
        if len(text.encode("utf-8")) > MAX_EDITOR_FILE_BYTES:
            raise ValueError("Editor graph file exceeds the 25 MiB limit")
        try:
            parsed: object = json.loads(
                text,
                object_pairs_hook=_object,
                parse_constant=_reject_constant,
                parse_float=_finite_float,
            )
        except RecursionError as error:
            raise ValueError("Editor graph JSON nesting is too deep") from error
        if not isinstance(parsed, dict):
            raise ValueError("Editor graph file must be a JSON object")
        value = cast(dict[str, object], parsed)
        if "format" not in value:
            graph = loads_graph(data, registry)
            document = GraphDocument(
                format=EDITOR_FILE_FORMAT,
                format_version=EDITOR_FILE_VERSION,
                graph=graph,
            )
            self._validate_node_parameters(document, registry)
            return document
        document = GraphDocument.model_validate(value)
        self._validate_node_parameters(document, registry)
        return document

    @staticmethod
    def _validate_node_parameters(document: GraphDocument, registry: NodeRegistry) -> None:
        for node in document.graph.nodes:
            registry.resolve(node.type_id).validate_params(node.params)


class LocalJsonStore(BrowserFileStore):
    """Persist validated graph documents under one configured local directory."""

    def __init__(self, directory: str | Path = "saved_graphs") -> None:
        self.directory = Path(directory).expanduser().resolve()

    def save(
        self,
        graph: Graph,
        name: str = DEFAULT_GRAPH_FILENAME,
        feedback_edge_ids: frozenset[str] = frozenset(),
    ) -> Path:
        payload = self.serialize(graph, feedback_edge_ids)
        target = self._path(name)
        self.directory.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            raise ValueError("Refusing to overwrite a symbolic link")
        temporary_path: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="wb", dir=self.directory, prefix=".igomgo-", suffix=".tmp", delete=False
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(payload)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, target)
        except OSError:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
            raise
        return target

    def load(self, registry: NodeRegistry, name: str = DEFAULT_GRAPH_FILENAME) -> GraphDocument:
        path = self._path(name)
        if path.is_symlink():
            raise ValueError("Refusing to load a symbolic link")
        with path.open("rb") as source:
            data = source.read(MAX_EDITOR_FILE_BYTES + 1)
        if len(data) > MAX_EDITOR_FILE_BYTES:
            raise ValueError("Editor graph file exceeds the 25 MiB limit")
        return self.deserialize(data, registry)

    def _path(self, name: str) -> Path:
        invalid = '<>:"/\\|?*'
        if (
            not name
            or len(name) > 128
            or name in {".", ".."}
            or any(character in invalid or ord(character) < 32 for character in name)
            or not name.endswith(".igomgo.json")
        ):
            raise ValueError("Use a filename ending in .igomgo.json without path separators")
        return self.directory / name
