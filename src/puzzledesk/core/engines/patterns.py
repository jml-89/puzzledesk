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

from puzzledesk.core.blocked import BLOCK, WHITE, BlockedGrid
from puzzledesk.core.engines import fill
from puzzledesk.core.lexicon import MultiLexicon
from puzzledesk.core.probe import (
    NULL_PROBE,
    PROGRESS_STRIDE,
    Attempt,
    Finished,
    PhaseStarted,
    Probe,
    Progress,
)
from puzzledesk.core.rng import Rng, RngFactory

# gen_capped's randomized cell order is white-biased: black-first this % of the
# time, white-first otherwise. Low => fewer, less-clustered blacks (cleaner grids);
# it only reorders search branches, so completeness is unaffected (D25).
_BLACK_FIRST_PCT = 15


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
    max_black: int | None = None,
    node_budget: int | None = None,
    randomize: bool = True,
    probe: Probe = NULL_PROBE,
) -> Iterator[BlockedGrid]:
    """Yield every legal :class:`BlockedGrid` whose every entry has length in
    ``[min_len, max_len]`` (``max_len`` ``None`` == no upper bound).

    This is the cap-driven sibling of :func:`gen_patterns`: the governing parameter
    is the *maximum* run length, and the black-cell count falls out of it. Two optional
    density knobs shape the count: ``num_black`` pins it exactly; ``max_black`` is an
    *upper bound* (yield only layouts with <= max_black blacks). Legality is otherwise
    identical to ``gen_patterns`` -- 180°-symmetric (unless ``symmetric=False``), fully
    checked, white cells 4-connected -- and with ``max_len=None`` and a fixed
    ``num_black`` it enumerates the *same set* ``gen_patterns`` does.

    Why a separate search: ``gen_patterns`` chooses black *orbits* and validates whole
    layouts at the leaf, so a run-length bound cannot prune until a layout is complete
    -- fine at 5x5, hopeless at 10x10 where a cap forces many blacks. This search runs
    **row-major** and prunes each partial row/column the moment a run is too short or
    too long (:func:`_cell_ok`), which is what makes a capped 10x10 tractable. It is
    still complete: iterating to exhaustion yields every legal layout (with <=
    ``max_black`` blacks if set), so an empty generator is a proof none exists.

    Diversity vs density (D25): ``randomize`` picks each free cell's black/white *order*,
    biased **white-first** (``_BLACK_FIRST_PCT`` of the time black-first) so the search
    prefers *fewer, less-clustered* black cells -- a much cleaner, real-crossword-like
    grid than a uniform 50/50 order, which over-blackens. The bias only reorders which
    layout appears first per seed; the reachable set (and completeness) is unchanged.
    ``randomize=False`` fixes a deterministic white-first order (for the ground-truth check).

    ``node_budget`` caps the search-tree nodes (like ``fill.solve``'s): the search stops
    early once exceeded, so a *budgeted* empty generator is exhaustion of the budget,
    **not** a proof (leave it ``None`` for the completeness guarantee). It exists because a
    black ceiling near the minimum feasible count makes the search backtrack heavily (a
    12x12 at a tight cap can otherwise run away, D25); the per-seed caller just moves to
    the next seed when a pathological one bails.
    """
    total = rows * cols
    if num_black is not None and (num_black < 0 or num_black >= total):
        return
    if max_black is not None and max_black < 0:
        return
    if num_black is not None and max_black is not None and num_black > max_black:
        return
    cells = [(r, c) for r in range(rows) for c in range(cols)]
    index = {rc: i for i, rc in enumerate(cells)}
    partner = {rc: _partner(rc[0], rc[1], rows, cols) for rc in cells}
    block = [[False] * cols for _ in range(rows)]
    colrun = [0] * cols
    nodes = 0

    def rec(idx: int, nblack: int) -> Iterator[BlockedGrid]:
        nonlocal nodes
        nodes += 1
        if node_budget is not None and nodes > node_budget:
            return  # budget spent: unwind (a budgeted empty result is not a proof)
        if nodes % PROGRESS_STRIDE == 0:
            probe.emit(Progress("layout", nodes, idx))
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
            # White-first, so the search prefers fewer/cleaner blacks; occasionally
            # black-first for diversity (D25). Order only; completeness is unaffected.
            choices = [False, True]
            if randomize and rng.integers(0, 100) < _BLACK_FIRST_PCT:
                choices = [True, False]
        for is_black in choices:
            if is_black and num_black is not None and nblack + 1 > num_black:
                continue
            if is_black and max_black is not None and nblack + 1 > max_black:
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
    max_black: int | None = None,
    node_budget: int | None = None,
    layout_node_budget: int | None = None,
    max_patterns: int | None = None,
    probe: Probe = NULL_PROBE,
) -> tuple[BlockedGrid, dict[int, str]] | None:
    """Search legal length-capped layouts for one that fills -- the cap-driven
    analogue of :func:`fill_by_count`.

    Returns ``(grid, assign)`` for the first :func:`gen_capped` layout (entries in
    ``[min_len, max_len]``) that admits a distinct fill from ``mlex``, or ``None``.
    Because a cap of ``max_len <= 5`` keeps every entry within the lengths the word
    data already covers (2..5), a 10x10 fills from the existing lists with no new data.
    ``num_black``/``max_black`` control density (an exact count or an upper bound, D25).
    Both searches are complete, so an *exhausted* ``None`` is a real UNSAT proof;
    but the capped layout space at 10x10 is astronomically large, so a ``None`` under a
    ``max_patterns``/``node_budget`` bound is exhaustion of the budget, not a theorem
    (say so when presenting it).
    """
    probe.emit(PhaseStarted("capped", f"{rows}x{cols} cap<={max_len}"))
    layouts = gen_capped(
        rows,
        cols,
        rng=rng_factory.create(seed),
        min_len=min_len,
        max_len=max_len,
        symmetric=symmetric,
        num_black=num_black,
        max_black=max_black,
        node_budget=layout_node_budget,
        probe=probe,
    )
    # A None here is a UNSAT *proof* only if nothing bounded the search (both stages
    # complete); otherwise it is budget exhaustion. That tag is exactly the reason on
    # the terminal Finished event.
    complete = layout_node_budget is None and max_patterns is None and node_budget is None
    tried = 0
    for i, g in enumerate(layouts):
        if max_patterns is not None and i >= max_patterns:
            probe.emit(Finished(ok=False, reason="budget", attempts=tried))
            return None
        tried += 1
        probe.emit(Attempt(i, sum(sum(row) for row in g.block), len(g.slots)))
        assign = fill.solve(
            g,
            mlex,
            rng=rng_factory.create(seed),
            distinct=distinct,
            node_budget=node_budget,
            probe=probe,
        )
        if assign is not None:
            probe.emit(Finished(ok=True, reason="solved", attempts=tried))
            return g, assign
    probe.emit(Finished(ok=False, reason="exhausted" if complete else "budget", attempts=tried))
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
