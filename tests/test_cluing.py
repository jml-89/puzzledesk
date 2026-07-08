"""The ClueService: pure orchestration, exercised with the fake provider.

No model, no network -- the DI payoff again. Covers the happy path (every entry
clued), the hard-constraint reject path (a provider that leaks the answer leaves
targets unclued), and that a meta target flows through unchanged.
"""

from __future__ import annotations

import numpy as np
from fakes import FakeClueProvider

from puzzledesk.app.clue import ClueStyle, Difficulty
from puzzledesk.app.cluing import ClueService
from puzzledesk.app.puzzle import FilledGrid, Target, filled_from_square
from puzzledesk.bootstrap import build
from puzzledesk.core.engines import backtrack
from puzzledesk.core.lexicon import Lexicon
from puzzledesk.core.square import DoubleSquare


def _grid() -> FilledGrid:
    sq = DoubleSquare(Lexicon(["ab", "cd", "ac", "bd"]))
    state = backtrack.solve(sq, rng=np.random.default_rng(0), distinct=True)
    assert state is not None
    return filled_from_square(sq, state)


def test_clues_every_entry_on_the_happy_path() -> None:
    grid = _grid()
    service = ClueService(FakeClueProvider())
    result = service.clue(grid, style=ClueStyle(difficulty=Difficulty.MONDAY))

    entries = grid.runs()
    assert set(result.clues) == {t.id for t in entries}
    assert result.unclued == ()
    # a chosen clue never contains its own answer (the hard constraint held)
    for t in entries:
        assert t.answer not in result.clues[t.id].text.lower()


def test_answer_leaking_clues_are_rejected() -> None:
    grid = _grid()
    service = ClueService(FakeClueProvider(leak_answer=True))
    result = service.clue(grid, style=ClueStyle())

    # every candidate embeds the answer -> every target is reported unclued
    assert result.clues == {}
    assert set(result.unclued) == {t.id for t in grid.runs()}


def test_explicit_targets_including_a_meta() -> None:
    grid = _grid()
    diag = ((0, 0), (1, 1))
    meta = Target(diag, "".join(grid.cells[r][c] or "" for r, c in diag), "meta")
    service = ClueService(FakeClueProvider())

    result = service.clue(grid, style=ClueStyle(), targets=[*grid.runs(), meta])
    assert meta.id in result.clues  # the meta was clued like any entry


def test_container_wires_a_clue_service() -> None:
    # build() constructs the whole graph including the Claude adapter without the
    # `anthropic` extra installed (the SDK import is lazy) -- only a clue call needs it.
    container = build()
    assert isinstance(container.clue, ClueService)
