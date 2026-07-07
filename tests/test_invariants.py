"""The load-bearing invariants, as tests (docs/architecture.md 0-5).

* completeness: ``None`` is a UNSAT proof, not a timeout;
* distinctness: an output path emits 2N distinct words;
* energy: energy 0 <=> valid.
"""

from __future__ import annotations

import numpy as np

from puzzledesk.core.engines import backtrack
from puzzledesk.core.lexicon import Lexicon
from puzzledesk.core.square import DoubleSquare
from puzzledesk.core.validate import validate


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def test_none_is_a_real_unsat_proof() -> None:
    # {ab, ba} has valid squares (ab/ba and ba/ab) but BOTH are the symmetric
    # basin: across == down. So a distinct square is genuinely impossible, and a
    # complete solver must return None -- a proof, exhausted over every seed.
    sq = DoubleSquare(Lexicon(["ab", "ba"]))
    for seed in range(25):
        assert backtrack.solve(sq, rng=_rng(seed), distinct=True) is None
    # ...while distinctness OFF, the same list solves (the basin is allowed).
    assert backtrack.solve(sq, rng=_rng(0), distinct=False) is not None


def test_distinct_square_has_2n_distinct_words() -> None:
    # ab/cd across induce ac/bd down -- four distinct words: a genuine double square.
    sq = DoubleSquare(Lexicon(["ab", "cd", "ac", "bd"]))
    state = backtrack.solve(sq, rng=_rng(0), distinct=True)
    assert state is not None
    v = validate(sq, state, threshold=0.0)
    assert v.ok
    assert v.distinct and v.n_distinct == 2 * sq.n


def test_energy_zero_iff_valid() -> None:
    sq = DoubleSquare(Lexicon(["ab", "cd", "ac", "bd"]))
    state = backtrack.solve(sq, rng=_rng(0), distinct=True)
    assert state is not None
    assert sq.energy(state) == 0
