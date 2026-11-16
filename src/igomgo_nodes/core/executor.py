"""Bounded execution of trusted consumer nodes in an isolated spawned process."""

import multiprocessing
import pickle
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from graphlib import TopologicalSorter
from heapq import heappop, heappush
from multiprocessing.connection import Connection
from multiprocessing.reduction import ForkingPickler
from time import monotonic

from .context import RunContext
from .graph import Edge, Graph
from .registry import NodeRegistry
from .unroll import ExpansionPlan, plan_graph

MAX_RUN_SECONDS = 60.0
MAX_CAPTURE_BYTES = 16 * 1024 * 1024
MAX_CAPTURES = 1000


@dataclass(frozen=True)
class Snapshot:
    component: tuple[str, ...]
    iteration: int
    outputs: dict[str, dict[str, object]]


@dataclass
class RunResult:
    outputs: dict[str, dict[str, object]] = field(default_factory=dict)
    snapshots: list[Snapshot] = field(default_factory=list)
    timed_out: bool = False


class ExecutionError(RuntimeError):
    """Consumer processing or worker communication failed."""


def _send(connection: Connection, message: object) -> None:
    # Only trusted local worker messages use pickle, never uploaded graph data.
    payload = pickle.dumps(message, protocol=pickle.HIGHEST_PROTOCOL)
    if len(payload) > MAX_CAPTURE_BYTES:
        raise ExecutionError("Worker message exceeds the 16 MiB result limit")
    connection.send_bytes(payload)


def _run_worker(
    connection: Connection,
    plan: ExpansionPlan,
    registry: NodeRegistry,
    capture_every: int,
    max_iterations: int,
    inputs: dict[str, dict[str, object]],
) -> None:
    try:
        _process(connection, plan, registry, capture_every, max_iterations, inputs)
        _send(connection, ("done", None))
    except Exception as error:
        _send(connection, ("error", f"{type(error).__name__}: {error}"))
    finally:
        connection.close()


def _process(
    connection: Connection,
    plan: ExpansionPlan,
    registry: NodeRegistry,
    capture_every: int,
    max_iterations: int,
    external_inputs: dict[str, dict[str, object]],
) -> None:
    nodes = {node.node_id: node for node in plan.graph.nodes}
    dependencies: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    incoming: dict[str, list[Edge]] = {node_id: [] for node_id in nodes}
    direct_feedback: dict[str, dict[str, set[str]]] = {}
    consumers: dict[str, int] = {node_id: 0 for node_id in nodes}
    groups: dict[tuple[int, int], list[str]] = {}
    for node_id, step in plan.steps.items():
        groups.setdefault((step.component, step.iteration), []).append(node_id)
    for edge in plan.graph.edges:
        dependencies[edge.dst_node].add(edge.src_node)
        incoming[edge.dst_node].append(edge)
        consumers[edge.src_node] += 1
        source, target = plan.steps[edge.src_node], plan.steps[edge.dst_node]
        if source.original_node_id == target.original_node_id and (
            source.iteration + 1 == target.iteration
        ):
            direct_feedback.setdefault(target.original_node_id, {}).setdefault(
                edge.dst_port, set()
            ).add(edge.edge_id)
    sorter = TopologicalSorter(dependencies)
    sorter.prepare()
    ready: list[tuple[int, int, str]] = []
    values: dict[str, dict[str, object]] = {}
    completed: dict[tuple[int, int], dict[str, dict[str, object]]] = {}
    original_inputs: dict[tuple[str, str], object] = {}
    while sorter.is_active():
        for node_id in sorter.get_ready():
            step = plan.steps[node_id]
            heappush(ready, (step.component, step.iteration, node_id))
        _, _, node_id = heappop(ready)
        definition = nodes[node_id]
        step = plan.steps[node_id]
        node_type = registry.resolve(definition.type_id)
        gathered: dict[str, list[object]] = {port.name: [] for port in node_type.spec.inputs}
        direct_values: dict[str, object] = {}
        for edge in incoming[node_id]:
            value = deepcopy(values[edge.src_node][edge.src_port])
            gathered[edge.dst_port].append(value)
            if edge.edge_id in direct_feedback.get(step.original_node_id, {}).get(
                edge.dst_port, set()
            ):
                direct_values[edge.dst_port] = value
            consumers[edge.src_node] -= 1
            if consumers[edge.src_node] == 0:
                del values[edge.src_node]
        inputs: dict[str, object] = {
            port.name: (gathered[port.name][0] if gathered[port.name] else None)
            if port.max_connections == 1
            else gathered[port.name]
            for port in node_type.spec.inputs
        }
        if step.iteration == 1:
            inputs.update(deepcopy(external_inputs.get(step.original_node_id, {})))
        try:
            node = node_type(node_id, definition.params)
            node.context = RunContext(step.original_node_id, step.iteration, max_iterations)
            mode = node_type.direct_loopback_mode(node.params)
            ports = direct_feedback.get(step.original_node_id, {})
            if mode == "add" and step.iteration == 1 and ports:
                for port in ports:
                    original_inputs[step.original_node_id, port] = deepcopy(inputs[port])
                if len(pickle.dumps(original_inputs, protocol=pickle.HIGHEST_PROTOCOL)) > (
                    MAX_CAPTURE_BYTES
                ):
                    raise ExecutionError("Direct loopback originals exceed the 16 MiB limit")
            if mode is not None and step.iteration > 1:
                for port, value in direct_values.items():
                    if mode == "add":
                        inputs[port] = node.combine_loopback(
                            port, deepcopy(original_inputs[step.original_node_id, port]), value
                        )
                        if step.iteration == max_iterations:
                            del original_inputs[step.original_node_id, port]
                    else:
                        spec = next(item for item in node_type.spec.inputs if item.name == port)
                        inputs[port] = value if spec.max_connections == 1 else [value]
            outputs = node.process(inputs)
        except Exception as error:
            raise ExecutionError(f"Node {node_id}: {type(error).__name__}: {error}") from error
        expected = {port.name for port in node_type.spec.outputs}
        if not isinstance(outputs, Mapping) or set(outputs) != expected:
            raise ExecutionError(
                f"Node {node_id} must return exactly output ports {sorted(expected)}"
            )
        outputs = deepcopy(dict(outputs))
        if consumers[node_id]:
            values[node_id] = outputs
        group_key = (step.component, step.iteration)
        group = completed.setdefault(group_key, {})
        group[step.original_node_id] = outputs
        if len(group) == len(groups[group_key]):
            snapshot = None
            if step.cyclic and step.iteration % capture_every == 0:
                snapshot = Snapshot(tuple(group), step.iteration, deepcopy(group))
            _send(connection, ("completed", (group, snapshot)))
            del completed[group_key]
        sorter.done(node_id)


class Executor:
    def run(
        self,
        graph: Graph,
        registry: NodeRegistry,
        *,
        feedback_edge_ids: frozenset[str] = frozenset(),
        inputs: Mapping[str, Mapping[str, object]] | None = None,
    ) -> RunResult:
        started = monotonic()
        graph.validate_connections(registry)
        graph.validate_feedback()
        supplied = {node_id: dict(ports) for node_id, ports in (inputs or {}).items()}
        nodes = {node.node_id: node for node in graph.nodes}
        connected = {(edge.dst_node, edge.dst_port) for edge in graph.edges}
        for node_id, values in supplied.items():
            if node_id not in nodes:
                raise ValueError(f"Unknown runtime input node: {node_id}")
            ports = {
                port.name: port for port in registry.resolve(nodes[node_id].type_id).spec.inputs
            }
            for name in values:
                port = ports.get(name)
                if port is None or port.max_connections != 1 or port.min_connections != 0:
                    raise ValueError(
                        f"Runtime input {node_id}.{name} requires an optional scalar port"
                    )
                if (node_id, name) in connected:
                    raise ValueError(
                        f"Runtime input {node_id}.{name} already has a graph connection"
                    )
        loop = graph.policy.loop
        budget = min(loop.timeout_seconds, MAX_RUN_SECONDS) if loop else MAX_RUN_SECONDS
        plan = plan_graph(graph, None, feedback_edge_ids)
        capture_groups = {
            (step.component, step.iteration)
            for step in plan.steps.values()
            if step.cyclic and step.iteration % (loop.capture_every if loop else 1) == 0
        }
        if len(capture_groups) > MAX_CAPTURES:
            raise ExecutionError("Run exceeds the 1000-snapshot limit")
        # Windows starts the interpreter before pickling; validate before allocating pipes.
        try:
            ForkingPickler.dumps((plan, registry, supplied))
        except (AttributeError, TypeError, pickle.PicklingError) as error:
            raise ExecutionError(
                "Worker startup failed; node classes must be importable module-level "
                f"definitions and data must support process transfer: {error}"
            ) from error
        context = multiprocessing.get_context("spawn")
        reader, writer = context.Pipe(duplex=False)
        worker = context.Process(
            target=_run_worker,
            args=(
                writer,
                plan,
                registry,
                loop.capture_every if loop else 1,
                loop.max_iterations if loop else 1,
                supplied,
            ),
        )
        result = RunResult()
        try:
            try:
                worker.start()
            except (AttributeError, TypeError, pickle.PicklingError) as error:
                raise ExecutionError(
                    "Worker startup failed; node classes must be importable module-level "
                    f"definitions and data must support process transfer: {error}"
                ) from error
            writer.close()
            while True:
                remaining = budget - (monotonic() - started)
                if remaining <= 0 or not reader.poll(remaining):
                    result.timed_out = True
                    return result
                try:
                    payload = reader.recv_bytes(MAX_CAPTURE_BYTES)
                except EOFError as error:
                    raise ExecutionError("Worker exited without a completion message") from error
                kind, data = pickle.loads(payload)
                if kind == "error":
                    raise ExecutionError(data)
                if kind == "done":
                    return result
                group, snapshot = data
                result.outputs.update(group)
                if snapshot is not None:
                    result.snapshots.append(snapshot)
                if len(result.snapshots) > MAX_CAPTURES:
                    raise ExecutionError("Run exceeds the 1000-snapshot limit")
                if len(pickle.dumps(result, protocol=pickle.HIGHEST_PROTOCOL)) > MAX_CAPTURE_BYTES:
                    raise ExecutionError("Run exceeds the 16 MiB retained result limit")
        finally:
            writer.close()
            reader.close()
            if worker.pid is not None:
                if worker.is_alive():
                    worker.terminate()
                worker.join(timeout=2)
                if worker.is_alive():
                    worker.kill()
                    worker.join()
                worker.close()
