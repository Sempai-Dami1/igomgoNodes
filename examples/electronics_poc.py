"""Symbolic electronics and an idealized numerical feedback example."""

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from igomgo_nodes.core import (
    BaseNode,
    Edge,
    Graph,
    GraphPolicy,
    LoopPolicy,
    NodeInstance,
    NodeRegistry,
    NodeSpec,
    PortSpec,
    Position,
)

from .common import chain

FEEDBACK_EDGE_ID = "sqrt-feedback"


class SupplyParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = "5 V"


class Supply(BaseNode):
    spec = NodeSpec(
        type_id="electronics.input",
        title="Supply",
        icon="electronics-supply",
        category="Symbolic electronics",
        outputs=(PortSpec(name="data", dtype="symbolic"),),
    )
    parameter_model = SupplyParams

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        return {"data": f"Supply ({self.params['label']})"}


class ResistorParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = "1 kOhm"


class Resistor(BaseNode):
    spec = NodeSpec(
        type_id="electronics.resistor",
        title="Resistor",
        category="Symbolic electronics",
        inputs=(PortSpec(name="data", dtype="symbolic", min_connections=1),),
        outputs=(PortSpec(name="data", dtype="symbolic"),),
    )
    parameter_model = ResistorParams

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        return {"data": f"{inputs['data']} -> Resistor ({self.params['label']})"}


class LED(BaseNode):
    spec = NodeSpec(
        type_id="electronics.output",
        title="LED",
        icon="electronics-led",
        category="Symbolic electronics",
        inputs=(PortSpec(name="data", dtype="symbolic", min_connections=1),),
        outputs=(PortSpec(name="data", dtype="symbolic"),),
    )

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        return {"data": f"{inputs['data']} -> LED (symbol only, not simulated)"}


def demo() -> tuple[Graph, NodeRegistry]:
    graph, registry = chain((Supply, Resistor, LED))
    nodes = tuple(
        node.model_copy(update={"position": Position(x=index * 300)})
        for index, node in enumerate(graph.nodes)
    )
    return graph.model_copy(update={"nodes": nodes}), registry


@dataclass(frozen=True)
class SquareRootState:
    radicand: float
    estimate: float


def _sqrt_state(state: object) -> SquareRootState:
    if not isinstance(state, SquareRootState):
        raise ValueError("Connect a square-root input or estimator")
    if (
        not isfinite(state.radicand)
        or state.radicand < 0
        or not isfinite(state.estimate)
        or state.estimate < 0
        or (state.radicand > 0 and state.estimate == 0)
    ):
        raise ValueError(
            "Square-root input and estimate must be finite and nonnegative; "
            "positive input requires a positive estimate"
        )
    return state


class NumberParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: float = Field(default=9, ge=0, le=10000, allow_inf_nan=False)


class NumberInput(BaseNode):
    spec = NodeSpec(
        type_id="electronics.number_input",
        title="Number input",
        category="Electronics feedback",
        outputs=(PortSpec(name="data", dtype="sqrt-state"),),
    )
    parameter_model = NumberParams

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        params = NumberParams.model_validate(self.params)
        return {"data": SquareRootState(params.value, 1.0)}


class SquareRoot(BaseNode):
    spec = NodeSpec(
        type_id="electronics.square_root",
        title="Square-root estimator",
        icon="square-root-feedback",
        category="Electronics feedback",
        inputs=(PortSpec(name="data", dtype="sqrt-state", min_connections=1, max_connections=2),),
        outputs=(PortSpec(name="data", dtype="sqrt-state", max_connections=2),),
    )

    @classmethod
    def direct_loopback_mode(cls, params: Mapping[str, JsonValue]) -> Literal["replace"]:
        return "replace"

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        values = inputs["data"]
        if not isinstance(values, list) or len(values) != 1:
            raise ValueError("Square-root estimator requires one input")
        state = _sqrt_state(values[0])
        estimate = (
            0.0 if state.radicand == 0 else 0.5 * (state.estimate + state.radicand / state.estimate)
        )
        return {"data": SquareRootState(state.radicand, estimate)}


class SquareRootOutput(BaseNode):
    spec = NodeSpec(
        type_id="electronics.sqrt_output",
        title="Square-root result",
        category="Electronics feedback",
        inputs=(PortSpec(name="data", dtype="sqrt-state", min_connections=1),),
        outputs=(PortSpec(name="estimate", dtype="number"),),
    )

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        return {"estimate": _sqrt_state(inputs["data"]).estimate}


def feedback_demo() -> tuple[Graph, NodeRegistry]:
    registry = NodeRegistry()
    for node_type in (NumberInput, SquareRoot, SquareRootOutput):
        registry.register(node_type)
    return (
        Graph(
            nodes=(
                NodeInstance(node_id="input", type_id="electronics.number_input"),
                NodeInstance(
                    node_id="sqrt", type_id="electronics.square_root", position=Position(x=300)
                ),
                NodeInstance(
                    node_id="output", type_id="electronics.sqrt_output", position=Position(x=650)
                ),
            ),
            edges=(
                Edge(
                    edge_id="input-sqrt",
                    src_node="input",
                    src_port="data",
                    dst_node="sqrt",
                    dst_port="data",
                ),
                Edge(
                    edge_id=FEEDBACK_EDGE_ID,
                    src_node="sqrt",
                    src_port="data",
                    dst_node="sqrt",
                    dst_port="data",
                ),
                Edge(
                    edge_id="sqrt-output",
                    src_node="sqrt",
                    src_port="data",
                    dst_node="output",
                    dst_port="data",
                ),
            ),
            policy=GraphPolicy(
                allow_feedback=True, loop=LoopPolicy(max_iterations=8, timeout_seconds=10)
            ),
        ),
        registry,
    )
