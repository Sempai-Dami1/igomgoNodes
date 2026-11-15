import json

import pytest

from examples.editor_demo import demo_graph, demo_registry
from igomgo_nodes.core import Edge, Graph, GraphPolicy, LoopPolicy, dumps_graph
from igomgo_nodes.storage import (
    MAX_EDITOR_FILE_BYTES,
    BrowserFileStore,
    GraphStore,
    LocalJsonStore,
)


def _feedback_graph() -> Graph:
    base = demo_graph()
    return Graph(
        nodes=base.nodes,
        edges=(
            *base.edges,
            Edge(
                edge_id="feedback",
                src_node="out",
                src_port="value",
                dst_node="stage",
                dst_port="value",
            ),
        ),
        policy=GraphPolicy(
            allow_feedback=True, loop=LoopPolicy(max_iterations=2, timeout_seconds=1)
        ),
    )


def test_browser_store_round_trips_graph_and_editor_feedback_boundaries() -> None:
    store: GraphStore = BrowserFileStore()
    graph = _feedback_graph()
    payload = store.serialize(graph, frozenset({"feedback"}))
    restored = store.deserialize(payload, demo_registry())

    assert restored.graph == graph
    assert restored.feedback_edge_ids == ("feedback",)
    assert b'"igomgo.editor-graph"' in payload


def test_browser_store_accepts_core_graph_json_and_starts_without_editor_metadata() -> None:
    restored = BrowserFileStore().deserialize(
        dumps_graph(demo_graph()).encode("utf-8"), demo_registry()
    )

    assert restored.graph == demo_graph()
    assert restored.feedback_edge_ids == ()


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"\xff", "UTF-8"),
        (b"[]", "object"),
        (b'{"format":"unknown"}', "format"),
        (b'{"format":"igomgo.editor-graph","format_version":2}', "format_version"),
        (b'{"format":"igomgo.editor-graph","format_version":true,"graph":{}}', "version"),
        (b'{"format":"igomgo.editor-graph","format_version":1,"format_version":1}', "Duplicate"),
        (b" " * (MAX_EDITOR_FILE_BYTES + 1), "25 MiB"),
    ],
)
def test_browser_store_rejects_malformed_or_unsupported_documents(
    payload: bytes, message: str
) -> None:
    with pytest.raises((ValueError, json.JSONDecodeError), match=message):
        BrowserFileStore().deserialize(payload, demo_registry())


def test_browser_store_requires_an_integer_graph_schema_version() -> None:
    store = BrowserFileStore()
    value = json.loads(store.serialize(demo_graph()))
    value["graph"]["schema_version"] = True
    with pytest.raises(ValueError, match="Graph schema_version"):
        store.deserialize(json.dumps(value).encode(), demo_registry())

    invalid_graph = demo_graph().model_copy(update={"schema_version": True})
    with pytest.raises(ValueError, match="Graph schema_version"):
        store.serialize(invalid_graph)


def test_browser_store_rejects_invalid_feedback_boundaries_and_unknown_types() -> None:
    store = BrowserFileStore()
    with pytest.raises(ValueError, match="reference edges"):
        store.serialize(demo_graph(), frozenset({"missing"}))
    unknown_graph = demo_graph().model_dump(mode="json")
    unknown_graph["nodes"][0]["type_id"] = "logic.not-registered"
    payload = json.dumps(
        {
            "format": "igomgo.editor-graph",
            "format_version": 1,
            "graph": unknown_graph,
            "feedback_edge_ids": [],
        }
    ).encode()
    with pytest.raises(KeyError, match="logic.not-registered"):
        store.deserialize(payload, demo_registry())


def test_browser_store_rejects_invalid_consumer_parameters() -> None:
    graph_data = demo_graph().model_dump(mode="json")
    graph_data["nodes"][0]["params"] = {"value": "not a boolean"}
    payload = json.dumps(
        {
            "format": "igomgo.editor-graph",
            "format_version": 1,
            "graph": graph_data,
            "feedback_edge_ids": [],
        }
    ).encode()

    with pytest.raises(ValueError):
        BrowserFileStore().deserialize(payload, demo_registry())


def test_local_store_saves_atomically_and_loads_with_the_same_codec(tmp_path) -> None:
    store = LocalJsonStore(tmp_path / "graphs")
    target = store.save(_feedback_graph(), "demo.igomgo.json", frozenset({"feedback"}))
    assert target == (tmp_path / "graphs" / "demo.igomgo.json").resolve()
    assert target.exists()
    assert list(target.parent.glob(".igomgo-*.tmp")) == []

    document = store.load(demo_registry(), "demo.igomgo.json")
    assert document.graph == _feedback_graph()
    assert document.feedback_edge_ids == ("feedback",)

    store.save(demo_graph(), "demo.igomgo.json")
    assert store.load(demo_registry(), "demo.igomgo.json").graph == demo_graph()


@pytest.mark.parametrize(
    "name",
    [
        "",
        "..\\outside.igomgo.json",
        "../outside.igomgo.json",
        "C:\\outside.igomgo.json",
        "nested/name.igomgo.json",
        "graph.json",
        "bad?.igomgo.json",
    ],
)
def test_local_store_rejects_unsafe_or_invalid_filenames(tmp_path, name: str) -> None:
    with pytest.raises(ValueError, match="filename"):
        LocalJsonStore(tmp_path).save(demo_graph(), name)


def test_local_store_rejects_oversized_files_before_reading(tmp_path) -> None:
    store = LocalJsonStore(tmp_path)
    tmp_path.mkdir(exist_ok=True)
    target = tmp_path / "large.igomgo.json"
    target.write_bytes(b" " * (MAX_EDITOR_FILE_BYTES + 1))

    with pytest.raises(ValueError, match="25 MiB"):
        store.load(demo_registry(), target.name)
