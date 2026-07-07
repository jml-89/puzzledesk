"""The mini-generator use-case: distinct double word squares above a quality bar.

Data flow (architecture.md "generate a mini"): load the curated list at length N,
filter to the bar, wrap in a DoubleSquare, and run the complete backtracker per
seed with ``distinct=True``; every solved grid is validated (>= bar and 2N
distinct) by construction, then shaped into a :class:`MiniResult`.

Everything impure is injected: the word list via a :class:`LexiconSource`, the
randomness via a :class:`RngFactory` (one fresh stream per seed, so results are
reproducible). The service itself is pure orchestration over the core.
"""

from __future__ import annotations

import numpy as np

from ..core.engines import backtrack
from ..core.rng import RngFactory
from ..core.square import DoubleSquare
from ..core.validate import Verdict, score_of, validate
from .ports import LexiconSource
from .results import MiniBatch, MiniResult, WordScore


class MiniService:
    """Generate distinct minis (double word squares) above a quality bar."""

    def __init__(
        self, lexicon: LexiconSource, rng_factory: RngFactory, *, list_name: str = "cw"
    ) -> None:
        self._lexicon = lexicon
        self._rng = rng_factory
        self._list_name = list_name

    def generate(self, n: int = 5, *, min_score: float = 70.0, count: int = 3) -> MiniBatch:
        """Up to ``count`` distinct minis of order ``n`` with every word scoring
        >= ``min_score``. Backtracking is complete, so a seed that returns None
        simply found no grid on its randomised path; we try more seeds up to a
        budget and stop at ``count`` grids (or when the budget is spent)."""
        lex = self._lexicon.load(self._list_name, n, min_score=min_score)
        sq = DoubleSquare(lex)
        results: list[MiniResult] = []
        for seed in range(count * 20):
            state = backtrack.solve(sq, rng=self._rng.create(seed), distinct=True)
            if state is None:
                continue
            v = validate(sq, state, min_score)
            assert v.ok, v  # filtered list + distinct=True guarantee this
            results.append(_to_result(sq, state, v))
            if len(results) >= count:
                break
        return MiniBatch(n=n, min_score=min_score, eligible=len(lex), results=results)


def _to_result(sq: DoubleSquare, state: np.ndarray, v: Verdict) -> MiniResult:
    across = [WordScore(sq.rows.words[i], float(sq.rows.scores[i])) for i in state]
    down = [WordScore(w, score_of(sq.cols, w)) for w in sq.column_strings(state)]
    return MiniResult(across=across, down=down, weakest=WordScore(v.weakest[0], v.weakest[1]))
