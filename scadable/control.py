"""Control primitives: PID controller and StateMachine."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class PID:
    """Declarative PID controller.

    Compiles to 3 float operations per cycle. The runtime handles
    the computation — this class just holds the parameters.
    """

    def __init__(
        self,
        *,
        input: Any,
        output: Any,
        setpoint: float,
        kp: float = 1.0,
        ki: float = 0.0,
        kd: float = 0.0,
        output_min: float = 0,
        output_max: float = 100,
    ):
        self.input = input
        self.output = output
        self.setpoint = setpoint
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.output_min = output_min
        self.output_max = output_max


class State:
    """A state in a StateMachine."""

    def __init__(
        self,
        name: str,
        *,
        on_enter: Callable | None = None,
        timeout: int | None = None,
        next: str | None = None,
    ):
        self.name = name
        self.on_enter = on_enter
        self.timeout = timeout
        self.next = next


class StateMachine:
    """Declarative state machine with typed transitions."""

    def __init__(self, initial: str = ""):
        self.initial = initial
        self.current = initial
        self.states: list[State] = []
        self.transitions: list[dict] = []

    def add_states(self, states: list[State]) -> None:
        self.states.extend(states)

    def add_transitions(self, transitions: list[dict]) -> None:
        self.transitions.extend(transitions)

    def transition(self, to_state: str) -> None:
        self.current = to_state
