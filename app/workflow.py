"""Workflow building blocks: Sequential, Parallel, Loop, Step, CodeStep, UserGate.

Nodes are domain-agnostic. They talk to a context object that provides:
    ctx.state                  shared run state
    ctx.bus                    EventBus
    ctx.run_agent(agent, skill)
    ctx.ask(gate, state) -> str | None   None means approved, a string is the user's correction
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Protocol


class Node(Protocol):
    def run(self, ctx: Any) -> None: ...


class Step:
    def __init__(self, agent: str, skill: str) -> None:
        self.agent, self.skill = agent, skill

    def run(self, ctx: Any) -> None:
        ctx.run_agent(self.agent, self.skill)


class CodeStep:
    """Runs plain Python (checks, reports). No LLM involved."""

    def __init__(self, name: str, fn: Callable[[Any], None]) -> None:
        self.name, self.fn = name, fn

    def run(self, ctx: Any) -> None:
        self.fn(ctx)


class Sequential:
    def __init__(self, *nodes: Node) -> None:
        self.nodes = nodes

    def run(self, ctx: Any) -> None:
        for node in self.nodes:
            node.run(ctx)


class Parallel:
    def __init__(self, *nodes: Node) -> None:
        self.nodes = nodes

    def run(self, ctx: Any) -> None:
        with ThreadPoolExecutor(max_workers=len(self.nodes)) as pool:
            futures = [pool.submit(node.run, ctx) for node in self.nodes]
            for f in futures:
                f.result()  # re-raise the first failure


class Loop:
    def __init__(
        self,
        *nodes: Node,
        until: Callable[[Any], bool],
        max_iterations: int = 3,
        give_up: Callable[[Any], bool] | None = None,
    ) -> None:
        """`until`: goal reached, stop. `give_up`: more rounds will not help, stop early."""
        self.body = Sequential(*nodes)
        self.until = until
        self.give_up = give_up
        self.max_iterations = max_iterations

    def run(self, ctx: Any) -> None:
        for i in range(1, self.max_iterations + 1):
            ctx.state.iteration = i
            ctx.bus.publish("loop_iteration", iteration=i, max=self.max_iterations)
            self.body.run(ctx)
            if self.until(ctx.state):
                ctx.bus.publish("loop_done", iteration=i, converged=True, stopped_early=False)
                return
            if self.give_up and i < self.max_iterations and self.give_up(ctx.state):
                ctx.bus.publish("loop_done", iteration=i, converged=False, stopped_early=True)
                return
        ctx.bus.publish("loop_done", iteration=self.max_iterations, converged=False, stopped_early=False)


class UserGate:
    """Pauses for the user (A2A input-required). On a correction, reruns `retry`."""

    def __init__(self, name: str, retry: Node | None = None, max_retries: int = 2) -> None:
        self.name, self.retry, self.max_retries = name, retry, max_retries

    def run(self, ctx: Any) -> None:
        for attempt in range(self.max_retries + 1):
            ctx.bus.publish("input_required", gate=self.name)
            correction = ctx.ask(self.name, ctx.state)
            if correction is None:
                ctx.bus.publish("gate_passed", gate=self.name)
                return
            ctx.state.feedback[self.name] = correction
            if self.retry is None or attempt == self.max_retries:
                break
            self.retry.run(ctx)
        ctx.bus.publish("gate_passed", gate=self.name, forced=True)
