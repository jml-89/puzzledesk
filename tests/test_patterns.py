"""Layout-search ground truth (promoted from scripts/generate.py's property_check).

Enumerate every legal block layout with ``gen_patterns`` and cross-check the whole
set against brute force (all black-cell subsets tested against the invariants
directly), for both the symmetric and non-symmetric searches -- the layout
analogue of the fill ground-truth check.
"""

from __future__ import annotations

from itertools import combinations

import numpy as np

from puzzledesk.core.engines import patterns


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def _invariants_hold(g, rows: int, cols: int, num_black: int, symmetric: bool) -> bool:
    block = g.block
    if sum(block[r][c] for r in range(rows) for c in range(cols)) != num_black:
        return False
    if g.orphans:  # a white cell in no slot => a sub-min_len run
        return False
    for ds in g.cell_slots.values():  # fully checked: across AND down at every cell
        if "A" not in ds or "D" not in ds:
            return False
    if symmetric:
        for r in range(rows):
            for c in range(cols):
                if block[r][c] != block[rows - 1 - r][cols - 1 - c]:
                    return False
    return True


def _brute_force(rows: int, cols: int, num_black: int, symmetric: bool, min_len: int = 3) -> set:
    cells = [(r, c) for r in range(rows) for c in range(cols)]
    truth = set()
    for combo in combinations(cells, num_black):
        black = set(combo)
        g = patterns._to_grid(
            [[(r, c) in black for c in range(cols)] for r in range(rows)], rows, cols, min_len
        )
        if _invariants_hold(g, rows, cols, num_black, symmetric):
            truth.add(tuple(tuple(row) for row in g.block))
    return truth


def _generated(rows: int, cols: int, num_black: int, symmetric: bool) -> set:
    grids = list(
        patterns.gen_patterns(
            rows, cols, num_black, rng=_rng(0), min_len=3, symmetric=symmetric, randomize=False
        )
    )
    seen: set = set()
    for g in grids:
        assert _invariants_hold(g, rows, cols, num_black, symmetric), g.render()
        key = tuple(tuple(row) for row in g.block)
        assert key not in seen, "generator produced a duplicate layout"
        seen.add(key)
    return seen


def test_symmetric_layout_search_matches_brute_force() -> None:
    assert _generated(5, 5, 4, symmetric=True) == _brute_force(5, 5, 4, symmetric=True)


def test_nonsymmetric_odd_count_matches_brute_force() -> None:
    assert _generated(5, 5, 3, symmetric=False) == _brute_force(5, 5, 3, symmetric=False)


def test_symmetric_5x5_rejects_odd_black_count() -> None:
    # A centre black splits the middle row/column into length-2 runs, so no
    # symmetric 3-black 5x5 exists -- an empty generator is the proof.
    assert _generated(5, 5, 3, symmetric=True) == set()
