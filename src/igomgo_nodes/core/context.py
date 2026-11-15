"""Metadata provided to consumer processing without changing its signature."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RunContext:
    original_node_id: str
    iteration: int
    max_iterations: int
