"""The clue interface, exercised end-to-end with no LLM and no network.

Proves the port is sufficient and the DI holds: a FilledGrid is projected from
each core grid model, ``runs()`` derives the entry-targets, and a FakeClueProvider
clues them (and a puzzle-level meta target) behind the ClueProvider port.
"""

from __future__ import annotations

import numpy as np
from fakes import FakeClueProvider

from puzzledesk.app.clue import ClueProvider, ClueStyle, Difficulty
from puzzledesk.app.puzzle import (
    FilledGrid,
    Target,
    filled_from_blocked,
    filled_from_square,
)
from puzzledesk.core.blocked import BlockedGrid
from puzzledesk.core.engines import backtrack, fill
from puzzledesk.core.lexicon import Lexicon, MultiLexicon
from puzzledesk.core.square import DoubleSquare


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


# ab/cd across induce ac/bd down -- a genuine distinct 2x2 double square.
_SQUARE_LEX = Lexicon(["ab", "cd", "ac", "bd"])


def _square_grid() -> FilledGrid:
    sq = DoubleSquare(_SQUARE_LEX)
    state = backtrack.solve(sq, rng=_rng(0), distinct=True)
    assert state is not None
    return filled_from_square(sq, state)


def test_runs_split_on_black_and_skip_singletons() -> None:
    # a b c
    # d e #   -> col2 is a length-1 run (dropped); row1 stops before the black.
    grid = FilledGrid((("a", "b", "c"), ("d", "e", None)))
    by_kind = {(t.kind, t.answer) for t in grid.runs()}
    assert by_kind == {("A", "abc"), ("A", "de"), ("D", "ad"), ("D", "be")}


def test_rebus_cell_reads_through() -> None:
    # a single cell holding a rebus string is read straight through.
    grid = FilledGrid((("he", "art"),))
    (t,) = [t for t in grid.runs() if t.kind == "A"]
    assert t.answer == "heart"


def test_crossings_are_the_shared_cells() -> None:
    grid = _square_grid()  # fully checked 2x2 -> every cell is a crossing
    cells = {x.cell for x in grid.crossings()}
    assert cells == {(0, 0), (0, 1), (1, 0), (1, 1)}


def test_project_square_recovers_the_words() -> None:
    grid = _square_grid()
    assert {t.answer for t in grid.runs()} == {"ab", "cd", "ac", "bd"}


def test_project_blocked_marks_black_and_recovers_the_words() -> None:
    g = BlockedGrid.parse(["...", "..#"], min_len=2)
    mlex = MultiLexicon({3: Lexicon(["abc"]), 2: Lexicon(["de", "ad", "be"])})
    assign = fill.solve(g, mlex, rng=_rng(0), distinct=True)
    assert assign is not None
    grid = filled_from_blocked(g, assign)
    assert grid.cells[1][2] is None  # the black square
    assert {t.answer for t in grid.runs()} == {"abc", "de", "ad", "be"}


def test_fake_provider_satisfies_the_port() -> None:
    assert isinstance(FakeClueProvider(), ClueProvider)


def test_provider_clues_every_target() -> None:
    provider: ClueProvider = FakeClueProvider()
    grid = _square_grid()
    targets = grid.runs()
    clues = provider.clue(grid, targets, style=ClueStyle(difficulty=Difficulty.SATURDAY), n=2)

    assert set(clues) == {t.id for t in targets}
    for t in targets:
        assert len(clues[t.id]) == 2  # n candidates
        assert t.answer in clues[t.id][0].text  # the right clue for the right target
        assert "SATURDAY" in clues[t.id][0].text  # the style knob reached the provider


def test_meta_target_is_just_another_target() -> None:
    # The seam for puzzle-level metas: a target over scattered cells needs no
    # interface change -- the provider clues it like any entry.
    provider: ClueProvider = FakeClueProvider()
    grid = _square_grid()
    diag = ((0, 0), (1, 1))
    meta = Target(diag, "".join(grid.cells[r][c] or "" for r, c in diag), "meta")

    clues = provider.clue(grid, [*grid.runs(), meta], style=ClueStyle())
    assert meta.id in clues
    assert "meta" in clues[meta.id][0].text
