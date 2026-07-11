"""Backtracking fill for a blocked grid -- a CSP over slots, not a scan of
columns.

Once black cells replace the induced-column trick (see blocked.py), filling is
the classic crossword problem: assign a word to every slot so that crossing
entries agree on their shared letter, and no entry repeats. We solve it the way
the fully-checked case taught us to (complete backtracking beats stochastic
search on small, hard, filtered lists -- D7), with two additions the varying
lengths force:

  * candidates come from a *pattern* query (a slot's already-fixed letters), via
    Lexicon.matching, against the right length bucket of a MultiLexicon;
  * slot ordering is dynamic MRV (minimum remaining values): always extend the
    unfilled slot with the fewest candidates, which collapses the search and
    detects a dead crossing (0 candidates) immediately.

Complete: if solve returns None the whole tree was exhausted -- a real proof that
the pattern admits no distinct fill from these lists. Randomised candidate order
gives distinct grids per seed, as before.
"""

from __future__ import annotations

from puzzledesk.core.blocked import BlockedGrid, Slot
from puzzledesk.core.lexicon import MultiLexicon
from puzzledesk.core.probe import NULL_PROBE, PROGRESS_STRIDE, Probe, Progress, Solved
from puzzledesk.core.rng import Rng


def _pattern(cell: dict[tuple[int, int], int], slot: Slot) -> list[int | None]:
    return [cell.get(rc) for rc in slot.cells]


def solve(
    g: BlockedGrid,
    mlex: MultiLexicon,
    *,
    rng: Rng,
    distinct: bool = True,
    randomize: bool = True,
    node_budget: int | None = None,
    probe: Probe = NULL_PROBE,
) -> dict[int, str] | None:
    """Return {slot_id: word} filling every slot, or None if none exists.

    ``rng`` (injected, fresh per seed) shuffles the MRV slot's candidate order for
    per-seed diversity; ``randomize=False`` ignores it. ``distinct`` (default)
    forbids repeating an entry anywhere in the grid, as a real crossword does.
    ``node_budget`` caps the search-tree nodes; None means run to completion (so
    None is a genuine UNSAT proof). ``probe`` (default no-op) observes the search:
    a sampled :class:`Progress` every ``PROGRESS_STRIDE`` nodes and a :class:`Solved`
    on success -- observe-only, so it cannot change the result."""
    if g.orphans:
        raise ValueError(f"grid has unchecked cells (runs < min_len): {g.orphans}")
    cell: dict[tuple[int, int], int] = {}
    assign: dict[int, str] = {}
    used: set[str] = set()
    nodes = 0

    def rec() -> dict[int, str] | None:
        nonlocal nodes
        nodes += 1
        if node_budget is not None and nodes > node_budget:
            return None
        if nodes % PROGRESS_STRIDE == 0:
            probe.emit(Progress("fill", nodes, len(assign)))
        unfilled = [s for s in g.slots if s.id not in assign]
        if not unfilled:
            probe.emit(Solved("fill", nodes))
            return dict(assign)
        # MRV: the unfilled slot with the fewest candidate words.
        best = best_lex = best_idxs = None
        for s in unfilled:
            lex = mlex.get(s.length)
            idxs = lex.matching(_pattern(cell, s))
            if best_idxs is None or len(idxs) < len(best_idxs):
                best, best_lex, best_idxs = s, lex, idxs
                if len(idxs) == 0:
                    break
        # `unfilled` is non-empty, so the loop always picks a best slot.
        assert best is not None and best_lex is not None and best_idxs is not None
        if len(best_idxs) == 0:
            return None  # dead crossing: this branch cannot complete
        order = list(best_idxs)
        if randomize:
            rng.shuffle(order)
        for idx in order:
            w = best_lex.words[idx]
            if distinct and w in used:
                continue
            written = []
            for k, rc in enumerate(best.cells):
                if rc not in cell:
                    cell[rc] = ord(w[k]) - 97
                    written.append(rc)
            assign[best.id] = w
            used.add(w)
            res = rec()
            if res is not None:
                return res
            del assign[best.id]
            used.discard(w)
            for rc in written:
                del cell[rc]
        return None

    return rec()


def enumerate_fills(
    g: BlockedGrid, mlex: MultiLexicon, *, limit: int | None = None, distinct: bool = True
) -> list[dict[int, str]]:
    """Every distinct fill (up to ``limit``). Ground truth for tiny grids -- the
    blocked-grid analogue of bruteforce.enumerate_squares."""
    if g.orphans:
        raise ValueError(f"grid has unchecked cells: {g.orphans}")
    cell: dict[tuple[int, int], int] = {}
    assign: dict[int, str] = {}
    used: set[str] = set()
    out: list[dict[int, str]] = []

    order = sorted(g.slots, key=lambda s: s.id)

    def rec(depth: int) -> None:
        if limit is not None and len(out) >= limit:
            return
        if depth == len(order):
            out.append(dict(assign))
            return
        s = order[depth]
        lex = mlex.get(s.length)
        for idx in lex.matching(_pattern(cell, s)):
            w = lex.words[idx]
            if distinct and w in used:
                continue
            written = []
            for k, rc in enumerate(s.cells):
                if rc not in cell:
                    cell[rc] = ord(w[k]) - 97
                    written.append(rc)
            assign[s.id] = w
            used.add(w)
            rec(depth + 1)
            del assign[s.id]
            used.discard(w)
            for rc in written:
                del cell[rc]
            if limit is not None and len(out) >= limit:
                return

    rec(0)
    return out


def letters_of(g: BlockedGrid, assign: dict[int, str]) -> dict[tuple[int, int], str]:
    """Cell -> letter for rendering, from a {slot_id: word} assignment."""
    slot = {s.id: s for s in g.slots}
    out: dict[tuple[int, int], str] = {}
    for sid, w in assign.items():
        for k, rc in enumerate(slot[sid].cells):
            out[rc] = w[k]
    return out
