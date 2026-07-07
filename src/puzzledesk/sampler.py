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


# Feasibility must dominate quality: BIG exceeds any achievable quality delta so
# a move never trades a valid column away for a more common word.
BIG = 1000.0


def _row_objective(sq: DoubleSquare, state: np.ndarray, i: int, quality: float) -> np.ndarray:
    """Objective for every candidate word in row i, holding other rows fixed:

        BIG * (#columns made valid)                       -- feasibility
        + quality * (across word score + induced down word scores)

    With quality=0 this reduces to pure min-conflicts (count of valid columns)."""
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
    return obj


def solve(
    sq: DoubleSquare,
    *,
    temperature: float = 0.0,
    quality: float = 0.0,
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
            obj = _row_objective(sq, state, i, quality)
            if temperature <= 0:
                best = np.flatnonzero(obj == obj.max())
                state[i] = int(rng.choice(best))
            else:
                logits = (obj - obj.max()) / temperature
                p = np.exp(logits)
                p /= p.sum()
                state[i] = int(rng.choice(len(obj), p=p))
    return Result(state, sq.energy(state), False, total_steps, max_restarts)
