"""The solve harness: drive a :class:`~puzzledesk.app.solver.SolverAgent` around the
deterministic session until the puzzle is solved or the turn budget is spent.

Pure orchestration over the port and the session (the shape of ``ClueService`` and
``PuzzleService``): build the answer-free view, ask the agent for a move, validate and
apply it, check under the policy, record the turn, repeat. It owns no I/O and no agent
of its own -- the agent is injected, the puzzle is passed in.

The one epistemic rule it must hold (D23's lesson, restated on the solving side): a
solver that exhausts ``max_turns`` has **not** proven anything. The fill engines'
``None`` is a UNSAT theorem; this budget miss is just "not solved in N turns". So the
report says ``solved``/``exhausted`` honestly and never dresses a budget miss as a
proof of unsolvability. ``SolveReport`` is the difficulty artifact: whether it
completed, how long it took, how much it flailed, and -- the point of the spike -- the
per-turn reasoning transcript to inspect.
"""

from __future__ import annotations

from dataclasses import dataclass

from .cluing import CluedPuzzle
from .solve import Board, Feedback, FeedbackPolicy, SolveState
from .solver import Placement, SolverAgent


@dataclass(frozen=True, slots=True)
class SolveTurn:
    """One turn of the loop: what the agent thought, what it played (and what was
    rejected as malformed), and the feedback the policy gave back."""

    index: int
    reasoning: str
    applied: tuple[Placement, ...]
    rejected: tuple[Placement, ...]
    feedback: Feedback
    reasoning_tokens: int | None = None
    gave_up: bool = False


@dataclass(frozen=True, slots=True)
class SolveReport:
    """The record of one solve attempt -- the difficulty artifact (D26).

    ``solved`` is the truth (the agent actually completed the grid). ``exhausted`` means
    the budget ran out first -- **not** a proof the puzzle is unsolvable, only that this
    agent did not get there in ``max_turns``. ``gave_up`` means the agent stopped itself.
    """

    puzzle: CluedPuzzle
    policy: FeedbackPolicy
    max_turns: int
    turns: tuple[SolveTurn, ...]
    final: SolveState

    @property
    def solved(self) -> bool:
        return self.final.is_solved()

    @property
    def n_turns(self) -> int:
        return len(self.turns)

    @property
    def gave_up(self) -> bool:
        return bool(self.turns) and self.turns[-1].gave_up

    @property
    def exhausted(self) -> bool:
        """Budget spent without solving and without giving up -- the honest 'ran out of
        turns', never an 'impossible'."""
        return not self.solved and not self.gave_up and self.n_turns >= self.max_turns

    @property
    def wrong_guesses(self) -> int:
        """How many entry-guesses the solver got wrong across the whole attempt (a flail
        proxy). Counts a wrong entry each turn it stands wrong, so churn shows up."""
        total = 0
        for t in self.turns:
            fb = t.feedback
            total += len(fb.wrong_entries)
        return total

    @property
    def total_reasoning_tokens(self) -> int | None:
        """Reasoning spent across the whole attempt -- **the difficulty tell** (D26): for
        a model that solves everything, *how much it had to think* is the graded signal,
        not whether it finished. ``None`` if no turn reported a count (e.g. the fake)."""
        counts = [t.reasoning_tokens for t in self.turns if t.reasoning_tokens is not None]
        return sum(counts) if counts else None


class SolveService:
    """Run a solver agent against a clued puzzle and report how it went."""

    def __init__(
        self,
        agent: SolverAgent,
        *,
        policy: FeedbackPolicy = FeedbackPolicy.CELL,
        max_turns: int = 12,
    ) -> None:
        self._agent = agent
        self._policy = policy
        self._max_turns = max_turns

    def solve(
        self,
        puzzle: CluedPuzzle,
        *,
        policy: FeedbackPolicy | None = None,
        max_turns: int | None = None,
    ) -> SolveReport:
        """Drive the agent around the session until solved, given up, or out of turns."""
        pol = policy if policy is not None else self._policy
        mt = max_turns if max_turns is not None else self._max_turns
        board = Board.of(puzzle)
        state = SolveState.initial(board)
        turns: list[SolveTurn] = []

        for i in range(mt):
            move = self._agent.act(state.view(pol))
            applied, rejected, state = _apply(state, board, move.placements)
            fb = state.feedback(pol)
            turns.append(
                SolveTurn(
                    index=i,
                    reasoning=move.reasoning,
                    applied=applied,
                    rejected=rejected,
                    feedback=fb,
                    reasoning_tokens=move.reasoning_tokens,
                    gave_up=move.give_up,
                )
            )
            if fb.solved or move.give_up:
                break

        return SolveReport(puzzle=puzzle, policy=pol, max_turns=mt, turns=tuple(turns), final=state)


def _apply(
    state: SolveState, board: Board, placements: tuple[Placement, ...]
) -> tuple[tuple[Placement, ...], tuple[Placement, ...], SolveState]:
    """Apply the well-formed placements, collect the malformed ones. A placement is
    rejected (not stored) when its ref names no entry, or a non-empty word does not
    match that entry's length -- so the session only ever holds coherent guesses."""
    applied: list[Placement] = []
    rejected: list[Placement] = []
    for p in placements:
        length = board.length_of(p.ref)
        if length is None or (p.word != "" and len(p.word) != length):
            rejected.append(p)
            continue
        state = state.with_guess(p.ref, p.word)
        applied.append(p)
    return tuple(applied), tuple(rejected), state
