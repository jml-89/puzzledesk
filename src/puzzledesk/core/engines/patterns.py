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

from ..blocked import BLOCK, WHITE, BlockedGrid
from ..lexicon import MultiLexicon
from ..rng import Rng, RngFactory
from . import fill


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
    rng: Rng,
    min_len: int = 3,
    symmetric: bool = True,
    randomize: bool = True,
) -> Iterator[BlockedGrid]:
    """Yield every legal :class:`BlockedGrid` with exactly ``num_black`` black
    cells (see module docstring for "legal").

    Complete: iterating to exhaustion enumerates all legal layouts, so an empty
    generator is a proof none exists (e.g. a symmetric grid with no centre cell
    cannot take an odd ``num_black``). ``rng`` (injected) shuffles the orbit order
    for diversity without affecting which layouts are reachable; ``randomize=False``
    leaves orbit order fixed (deterministic, for the ground-truth check).
    """
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


def _cell_ok(
    block: list[list[bool]],
    colrun: list[int],
    r: int,
    c: int,
    cols: int,
    is_black: bool,
    min_len: int,
    max_len: int | None,
) -> bool:
    """Row/column run-length prune for placing ``is_black`` at ``(r, c)`` during a
    row-major scan. Sound (never rejects a value a legal layout could use):

      * a black that *closes* a white run of length 1..min_len-1 (across or down)
        can never become legal -- that run is already too short;
      * a white that pushes its across/down run past ``max_len`` can never become
        legal -- the run is already too long.

    ``colrun[c]`` is the open (not-yet-closed) white run in column ``c`` as the scan
    descends. Row runs are read left-to-right from ``block``. The final open column
    runs (>= min_len) and connectivity are checked at the leaf, not here.
    """
    if is_black:
        run = 0  # white cells immediately left of (r, c) in this row
        cc = c - 1
        while cc >= 0 and not block[r][cc]:
            run += 1
            cc -= 1
        if 0 < run < min_len:
            return False
        return not 0 < colrun[c] < min_len
    run = 1  # this white plus the white run to its left
    cc = c - 1
    while cc >= 0 and not block[r][cc]:
        run += 1
        cc -= 1
    if max_len is not None and run > max_len:
        return False
    if max_len is not None and colrun[c] + 1 > max_len:
        return False
    # last column: this white run is final (no block can close it), so it must
    # already reach min_len.
    return not (c == cols - 1 and run < min_len)


def gen_capped(
    rows: int,
    cols: int,
    *,
    rng: Rng,
    min_len: int = 3,
    max_len: int | None = None,
    symmetric: bool = True,
    num_black: int | None = None,
    randomize: bool = True,
) -> Iterator[BlockedGrid]:
    """Yield every legal :class:`BlockedGrid` whose every entry has length in
    ``[min_len, max_len]`` (``max_len`` ``None`` == no upper bound).

    This is the cap-driven sibling of :func:`gen_patterns`: the governing parameter
    is the *maximum* run length, and the black-cell count falls out of it (pass
    ``num_black`` to also pin the count). Legality is otherwise identical to
    ``gen_patterns`` -- 180°-symmetric (unless ``symmetric=False``), fully checked,
    white cells 4-connected -- and with ``max_len=None`` and a fixed ``num_black`` it
    enumerates the *same set* ``gen_patterns`` does.

    Why a separate search: ``gen_patterns`` chooses black *orbits* and validates whole
    layouts at the leaf, so a run-length bound cannot prune until a layout is complete
    -- fine at 5x5, hopeless at 10x10 where a cap forces many blacks. This search runs
    **row-major** and prunes each partial row/column the moment a run is too short or
    too long (:func:`_cell_ok`), which is what makes a capped 10x10 tractable. It is
    still complete: iterating to exhaustion yields every legal layout, so an empty
    generator is a proof none exists. ``rng`` shuffles each cell's black/white order
    for per-seed diversity without changing the reachable set; ``randomize=False``
    fixes it (for the ground-truth check).
    """
    total = rows * cols
    if num_black is not None and (num_black < 0 or num_black >= total):
        return
    cells = [(r, c) for r in range(rows) for c in range(cols)]
    index = {rc: i for i, rc in enumerate(cells)}
    partner = {rc: _partner(rc[0], rc[1], rows, cols) for rc in cells}
    block = [[False] * cols for _ in range(rows)]
    colrun = [0] * cols

    def rec(idx: int, nblack: int) -> Iterator[BlockedGrid]:
        if idx == total:
            if num_black is not None and nblack != num_black:
                return
            if nblack == total:  # an all-black grid has no entries; not a puzzle
                return
            if any(0 < colrun[c] < min_len for c in range(cols)):
                return  # a final (bottom-edge) column run is too short
            if _connected(block, rows, cols, total - nblack):
                yield _to_grid(block, rows, cols, min_len)
            return
        # Lower-bound prune: even blackening every remaining cell can't reach the target.
        if num_black is not None and nblack + (total - idx) < num_black:
            return
        r, c = cells[idx]
        p = partner[(r, c)]
        if symmetric and index[p] < idx:
            choices = [block[p[0]][p[1]]]  # partner already fixed this cell
        else:
            choices = [False, True]
            if randomize:
                rng.shuffle(choices)
        for is_black in choices:
            if num_black is not None and is_black and nblack + 1 > num_black:
                continue
            if not _cell_ok(block, colrun, r, c, cols, is_black, min_len, max_len):
                continue
            saved = colrun[c]
            block[r][c] = is_black
            colrun[c] = 0 if is_black else colrun[c] + 1
            yield from rec(idx + 1, nblack + (1 if is_black else 0))
            block[r][c] = False
            colrun[c] = saved

    yield from rec(0, 0)


def fill_capped(
    rows: int,
    cols: int,
    mlex: MultiLexicon,
    *,
    rng_factory: RngFactory,
    max_len: int,
    seed: int = 0,
    min_len: int = 3,
    symmetric: bool = True,
    distinct: bool = True,
    num_black: int | None = None,
    node_budget: int | None = None,
    max_patterns: int | None = None,
) -> tuple[BlockedGrid, dict[int, str]] | None:
    """Search legal length-capped layouts for one that fills -- the cap-driven
    analogue of :func:`fill_by_count`.

    Returns ``(grid, assign)`` for the first :func:`gen_capped` layout (entries in
    ``[min_len, max_len]``) that admits a distinct fill from ``mlex``, or ``None``.
    Because a cap of ``max_len <= 5`` keeps every entry within the lengths the word
    data already covers (2..5), a 10x10 fills from the existing lists with no new
    data. Both searches are complete, so an *exhausted* ``None`` is a real UNSAT proof;
    but the capped layout space at 10x10 is astronomically large, so a ``None`` under a
    ``max_patterns``/``node_budget`` bound is exhaustion of the budget, not a theorem
    (say so when presenting it).
    """
    layouts = gen_capped(
        rows,
        cols,
        rng=rng_factory.create(seed),
        min_len=min_len,
        max_len=max_len,
        symmetric=symmetric,
        num_black=num_black,
    )
    for tried, g in enumerate(layouts):
        if max_patterns is not None and tried >= max_patterns:
            return None
        assign = fill.solve(
            g, mlex, rng=rng_factory.create(seed), distinct=distinct, node_budget=node_budget
        )
        if assign is not None:
            return g, assign
    return None


def fill_by_count(
    rows: int,
    cols: int,
    num_black: int,
    mlex: MultiLexicon,
    *,
    rng_factory: RngFactory,
    seed: int = 0,
    min_len: int = 3,
    symmetric: bool = True,
    distinct: bool = True,
    node_budget: int | None = None,
    max_patterns: int | None = None,
) -> tuple[BlockedGrid, dict[int, str]] | None:
    """Search legal ``num_black``-black layouts for one that fills.

    Returns ``(grid, assign)`` for the first layout that admits a distinct fill
    from ``mlex``, or ``None``. This composite re-seeds internally, so it takes an
    :class:`~puzzledesk.core.rng.RngFactory` (not a single stream) and a ``seed``:
    the layout search and every fill attempt each get a fresh ``factory.create(seed)``
    stream -- matching the original per-attempt seeding exactly. With both the
    layout search (`gen_patterns`) and the fill (`fill.solve`) complete and
    ``max_patterns``/``node_budget`` left as ``None``, a ``None`` return is a
    genuine UNSAT proof for this shape, count, and word lists. ``max_patterns``
    caps how many layouts are tried (trading the completeness of the proof for a
    time bound); it does not affect a SAT result.
    """
    layouts = gen_patterns(
        rows, cols, num_black, rng=rng_factory.create(seed), min_len=min_len, symmetric=symmetric
    )
    for tried, g in enumerate(layouts):
        if max_patterns is not None and tried >= max_patterns:
            return None
        assign = fill.solve(
            g, mlex, rng=rng_factory.create(seed), distinct=distinct, node_budget=node_budget
        )
        if assign is not None:
            return g, assign
    return None
