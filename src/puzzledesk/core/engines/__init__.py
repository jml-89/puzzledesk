"""Solving engines over the two grid models.

Squares: :mod:`backtrack` (primary, complete) and :mod:`sampler` (secondary,
stochastic), with :mod:`bruteforce` as tiny-N ground truth. Blocked grids:
:mod:`fill` (complete MRV backtracking over slots) and :mod:`patterns` (generate
legal block layouts from a count, then fill).

Every engine takes its randomness as an injected :class:`~puzzledesk.core.rng.Rng`
(or, where it re-seeds internally, a :class:`~puzzledesk.core.rng.RngFactory`)
rather than constructing ``np.random.default_rng`` itself -- randomness is the
kernel's one impure dependency, kept at the boundary so a fake stream can drive
the engines under test.
"""
