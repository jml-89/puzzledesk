"""The solver-agent port: turn a solve view into a move, with its reasoning.

The soft, generative counterpart to :class:`~puzzledesk.app.clue.ClueProvider`. Where
cluing is the one soft stage in *generation*, this is the one soft stage in *solving*:
nothing here proves anything, so it is fenced behind a port and kept out of ``core``
(and out of the deterministic session) entirely. The real implementation is a Claude
adapter (``adapters/claude_solver.py``); tests drive a deterministic fake.

The port is deliberately **one-shot and stateless**: ``act`` maps a
:class:`~puzzledesk.app.solve.SolveView` to a :class:`SolverMove`. The view already
carries the full observable state (geometry, clues, current letters, last feedback),
so the agent is a *function of observable state* -- the harness re-derives and re-sends
the whole view each turn rather than the agent hoarding a private history. An adapter
may still be internally conversational, but the contract is view -> move.

The move carries the agent's **reasoning** because inspecting how the solver thought
its way through is a first-class output of this spike (D24): it is the difficulty
signal that ``difficulty.solve_order`` can only *model*. For the Claude adapter the
reasoning is the captured extended-thinking trace; the fake leaves it empty or canned.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .solve import EntryRef, SolveView


@dataclass(frozen=True, slots=True)
class Placement:
    """One proposed fill: write ``word`` into entry ``(number, direction)``. An empty
    ``word`` clears the entry (erasing is part of solving). The harness validates the
    ref and length before it reaches the session."""

    number: int
    direction: str  # "A" | "D"
    word: str

    @property
    def ref(self) -> EntryRef:
        return (self.number, self.direction)


@dataclass(frozen=True, slots=True)
class SolverMove:
    """One turn's output: the placements to apply, the reasoning behind them, the
    *amount* of reasoning the agent spent (``reasoning_tokens`` -- the difficulty tell,
    D24; ``None`` when the agent cannot report it, e.g. the fake), and an optional
    ``give_up`` when the agent judges itself stuck (the harness still decides when the
    loop ends -- a give-up is a signal, not a proof of unsolvability)."""

    placements: tuple[Placement, ...] = ()
    reasoning: str = ""
    reasoning_tokens: int | None = None
    give_up: bool = False


@runtime_checkable
class SolverAgent(Protocol):
    """Propose the next move given the current answer-free view. Total: it always
    returns a :class:`SolverMove` (an empty one is allowed), never raises."""

    def act(self, view: SolveView) -> SolverMove: ...
