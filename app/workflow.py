"""Workflow building blocks: Sequential, Parallel, Loop, Step, CodeStep, UserGate.

Nodes are domain-agnostic. They talk to a context object that provides:
    ctx.state                  shared run state
    ctx.bus                    EventBus
    ctx.run_agent(agent, skill)
    ctx.ask(gate, state) -> str | None   None means approved, a string is the user's correction

A context may also offer checkpoints (is_done, mark, forget). A node that already finished in an
earlier attempt is skipped, which is how a paused run continues where it stopped.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Protocol


class Node(Protocol):
    def run(self, ctx: Any) -> None: ...


def scope(ctx: Any) -> int:
    """Loop round the node runs in (0 outside loops). Separate from state.iteration, which a
    resumed run restores to the last round."""
    return getattr(ctx, "scope", 0)


def is_done(ctx: Any, key: str) -> bool:
    return bool(getattr(ctx, "is_done", None) and ctx.is_done(key))


def mark(ctx: Any, key: str) -> None:
    if getattr(ctx, "mark", None):
        ctx.mark(key)


def forget(ctx: Any, key: str) -> None:
    if getattr(ctx, "forget", None):
        ctx.forget(key)


class Step:
    def __init__(self, agent: str, skill: str) -> None:
        self.agent, self.skill = agent, skill

    def key(self, ctx: Any) -> str:
        return f"{scope(ctx)}:{self.agent}.{self.skill}"

    def run(self, ctx: Any) -> None:
        key = self.key(ctx)
        if is_done(ctx, key):
            return
        ctx.run_agent(self.agent, self.skill)
        mark(ctx, key)


class CodeStep:
    """Runs plain Python (checks, reports). No LLM involved."""

    def __init__(self, name: str, fn: Callable[[Any], None]) -> None:
        self.name, self.fn = name, fn

    def run(self, ctx: Any) -> None:
        key = f"{scope(ctx)}:{self.name}"
        if is_done(ctx, key):
            return
        self.fn(ctx)
        mark(ctx, key)


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
        if is_done(ctx, "loop.end"):
            return
        try:
            self._rounds(ctx)
        finally:
            ctx.scope = 0

    def _rounds(self, ctx: Any) -> None:
        for i in range(1, self.max_iterations + 1):
            if is_done(ctx, f"loop.round{i}"):
                continue  # finished in an earlier attempt and the loop went on
            ctx.state.iteration = ctx.scope = i
            ctx.bus.publish("loop_iteration", iteration=i, max=self.max_iterations)
            self.body.run(ctx)
            if self.until(ctx.state):
                ctx.bus.publish("loop_done", iteration=i, converged=True, stopped_early=False)
                mark(ctx, "loop.end")
                return
            if self.give_up and i < self.max_iterations and self.give_up(ctx.state):
                ctx.bus.publish("loop_done", iteration=i, converged=False, stopped_early=True)
                mark(ctx, "loop.end")
                return
            mark(ctx, f"loop.round{i}")
        ctx.bus.publish("loop_done", iteration=self.max_iterations, converged=False, stopped_early=False)
        mark(ctx, "loop.end")


class UserGate:
    """Pauses for the user (A2A input-required). On a correction, reruns `retry`."""

    def __init__(self, name: str, retry: Node | None = None, max_retries: int = 2) -> None:
        self.name, self.retry, self.max_retries = name, retry, max_retries

    def run(self, ctx: Any) -> None:
        key = f"{scope(ctx)}:gate.{self.name}"
        if is_done(ctx, key):
            return
        for attempt in range(self.max_retries + 1):
            ctx.bus.publish("input_required", gate=self.name)
            correction = ctx.ask(self.name, ctx.state)
            if correction is None:
                ctx.bus.publish("gate_passed", gate=self.name)
                mark(ctx, key)
                return
            ctx.state.feedback[self.name] = correction
            if self.retry is None or attempt == self.max_retries:
                break
            if isinstance(self.retry, Step):
                forget(ctx, self.retry.key(ctx))  # a deliberate rerun, not a replay
            self.retry.run(ctx)
        ctx.bus.publish("gate_passed", gate=self.name, forced=True)
        mark(ctx, key)
