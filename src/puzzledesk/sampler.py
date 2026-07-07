"""Stochastic sampler for double word squares.

State = N row-word indices. Each step re-chooses one row's word to minimise the
number of invalid columns. The move is computed from the per-column "allowed
letters" marginal: for the chosen row i and each column j, which letters at
position i keep column j a valid word (given the other rows fixed). A candidate
row-word's score is how many columns it satisfies. We pick greedily at
temperature T=0, or sample proportional to exp(score / T) otherwise -- annealed
Gibbs over the row variable. Random restarts escape dead configurations.

**Distinctness.** A genuine double word square has all 2N words distinct; the
degenerate case is a grid symmetric down the diagonal (across == down), a fixed
point of pure min-conflicts. With ``distinct=True`` the objective gains a
duplicate-pair penalty (``_distinct_penalty``) so the descent is *pulled off*
the symmetric basin toward genuine squares, and acceptance requires all 2N words
distinct. The penalty is weighted below one valid column, so feasibility always
dominates. A ``guided=False`` variant instead restarts whenever it lands on a
valid-but-degenerate grid -- the naive "gate" baseline that scripts/samplers.py
compares against (guided descent wins; see docs/notes.md).

This is deliberately plain NumPy: correct and easy to reason about at small N.
The hot loop (the per-candidate scoring) is the part that later vectorises onto
JAX for parallel-chain exploration at N=5.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .lexicon import decode
from .square import DoubleSquare


@dataclass
class Result:
    state: np.ndarray
    energy: int
    solved: bool
    steps: int
    restarts: int


# Feasibility must dominate quality AND distinctness: BIG exceeds any achievable
# quality delta or distinctness penalty so a move never trades a valid column
# away for a more common word or a more distinct fill.
BIG = 1000.0
# Weight on the duplicate-pair penalty. There are at most C(2N,2)=45 pairs at
# N=5, so DUP_WEIGHT*45 < BIG keeps one extra valid column worth more than any
# distinctness gain -- feasibility strictly first, distinctness second.
DUP_WEIGHT = 10.0


def _word_ids(sq: DoubleSquare) -> dict[str, int]:
    """String -> small-int id over the shared across/down vocabulary. Identical
    strings (whether they surface as an across or a down word) share an id, so id
    equality is exactly string equality -- the basis for counting duplicates."""
    vocab: dict[str, int] = {}
    for w in sq.rows.words:
        vocab.setdefault(w, len(vocab))
    for w in sq.cols.words:
        vocab.setdefault(w, len(vocab))
    return vocab


def _distinct_penalty(
    sq: DoubleSquare, state: np.ndarray, i: int, cand_across_id: np.ndarray, vocab: dict[str, int]
) -> np.ndarray:
    """For every candidate word at row ``i`` (other rows fixed), the number of
    duplicate word-pairs among the resulting 2N words (0 == all distinct).

    Vectorised: every word gets an integer id (``vocab`` for real words, a fresh
    per-step id for the throwaway non-word strings a bad column can spell), so
    two words collide iff their ids match. We build an (M, 2N) id matrix and
    count equal pairs across its 2N columns.
    """
    n = sq.n
    grid = sq.grid(state)  # (N, N) uint8
    next_id = len(vocab)
    nonword: dict[str, int] = {}

    # down_id[j, c] = id of the word read down column j if row i held letter c.
    down_id = np.empty((n, 26), dtype=np.int64)
    for j in range(n):
        col = grid[:, j].copy()
        for c in range(26):
            col[i] = c
            s = decode(col)
            wid = vocab.get(s)
            if wid is None:
                wid = nonword.get(s)
                if wid is None:
                    wid = next_id
                    nonword[s] = wid
                    next_id += 1
            down_id[j, c] = wid

    m = len(sq.rows)
    ids = np.empty((m, 2 * n), dtype=np.int64)
    # Across words: this row's candidate, plus the N-1 fixed other rows.
    ids[:, 0] = cand_across_id
    col_ptr = 1
    for r in range(n):
        if r == i:
            continue
        ids[:, col_ptr] = cand_across_id[state[r]]
        col_ptr += 1
    # Down words: pick each column's id by the candidate's letter in that column.
    letters = sq.rows.letters  # (M, N)
    for j in range(n):
        ids[:, n + j] = down_id[j, letters[:, j]]

    coll = np.zeros(m, dtype=np.float64)
    for a in range(2 * n):
        for b in range(a + 1, 2 * n):
            coll += ids[:, a] == ids[:, b]
    return coll


def _row_objective(
    sq: DoubleSquare,
    state: np.ndarray,
    i: int,
    quality: float,
    distinct: bool,
    cand_across_id: np.ndarray | None,
    vocab: dict[str, int],
) -> np.ndarray:
    """Objective for every candidate word in row i, holding other rows fixed:

        BIG * (#columns made valid)                       -- feasibility
        + quality * (across word score + induced down word scores)
        - DUP_WEIGHT * (#duplicate word-pairs)            -- distinctness

    With quality=0 and distinct=False this reduces to pure min-conflicts (count
    of valid columns)."""
    g = sq.grid(state)
    satisfied = np.zeros(len(sq.rows), dtype=np.float64)
    downq = np.zeros(len(sq.rows), dtype=np.float64)
    for j in range(sq.n):
        pattern: list[int | None] = [int(g[r, j]) for r in range(sq.n)]
        pattern[i] = None  # free the cell in the row we are re-choosing
        allowed, colscore = sq.cols.allowed_and_scores_at(pattern)
        cand_letter = sq.rows.letters[:, j]
        satisfied += allowed[cand_letter]
        downq += colscore[cand_letter]  # 0 where the column would be invalid
    obj = BIG * satisfied
    if quality:
        obj += quality * (sq.rows.scores + downq)
    if distinct:
        assert cand_across_id is not None  # the caller builds it whenever distinct
        obj -= DUP_WEIGHT * _distinct_penalty(sq, state, i, cand_across_id, vocab)
    return obj


def _is_distinct(sq: DoubleSquare, state: np.ndarray) -> bool:
    across = [sq.rows.words[i] for i in state]
    down = sq.column_strings(state)
    words = across + down
    return len(set(words)) == len(words)


def solve(
    sq: DoubleSquare,
    *,
    temperature: float = 0.0,
    quality: float = 0.0,
    distinct: bool = False,
    guided: bool = True,
    max_steps: int = 2000,
    max_restarts: int = 200,
    seed: int = 0,
) -> Result:
    """Min-conflicts / annealed-Gibbs search for a double word square.

    ``distinct`` requires all 2N words distinct (a genuine double word square).
    ``guided`` (default) folds the distinctness penalty into the move so the
    descent walks off the symmetric basin; ``guided=False`` is the naive baseline
    that restarts on every valid-but-degenerate grid (the symmetric basin is a
    fixed point of the unguided move, so it cannot climb out).
    """
    rng = np.random.default_rng(seed)
    total_steps = 0
    vocab = _word_ids(sq) if distinct else {}
    cand_across_id = (
        np.array([vocab[w] for w in sq.rows.words], dtype=np.int64) if distinct else None
    )
    for restart in range(max_restarts):
        state = rng.integers(0, len(sq.rows), size=sq.n)
        for _ in range(max_steps):
            total_steps += 1
            bad = sq.invalid_columns(state)
            if not bad:
                if not distinct or _is_distinct(sq, state):
                    return Result(state, 0, True, total_steps, restart)
                if not guided:
                    break  # gate baseline: degenerate fixed point -> restart
            i = int(rng.integers(0, sq.n))  # row to re-choose
            # The distinctness penalty only changes the argmax once the grid is
            # at/near feasibility -- with >1 invalid column, BIG*feasibility
            # dominates any distinctness delta. Gating it there keeps the common
            # (still-packing) step cheap, since the penalty rebuilds N*26 column
            # strings each time it runs.
            apply_penalty = distinct and guided and len(bad) <= 1
            obj = _row_objective(sq, state, i, quality, apply_penalty, cand_across_id, vocab)
            if temperature <= 0:
                best = np.flatnonzero(obj == obj.max())
                state[i] = int(rng.choice(best))
            else:
                logits = (obj - obj.max()) / temperature
                p = np.exp(logits)
                p /= p.sum()
                state[i] = int(rng.choice(len(obj), p=p))
    return Result(state, sq.energy(state), False, total_steps, max_restarts)
