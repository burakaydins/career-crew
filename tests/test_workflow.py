import threading
import time
from types import SimpleNamespace

from app.events import EventBus
from app.workflow import CodeStep, Loop, Parallel, Sequential, Step, UserGate


class Ctx:
    def __init__(self, answers=()):
        self.state = SimpleNamespace(iteration=0, feedback={}, n=0)
        self.bus = EventBus()
        self.events = []
        self.bus.subscribe(lambda e: self.events.append(e.type))
        self.calls = []
        self.answers = list(answers)

    def run_agent(self, agent, skill):
        self.calls.append((agent, skill, threading.current_thread().name))

    def ask(self, gate, state):
        return self.answers.pop(0) if self.answers else None


def test_sequential_order():
    ctx = Ctx()
    Sequential(Step("a", "x"), Step("b", "y")).run(ctx)
    assert [c[:2] for c in ctx.calls] == [("a", "x"), ("b", "y")]


def test_parallel_runs_concurrently():
    ctx = Ctx()
    started = []

    def slow(c):
        started.append(time.monotonic())
        time.sleep(0.2)

    t0 = time.monotonic()
    Parallel(CodeStep("a", slow), CodeStep("b", slow)).run(ctx)
    assert time.monotonic() - t0 < 0.35


def test_loop_stops_when_condition_met():
    ctx = Ctx()
    inc = CodeStep("inc", lambda c: setattr(c.state, "n", c.state.n + 1))
    Loop(inc, until=lambda s: s.n >= 2, max_iterations=3).run(ctx)
    assert ctx.state.n == 2 and ctx.state.iteration == 2
    assert ctx.events[-1] == "loop_done"


def test_loop_respects_max_iterations():
    ctx = Ctx()
    inc = CodeStep("inc", lambda c: setattr(c.state, "n", c.state.n + 1))
    Loop(inc, until=lambda s: False, max_iterations=3).run(ctx)
    assert ctx.state.n == 3


def test_user_gate_retries_with_correction():
    ctx = Ctx(answers=["Seviye senior olmalı", None])
    UserGate("confirm_job", retry=Step("job_analyst", "analyze_job")).run(ctx)
    assert ctx.state.feedback["confirm_job"] == "Seviye senior olmalı"
    assert len(ctx.calls) == 1
    assert ctx.events.count("input_required") == 2


def test_loop_gives_up_early():
    ctx = Ctx()
    inc = CodeStep("inc", lambda c: setattr(c.state, "n", c.state.n + 1))
    Loop(inc, until=lambda s: False, give_up=lambda s: s.n >= 2, max_iterations=3).run(ctx)
    assert ctx.state.n == 2
    done = [e for e in ctx.events if e == "loop_done"]
    assert len(done) == 1
