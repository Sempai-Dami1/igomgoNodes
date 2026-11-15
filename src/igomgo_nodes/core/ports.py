"""Serializable declarations of node ports."""

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

ConnectionCount = Annotated[int, Field(ge=0, strict=True)]
PortName = Annotated[str, Field(min_length=1, pattern=r"\S")]


class PortSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: PortName
    dtype: PortName
    min_connections: ConnectionCount = 0
    max_connections: ConnectionCount | None = 1

    @model_validator(mode="after")
    def validate_connection_range(self) -> Self:
        if self.max_connections is not None and self.min_connections > self.max_connections:
            raise ValueError("min_connections cannot exceed max_connections")
        return self
