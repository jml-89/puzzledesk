"""The solve harness, driven with the deterministic ``FakeSolverAgent`` -- no model.

Covers the happy path (an oracle solver completes and the reasoning is captured), the
honest budget epistemics (a stuck solver exhausts the turn budget -- reported as
``exhausted``, never as a proof), malformed-move rejection, and give-up.
"""

from __future__ import annotations

from fakes import FakeSolverAgent

from puzzledesk.app.clue import Clue
from puzzledesk.app.cluing import CluedPuzzle
from puzzledesk.app.puzzle import FilledGrid
from puzzledesk.app.solve import FeedbackPolicy
from puzzledesk.app.solve_service import SolveService
from puzzledesk.app.solver import Placement, SolverMove


def _clued2x2() -> CluedPuzzle:
    grid = FilledGrid((("a", "b"), ("c", "d")))
    texts = {"ab": "one-two", "cd": "three-four", "ac": "one-three", "bd": "two-four"}
    clues = {t.id: Clue(texts[t.answer]) for t in grid.runs()}
    return CluedPuzzle(grid=grid, clues=clues, unclued=())


def test_oracle_solver_completes_and_reasoning_is_captured() -> None:
    puzzle = _clued2x2()
    agent = FakeSolverAgent(oracle=puzzle, per_turn=1, reasoning="crossing check")
    report = SolveService(agent, max_turns=12).solve(puzzle)
    assert report.solved
    assert not report.exhausted
    assert 1 <= report.n_turns <= 4  # one entry per turn, four entries
    assert all(t.reasoning == "crossing check" for t in report.turns)


def test_budget_exhaustion_is_not_a_proof() -> None:
    puzzle = _clued2x2()
    # a solver that keeps guessing the same wrong word never solves
    stuck = FakeSolverAgent(script=[SolverMove((Placement(1, "A", "zz"),))])
    report = SolveService(stuck, max_turns=3).solve(puzzle, policy=FeedbackPolicy.WORD)
    assert not report.solved
    assert report.exhausted
    assert not report.gave_up
    assert report.n_turns == 3
    assert report.wrong_guesses >= 1  # 1A stood wrong each turn


def test_malformed_placements_are_rejected_not_stored() -> None:
    puzzle = _clued2x2()
    bad = FakeSolverAgent(
        script=[SolverMove((Placement(9, "A", "ab"), Placement(1, "A", "toolong")))]
    )
    report = SolveService(bad, max_turns=1).solve(puzzle)
    turn = report.turns[0]
    assert turn.applied == ()
    assert {(p.number, p.direction) for p in turn.rejected} == {(9, "A"), (1, "A")}


def test_report_totals_reasoning_tokens() -> None:
    puzzle = _clued2x2()
    # spread the fill over three turns so all three token counts are summed (placing both
    # acrosses would solve it via the derived downs and end the loop early)
    script = [
        SolverMove((Placement(1, "A", "ab"),), reasoning_tokens=100),
        SolverMove((Placement(1, "D", "ac"),), reasoning_tokens=250),
        SolverMove((Placement(3, "A", "cd"),), reasoning_tokens=40),
    ]
    report = SolveService(FakeSolverAgent(script=script), max_turns=5).solve(puzzle)
    assert report.solved
    assert report.n_turns == 3
    assert report.total_reasoning_tokens == 390  # summed across turns


def test_total_reasoning_tokens_is_none_when_unreported() -> None:
    # the oracle fake does not report token counts -> None, not 0
    puzzle = _clued2x2()
    report = SolveService(FakeSolverAgent(oracle=puzzle), max_turns=8).solve(puzzle)
    assert report.total_reasoning_tokens is None


def test_give_up_ends_the_loop_early() -> None:
    puzzle = _clued2x2()
    quitter = FakeSolverAgent(script=[SolverMove(reasoning="stuck", give_up=True)])
    report = SolveService(quitter, max_turns=10).solve(puzzle)
    assert report.gave_up
    assert not report.solved
    assert report.n_turns == 1
