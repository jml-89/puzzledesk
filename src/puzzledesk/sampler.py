"""Stochastic sampler for double word squares.

State = N row-word indices. Each step re-chooses one row's word to minimise the
number of invalid columns. The move is computed from the per-column "allowed
letters" marginal: for the chosen row i and each column j, which letters at
position i keep column j a valid word (given the other rows fixed). A candidate
row-word's score is how many columns it satisfies. We pick greedily at
temperature T=0, or sample proportional to exp(score / T) otherwise -- annealed
Gibbs over the row variable. Random restarts escape dead configurations.

This is deliberately plain NumPy: correct and easy to reason about at small N.
The hot loop (the per-candidate scoring) is the part that later vectorises onto
JAX for parallel-chain exploration at N=5.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .square import DoubleSquare


@dataclass
class Result:
    state: np.ndarray
    energy: int
    solved: bool
    steps: int
    restarts: int


def _row_scores(sq: DoubleSquare, state: np.ndarray, i: int) -> np.ndarray:
    """For row i, score every candidate row-word by how many of the N columns it
    would make valid, holding the other rows fixed."""
    g = sq.grid(state)
    scores = np.zeros(len(sq.rows), dtype=np.int32)
    for j in range(sq.n):
        pattern: list[int | None] = [int(g[r, j]) for r in range(sq.n)]
        pattern[i] = None  # free the cell in the row we are re-choosing
        allowed = sq.cols.allowed_at(pattern)  # 26-bool marginal for this column
        # +1 to every candidate whose letter at column j is allowed.
        scores += allowed[sq.rows.letters[:, j]]
    return scores


def solve(
    sq: DoubleSquare,
    *,
    temperature: float = 0.0,
    max_steps: int = 2000,
    max_restarts: int = 200,
    seed: int = 0,
) -> Result:
    rng = np.random.default_rng(seed)
    total_steps = 0
    for restart in range(max_restarts):
        state = rng.integers(0, len(sq.rows), size=sq.n)
        for _ in range(max_steps):
            total_steps += 1
            bad = sq.invalid_columns(state)
            if not bad:
                return Result(state, 0, True, total_steps, restart)
            i = int(rng.integers(0, sq.n))  # row to re-choose
            scores = _row_scores(sq, state, i)
            if temperature <= 0:
                best = np.flatnonzero(scores == scores.max())
                state[i] = int(rng.choice(best))
            else:
                logits = (scores - scores.max()) / temperature
                p = np.exp(logits)
                p /= p.sum()
                state[i] = int(rng.choice(len(scores), p=p))
    return Result(state, sq.energy(state), False, total_steps, max_restarts)
