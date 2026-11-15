"""Graph-wide permission and finite limits for feedback execution."""

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

IterationCount = Annotated[int, Field(gt=0, strict=True)]


class LoopPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_iterations: IterationCount
    timeout_seconds: Annotated[float, Field(gt=0, allow_inf_nan=False, strict=True)]
    capture_every: IterationCount = 1


class GraphPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    allow_feedback: Annotated[bool, Field(strict=True)] = False
    loop: LoopPolicy | None = None

    @model_validator(mode="after")
    def validate_loop_permission(self) -> Self:
        if self.allow_feedback and self.loop is None:
            raise ValueError("Feedback requires a LoopPolicy")
        if not self.allow_feedback and self.loop is not None:
            raise ValueError("LoopPolicy requires feedback permission")
        return self
