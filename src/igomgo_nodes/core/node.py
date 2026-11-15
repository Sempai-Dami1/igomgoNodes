"""Consumer-defined nodes and their serializable metadata."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from copy import deepcopy
from typing import ClassVar, Self

from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter, model_validator

from .context import RunContext
from .ports import ConnectionCount, PortName, PortSpec

_PARAMETERS = TypeAdapter(dict[str, JsonValue])


class NodeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type_id: PortName
    title: PortName
    icon: str = ""
    category: PortName = "General"
    inputs: tuple[PortSpec, ...] = ()
    outputs: tuple[PortSpec, ...] = ()
    max_inputs: ConnectionCount | None = None
    max_outputs: ConnectionCount | None = None

    @model_validator(mode="after")
    def validate_ports(self) -> Self:
        for direction, ports, limit in (
            ("input", self.inputs, self.max_inputs),
            ("output", self.outputs, self.max_outputs),
        ):
            names = [port.name for port in ports]
            if len(set(names)) != len(names):
                raise ValueError(f"Duplicate {direction} port names")
            if limit is not None and len(ports) > limit:
                raise ValueError(f"Declared {direction} ports exceed the node limit")
        return self


class BaseNode(ABC):
    spec: ClassVar[NodeSpec]
    parameter_model: ClassVar[type[BaseModel] | None] = None

    def __init__(self, node_id: str, params: Mapping[str, object] | None = None) -> None:
        if not node_id.strip():
            raise ValueError("node_id must not be empty")
        self.node_id = node_id
        self.context: RunContext | None = None
        self.params = self.validate_params(params if params is not None else {})

    @classmethod
    def validate_params(cls, params: Mapping[str, object]) -> dict[str, JsonValue]:
        if cls.parameter_model is not None:
            validated = cls.parameter_model.model_validate(dict(params))
            return _PARAMETERS.validate_python(validated.model_dump(mode="json"))
        return deepcopy(_PARAMETERS.validate_python(dict(params)))

    @abstractmethod
    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        """Return values keyed by output port name; consumers own the processing."""
