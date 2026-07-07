"""Small-first ground truth: the solvers' output is a subset of brute-force
enumeration. These are the contracts that used to be asserted ad hoc inside
scripts/demo.py and scripts/blackcells.py, promoted to real tests and driven with
injected randomness on in-memory lexicons (no files, no global RNG).
"""

from __future__ import annotations

import numpy as np

from puzzledesk.core.engines import backtrack, fill
from puzzledesk.core.engines.bruteforce import enumerate_squares
from puzzledesk.core.engines.sampler import solve as sample_solve
from puzzledesk.core.lexicon import Lexicon, MultiLexicon
from puzzledesk.core.square import DoubleSquare

# A tiny 2-letter list where NOT every grid is valid (no "bb"), so the column
# check actually has to bite -- the solver must never emit a square outside truth.
_TINY = ["aa", "ab", "ba"]


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def test_backtrack_output_is_a_valid_square_in_ground_truth() -> None:
    sq = DoubleSquare(Lexicon(_TINY))
    truth = set(enumerate_squares(sq.rows))
    assert truth, "expected the tiny list to admit some squares"
    solved = 0
    for seed in range(20):
        state = backtrack.solve(sq, rng=_rng(seed), distinct=False)
        if state is None:
            continue
        solved += 1
        rows = tuple(sq.rows.words[i] for i in state)
        assert rows in truth
        assert sq.energy(state) == 0
    assert solved > 0


def test_sampler_output_is_a_valid_square_in_ground_truth() -> None:
    sq = DoubleSquare(Lexicon(_TINY))
    truth = set(enumerate_squares(sq.rows))
    for seed in range(20):
        r = sample_solve(sq, rng=_rng(seed), max_steps=200, max_restarts=50)
        if not r.solved:
            continue
        rows = tuple("".join(chr(int(c) + 97) for c in sq.rows.letters[i]) for i in r.state)
        assert rows in truth
        assert sq.energy(r.state) == 0


def test_blocked_fill_is_a_subset_of_enumeration() -> None:
    # A 2x2 fully-open grid (four length-2 slots) with a list that admits a
    # genuinely distinct fill: ab/cd across, ac/bd down -- all four distinct.
    from puzzledesk.core.blocked import BlockedGrid

    g = BlockedGrid.parse(["..", ".."], min_len=2)
    mlex = MultiLexicon({2: Lexicon(["ab", "cd", "ac", "bd"])})
    truth = {tuple(sorted(a.items())) for a in fill.enumerate_fills(g, mlex)}
    assert truth, "expected at least one distinct fill"
    for seed in range(30):
        a = fill.solve(g, mlex, rng=_rng(seed), distinct=True)
        if a is None:
            continue
        assert tuple(sorted(a.items())) in truth
