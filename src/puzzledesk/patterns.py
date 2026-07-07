"""Block-pattern generation: turn the black cells from a fixed template into a
*parameter*.

`blocked.py` takes a block pattern as INPUT -- you hand it the exact `.`/`#`
layout. This module is the piece that was deliberately left out of that spike
(see docs/open-questions.md, "Block-pattern generation"): given only a shape and
a *number* of black cells, generate the legal layouts and let fill place words in
them. "Specify how many blacks; let the search figure out where."

A layout is legal (an American-style grid) iff:

  * it has exactly ``num_black`` black cells;
  * (default) it is symmetric under 180° rotation -- the crossword convention;
  * every white cell lies in an across run AND a down run of length >= min_len
    (i.e. no white run is length 1..min_len-1): the grid is *fully checked*, no
    unchecked cells, no too-short entries; and
  * the white cells form a single connected region.

Generation is complete backtracking over the cells (grouped into 180°-rotation
orbits when symmetric), the same engine choice the rest of the system made (D7):
exhaustive, so "no pattern" is a proof, not a timeout, and randomised orbit order
gives per-seed diversity. Each yielded layout is a ready-to-fill
:class:`~puzzledesk.blocked.BlockedGrid`.

`fill_by_count` ties this to `fill.solve`: enumerate legal layouts, return the
first that admits a distinct fill from the given lists. Because both the layout
search and the fill are complete, a ``None`` result is a real theorem -- no
legal K-black layout of this shape fills from these lists.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator

import numpy as np

from . import fill
from .blocked import BLOCK, WHITE, BlockedGrid
from .lexicon import MultiLexicon


def _partner(r: int, c: int, rows: int, cols: int) -> tuple[int, int]:
    """The cell that maps onto (r, c) under a 180° rotation of the grid."""
    return (rows - 1 - r, cols - 1 - c)


def _orbits(rows: int, cols: int) -> list[list[tuple[int, int]]]:
    """Group cells into 180°-rotation orbits (row-major over representatives).

    Each orbit is a self-paired centre cell (odd*odd grids only) as a 1-list, or
    a {cell, its rotation partner} 2-list. A symmetric layout blackens whole
    orbits, so the orbit is the unit of choice -- and it is why a symmetric grid
    can only have an odd black count when it has a centre cell to carry it.
    """
    seen: set[tuple[int, int]] = set()
    orbits: list[list[tuple[int, int]]] = []
    for r in range(rows):
        for c in range(cols):
            if (r, c) in seen:
                continue
            p = _partner(r, c, rows, cols)
            if p == (r, c):
                orbits.append([(r, c)])
                seen.add((r, c))
            else:
                orbits.append([(r, c), p])
                seen.update({(r, c), p})
    return orbits


def _fully_checked(block: list[list[bool]], rows: int, cols: int, min_len: int) -> bool:
    """True iff no white run (across or down) has length in 1..min_len-1.

    Equivalent to "every white cell is in an across AND a down entry of length
    >= min_len": each white cell belongs to exactly one run each way, and a run
    that is neither empty nor short is >= min_len. This is the no-orphan,
    no-unchecked-cell condition blocked.py's fill demands.
    """
    for r in range(rows):
        run = 0
        for c in range(cols + 1):
            if c < cols and not block[r][c]:
                run += 1
            else:
                if 0 < run < min_len:
                    return False
                run = 0
    for c in range(cols):
        run = 0
        for r in range(rows + 1):
            if r < rows and not block[r][c]:
                run += 1
            else:
                if 0 < run < min_len:
                    return False
                run = 0
    return True


def _connected(block: list[list[bool]], rows: int, cols: int, n_white: int) -> bool:
    """True iff the white cells form one 4-connected region (BFS from any white
    cell must reach all of them). A split grid is two puzzles, not one."""
    start = next(((r, c) for r in range(rows) for c in range(cols) if not block[r][c]), None)
    if start is None:
        return n_white == 0
    seen = {start}
    dq = deque([start])
    while dq:
        r, c = dq.popleft()
        for nr, nc in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
            if 0 <= nr < rows and 0 <= nc < cols and not block[nr][nc] and (nr, nc) not in seen:
                seen.add((nr, nc))
                dq.append((nr, nc))
    return len(seen) == n_white


def _to_grid(block: list[list[bool]], rows: int, cols: int, min_len: int) -> BlockedGrid:
    rowstrs = ["".join(BLOCK if block[r][c] else WHITE for c in range(cols)) for r in range(rows)]
    return BlockedGrid.parse(rowstrs, min_len=min_len)


def gen_patterns(
    rows: int,
    cols: int,
    num_black: int,
    *,
    min_len: int = 3,
    symmetric: bool = True,
    seed: int = 0,
    randomize: bool = True,
) -> Iterator[BlockedGrid]:
    """Yield every legal :class:`BlockedGrid` with exactly ``num_black`` black
    cells (see module docstring for "legal").

    Complete: iterating to exhaustion enumerates all legal layouts, so an empty
    generator is a proof none exists (e.g. a symmetric grid with no centre cell
    cannot take an odd ``num_black``). ``randomize`` shuffles the orbit order per
    ``seed`` for diversity without affecting which layouts are reachable.
    """
    rng = np.random.default_rng(seed)
    total = rows * cols
    if num_black < 0 or num_black > total:
        return
    units = (
        _orbits(rows, cols) if symmetric else [[(r, c)] for r in range(rows) for c in range(cols)]
    )
    order = list(range(len(units)))
    if randomize:
        rng.shuffle(order)
    units = [units[i] for i in order]
    sizes = [len(u) for u in units]
    # suffix[i] = max blacks still placeable from unit i onward, for pruning.
    suffix = [0] * (len(units) + 1)
    for i in range(len(units) - 1, -1, -1):
        suffix[i] = suffix[i + 1] + sizes[i]

    block = [[False] * cols for _ in range(rows)]
    n_white_target = total - num_black
    placed = 0

    def rec(i: int) -> Iterator[BlockedGrid]:
        nonlocal placed
        if placed == num_black:
            # Budget spent; every remaining unit stays white. Validate this layout.
            if _fully_checked(block, rows, cols, min_len) and _connected(
                block, rows, cols, n_white_target
            ):
                yield _to_grid(block, rows, cols, min_len)
            return
        if i == len(units) or placed + suffix[i] < num_black:
            return
        # Branch 1: blacken unit i, if it fits the remaining budget.
        if placed + sizes[i] <= num_black:
            for r, c in units[i]:
                block[r][c] = True
            placed += sizes[i]
            yield from rec(i + 1)
            placed -= sizes[i]
            for r, c in units[i]:
                block[r][c] = False
        # Branch 2: leave unit i white.
        yield from rec(i + 1)

    yield from rec(0)


def fill_by_count(
    rows: int,
    cols: int,
    num_black: int,
    mlex: MultiLexicon,
    *,
    min_len: int = 3,
    symmetric: bool = True,
    seed: int = 0,
    distinct: bool = True,
    node_budget: int | None = None,
    max_patterns: int | None = None,
) -> tuple[BlockedGrid, dict[int, str]] | None:
    """Search legal ``num_black``-black layouts for one that fills.

    Returns ``(grid, assign)`` for the first layout that admits a distinct fill
    from ``mlex``, or ``None``. With both the layout search (`gen_patterns`) and
    the fill (`fill.solve`) complete and ``max_patterns``/``node_budget`` left as
    ``None``, a ``None`` return is a genuine UNSAT proof for this shape, count,
    and word lists. ``max_patterns`` caps how many layouts are tried (trading the
    completeness of the proof for a time bound); it does not affect a SAT result.
    """
    for tried, g in enumerate(
        gen_patterns(rows, cols, num_black, min_len=min_len, symmetric=symmetric, seed=seed)
    ):
        if max_patterns is not None and tried >= max_patterns:
            return None
        assign = fill.solve(g, mlex, seed=seed, distinct=distinct, node_budget=node_budget)
        if assign is not None:
            return g, assign
    return None
