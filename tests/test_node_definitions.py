from collections.abc import Mapping

import pytest
from pydantic import ValidationError

from igomgo_nodes.core import BaseNode, NodeRegistry, NodeSpec, PortSpec


class NotNode(BaseNode):
    spec = NodeSpec(
        type_id="logic.not",
        title="NOT",
        inputs=(PortSpec(name="value", dtype="bool"),),
        outputs=(PortSpec(name="result", dtype="bool", max_connections=None),),
    )

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        return {"result": not inputs["value"]}


@pytest.mark.parametrize(
    ("minimum", "maximum"),
    [(-1, 1), (0, -1), (2, 1), (0, True), (0, 1.5)],
)
def test_invalid_connection_limits(minimum: object, maximum: object) -> None:
    with pytest.raises(ValidationError):
        PortSpec.model_validate(
            {
                "name": "value",
                "dtype": "bool",
                "min_connections": minimum,
                "max_connections": maximum,
            }
        )


@pytest.mark.parametrize("name", ["", "   "])
def test_empty_port_names_are_rejected(name: str) -> None:
    with pytest.raises(ValidationError):
        PortSpec(name=name, dtype="bool")


def test_spec_round_trip_preserves_unlimited_and_zero_limits() -> None:
    spec = NodeSpec(
        type_id="test.source",
        title="Source",
        max_inputs=0,
        outputs=(PortSpec(name="value", dtype="any", min_connections=2, max_connections=None),),
        max_outputs=1,
    )
    assert NodeSpec.model_validate_json(spec.model_dump_json()) == spec


@pytest.mark.parametrize("direction", ["inputs", "outputs"])
def test_duplicate_port_names_are_rejected(direction: str) -> None:
    port = {"name": "value", "dtype": "bool"}
    with pytest.raises(ValidationError, match="Duplicate"):
        NodeSpec.model_validate({"type_id": "test", "title": "Test", direction: [port, port]})


@pytest.mark.parametrize("direction", ["inputs", "outputs"])
def test_node_port_limit_is_enforced(direction: str) -> None:
    with pytest.raises(ValidationError, match="exceed"):
        NodeSpec.model_validate(
            {
                "type_id": "test",
                "title": "Test",
                direction: [{"name": "value", "dtype": "bool"}],
                f"max_{direction}": 0,
            }
        )


def test_same_name_is_allowed_across_input_and_output() -> None:
    port = PortSpec(name="value", dtype="bool")
    NodeSpec(type_id="test", title="Test", inputs=(port,), outputs=(port,))


def test_consumer_processing_and_registry() -> None:
    registry = NodeRegistry()
    registry.register(NotNode)
    node = registry.resolve("logic.not")("instance-1")
    assert node.process({"value": True}) == {"result": False}
    assert node.process({"value": False}) == {"result": True}
    with pytest.raises(ValueError, match="already registered"):
        registry.register(NotNode)
    with pytest.raises(KeyError, match="Unknown node type"):
        registry.resolve("unknown")


def test_registry_rejects_abstract_or_missing_spec() -> None:
    class MissingSpec(BaseNode):
        def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
            return {}

    registry = NodeRegistry()
    with pytest.raises(TypeError, match="concrete"):
        registry.register(BaseNode)
    with pytest.raises(TypeError, match="NodeSpec"):
        registry.register(MissingSpec)


def test_node_instances_do_not_share_nested_parameters() -> None:
    params = {"settings": {"gain": 1}}
    first = NotNode("first", params)
    second = NotNode("second", params)
    settings = first.params["settings"]
    assert isinstance(settings, dict)
    settings["gain"] = 2
    assert second.params == {"settings": {"gain": 1}}
    assert params == {"settings": {"gain": 1}}
    with pytest.raises(ValueError, match="node_id"):
        NotNode(" ")


def test_non_json_parameters_are_rejected() -> None:
    with pytest.raises(ValidationError):
        NotNode("invalid", {"value": object()})
