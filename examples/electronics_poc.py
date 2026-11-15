"""Symbolic component labels only; deliberately not an electrical simulator."""

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict

from igomgo_nodes.core import BaseNode, Graph, NodeRegistry, NodeSpec, PortSpec

from .common import chain


class SupplyParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = "5 V"


class Supply(BaseNode):
    spec = NodeSpec(
        type_id="electronics.input",
        title="Supply",
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
        category="Symbolic electronics",
        inputs=(PortSpec(name="data", dtype="symbolic", min_connections=1),),
        outputs=(PortSpec(name="data", dtype="symbolic"),),
    )

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        return {"data": f"{inputs['data']} -> LED (symbol only, not simulated)"}


def demo() -> tuple[Graph, NodeRegistry]:
    return chain((Supply, Resistor, LED))
