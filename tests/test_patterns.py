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


# --- gen_capped: the cap-driven layout search (D24) -----------------------------


def _capped_set(rows, cols, num_black, symmetric, min_len, max_len) -> set:
    seen: set = set()
    for g in patterns.gen_capped(
        rows,
        cols,
        rng=_rng(0),
        min_len=min_len,
        max_len=max_len,
        symmetric=symmetric,
        num_black=num_black,
        randomize=False,
    ):
        key = tuple(tuple(row) for row in g.block)
        assert key not in seen, "gen_capped produced a duplicate layout"
        seen.add(key)
    return seen


def _brute_capped(rows, cols, num_black, symmetric, min_len, max_len) -> set:
    cells = [(r, c) for r in range(rows) for c in range(cols)]
    truth = set()
    for combo in combinations(cells, num_black):
        black = set(combo)
        block = [[(r, c) in black for c in range(cols)] for r in range(rows)]
        g = patterns._to_grid(block, rows, cols, min_len)
        if not _invariants_hold(g, rows, cols, num_black, symmetric):
            continue
        if any(s.length > max_len for s in g.slots):  # the cap
            continue
        if not patterns._connected(block, rows, cols, rows * cols - num_black):
            continue
        truth.add(tuple(tuple(row) for row in g.block))
    return truth


def test_capped_generalizes_gen_patterns() -> None:
    # With no upper bound, gen_capped enumerates the exact same set gen_patterns
    # does -- it is a strict generalization (and this cross-checks its completeness).
    for nb in range(9):
        assert _capped_set(5, 5, nb, True, 3, None) == _generated(5, 5, nb, symmetric=True)


def test_capped_matches_brute_force() -> None:
    # Where the cap bites (a length-5 run is illegal at max_len=4), gen_capped still
    # equals brute force over all black-cell subsets, both symmetries.
    for nb in range(9):
        assert _capped_set(5, 5, nb, True, 3, 4) == _brute_capped(5, 5, nb, True, 3, 4)
    for nb in range(7):
        assert _capped_set(5, 5, nb, False, 3, 4) == _brute_capped(5, 5, nb, False, 3, 4)


def test_capped_free_count_is_union_over_counts() -> None:
    # num_black=None (let the cap decide the count) == the union over every count.
    free = _capped_set(5, 5, None, True, 3, 4)
    union: set = set()
    for nb in range(26):
        union |= _capped_set(5, 5, nb, True, 3, 4)
    assert free == union and len(free) > 0


def test_capped_10x10_controls_max_word_length() -> None:
    # The headline: black cells cap every entry at max_len, so a 10x10 has no run
    # longer than 5 -- fillable from the 2..5 word data. Check several seeds.
    for seed in range(5):
        g = next(
            patterns.gen_capped(10, 10, rng=_rng(seed), min_len=3, max_len=5, symmetric=True),
            None,
        )
        assert g is not None, "a capped 10x10 layout must exist"
        assert not g.orphans  # fully checked
        assert all(3 <= s.length <= 5 for s in g.slots)  # every entry within [min,max]
        # symmetric
        block = g.block
        assert all(block[r][c] == block[9 - r][9 - c] for r in range(10) for c in range(10))


def test_capped_symmetric_even_grid_rejects_odd_count() -> None:
    # No centre cell on a 10x10, so an odd black count is impossible -- a proof,
    # exactly as gen_patterns rejects an odd count on the 5x5's even-parity orbits.
    assert next(patterns.gen_capped(10, 10, rng=_rng(0), max_len=5, num_black=17), None) is None
