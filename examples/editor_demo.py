"""Tiny logic consumer used by the editor demo; no domain logic belongs in core."""

from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from igomgo_nodes.core import (
    BaseNode,
    Edge,
    Graph,
    NodeInstance,
    NodeRegistry,
    NodeSpec,
    PortSpec,
    Position,
)


class ConstantParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: bool = True


class Constant(BaseNode):
    parameter_model = ConstantParams
    spec = NodeSpec(
        type_id="logic.constant",
        title="Boolean input",
        category="Logic",
        outputs=(PortSpec(name="value", dtype="bool", max_connections=None),),
    )

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        return {"value": self.params["value"]}


class Not(BaseNode):
    spec = NodeSpec(
        type_id="logic.not",
        title="NOT",
        category="Logic",
        inputs=(PortSpec(name="value", dtype="bool", min_connections=1),),
        outputs=(PortSpec(name="value", dtype="bool", max_connections=None),),
    )

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        return {"value": not inputs["value"]}


class And(BaseNode):
    spec = NodeSpec(
        type_id="logic.and",
        title="AND",
        category="Logic",
        inputs=tuple(PortSpec(name=name, dtype="bool", min_connections=1) for name in ("a", "b")),
        outputs=(PortSpec(name="value", dtype="bool", max_connections=None),),
    )

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        return {"value": bool(inputs["a"]) and bool(inputs["b"])}


class Display(BaseNode):
    spec = NodeSpec(
        type_id="logic.display",
        title="Output",
        category="Logic",
        inputs=(PortSpec(name="value", dtype="bool", min_connections=1),),
        outputs=(PortSpec(name="value", dtype="bool", max_connections=None),),
    )

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        return {"value": inputs["value"]}


class Or(And):
    spec = And.spec.model_copy(update={"type_id": "logic.or", "title": "OR"})

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        return {"value": bool(inputs["a"]) or bool(inputs["b"])}


class Xor(And):
    spec = And.spec.model_copy(update={"type_id": "logic.xor", "title": "XOR"})

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        return {"value": bool(inputs["a"]) != bool(inputs["b"])}


class FeedbackParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_incoming: int = Field(default=2, ge=1, le=8, strict=True)
    graph_loopback: Literal["replace", "add"] = "replace"
    internal_loopback: Literal["replace", "add"] = "replace"
    internal_iterations: int = Field(default=0, ge=0, le=8, strict=True)


class FeedbackNot(BaseNode):
    """Small consumer example: invert a Boolean fan-in, optionally feeding it back."""

    spec = NodeSpec(
        type_id="logic.feedback_not",
        title="Configurable feedback NOT",
        category="Logic",
        inputs=(PortSpec(name="value", dtype="bool", max_connections=None),),
        outputs=(PortSpec(name="value", dtype="bool", max_connections=None),),
    )
    parameter_model = FeedbackParams

    @classmethod
    def input_connection_limit(cls, params: Mapping[str, JsonValue]) -> int:
        return FeedbackParams.model_validate(params).max_incoming

    @classmethod
    def direct_loopback_mode(cls, params: Mapping[str, JsonValue]) -> Literal["replace", "add"]:
        return FeedbackParams.model_validate(params).graph_loopback

    def combine_loopback(self, port: str, original: object, feedback: object) -> object:
        if not isinstance(original, list) or not all(isinstance(value, bool) for value in original):
            raise ValueError("Expected Boolean original inputs")
        if not isinstance(feedback, bool):
            raise ValueError("Expected Boolean feedback")
        return [any(original) or feedback]

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        values = inputs["value"]
        if not isinstance(values, list) or not all(isinstance(value, bool) for value in values):
            raise ValueError("Expected Boolean inputs")
        params = FeedbackParams.model_validate(self.params)
        original = any(values)
        output = not original
        for _ in range(params.internal_iterations):
            output = not (original or output if params.internal_loopback == "add" else output)
        return {"value": output}


def demo_registry() -> NodeRegistry:
    registry = NodeRegistry()
    for node_type in (Constant, Not, And, Or, Xor, Display, FeedbackNot):
        registry.register(node_type)
    return registry


def demo_graph() -> Graph:
    return Graph(
        nodes=(
            NodeInstance(node_id="in", type_id="logic.constant", params={"value": True}),
            NodeInstance(node_id="stage", type_id="logic.not", position=Position(x=240)),
            NodeInstance(node_id="out", type_id="logic.display", position=Position(x=480)),
        ),
        edges=(
            Edge(
                edge_id="in-stage",
                src_node="in",
                src_port="value",
                dst_node="stage",
                dst_port="value",
            ),
            Edge(
                edge_id="stage-out",
                src_node="stage",
                src_port="value",
                dst_node="out",
                dst_port="value",
            ),
        ),
    )
