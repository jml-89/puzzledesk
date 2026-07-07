"""Propagation-backtracking solver for double word squares.

Once the acceptance test collapsed 'quality' into feasibility on a filtered
list, min-conflicts became the wrong tool: on a small, hard list it wanders and
restarts. A complete search with strong pruning is the right engine here.

We fill rows top to bottom. Before placing row r, every partial column must stay
a live prefix of some column word. For each column we know exactly which letters
keep that prefix alive; intersecting those per-position constraints against the
row lexicon (via Lexicon.words_matching) yields the legal row words directly --
no scan-and-reject. Randomising the candidate order gives distinct grids per
seed, recovering the diversity we liked about sampling.
"""

from __future__ import annotations

import numpy as np

from .lexicon import Lexicon
from .square import DoubleSquare


class _PrefixIndex:
    """For each prefix of a column word, which letters may follow (26-bool)."""

    def __init__(self, lex: Lexicon) -> None:
        self.nxt: dict[str, np.ndarray] = {}
        for w in lex.words:
            for k in range(lex.n):
                m = self.nxt.get(w[:k])
                if m is None:
                    m = np.zeros(26, dtype=bool)
                    self.nxt[w[:k]] = m
                m[ord(w[k]) - 97] = True
        self._empty = np.zeros(26, dtype=bool)

    def allowed(self, prefix: str) -> np.ndarray:
        return self.nxt.get(prefix, self._empty)


def solve(
    sq: DoubleSquare, *, seed: int = 0, randomize: bool = True, distinct: bool = True
) -> np.ndarray | None:
    """Return a solved state (array of N row-word indices) or None if the grid
    admits no double word square from these lexicons (a real proof of UNSAT).

    With ``distinct`` (default), the 2N words must all differ: no across word
    reused, and no down word equal to another down word or to any across word.
    This forbids the symmetric-square basin (across == down down the diagonal),
    where the down constraints collapse onto the across constraints and the
    solver would otherwise get an easy, degenerate fill.
    """
    rng = np.random.default_rng(seed)
    n = sq.n
    pidx = _PrefixIndex(sq.cols)
    state = np.full(n, -1, dtype=np.int64)
    cols = [""] * n
    used_across: set[str] = set()

    def rec(r: int) -> np.ndarray | None:
        if r == n:
            if distinct:
                downs = [cols[j] for j in range(n)]
                if len(set(downs)) != n or used_across & set(downs):
                    return None  # repeated word: keep searching
            return state.copy()
        allowed = [pidx.allowed(cols[j]) for j in range(n)]
        cands = sq.rows.words_matching(allowed)  # rows legal at every column
        if randomize:
            rng.shuffle(cands)
        for idx in cands:
            w = sq.rows.words[idx]
            if distinct and w in used_across:
                continue  # no duplicate across word
            state[r] = idx
            for j in range(n):
                cols[j] += w[j]
            used_across.add(w)
            res = rec(r + 1)
            if res is not None:
                return res
            used_across.discard(w)
            for j in range(n):
                cols[j] = cols[j][:-1]
        state[r] = -1
        return None

    return rec(0)
