"""Relational difficulty: a mini's difficulty is a property of the crossing GRAPH,
not of any single word (a discovery spike, not a shipped model).

The lemma (the user's, formalised). Picture the *maximally hard* word: its clue is
useless -- it pins nothing, so from the clue alone the answer is one of many words.
Any *less* hard word has a somewhat-useful clue. Now the relation: if a somewhat-gettable
word **crosses** the hard word, then getting it donates a letter to the hard word, and the
hard word gets easier. So a word's difficulty is not intrinsic; it is *where it sits in the
solve, relative to what its neighbours give it*. Difficulty is relational.

This module formalises that as **information propagation on the crossing graph**, and it is
the network generalisation of ``app.difficulty.solve_order`` (D22): where ``solve_order``
replays ONE greedy easiest-first order with a score-based ``gimme`` proxy, this takes an
explicit **clue-power vector** -- which entries are gimmes (clue solvable alone) -- and
computes the whole *forced-solve DAG*: who unlocks whom, in how many parallel waves, and
whether it solves at all.

The model
---------
Entry ``e`` has cells; some are shared with crossing entries. A solver knows ``e``'s
letters from two sources: its **clue** and the **crossing letters** donated by neighbours
already solved. Model the clue as a binary per-entry flag -- a **gimme** (score/precision
enough to write the word from the clue alone) or not. Then:

  * A cell is *known* once any entry through it is solved (crossings share the cell).
  * An unsolved entry becomes *solvable* this wave iff it is a gimme, OR its currently-known
    cells already force it: ``n_candidates(answer, known-cells) == 1`` -- the lexicon admits
    exactly one word for the pattern its crossings have pinned.
  * Solve every newly-solvable entry at once (one **wave**), donate their cells, repeat.
  * If a wave solves nothing and the grid is incomplete, the remainder **deadlocks** -- a
    Natick cluster under this clue-power vector (the maximally-hard-word-with-no-useful-
    neighbours case, made a theorem).

Quantities this buys (all computable, no solve data, trivia-independent):

  * **depth** -- number of waves to solve. depth 1 == every entry a gimme (a bag of ten
    independent trivia clues, the D26 "not a constraint puzzle" regime). Higher depth ==
    longer forced-inference chains == the grid carries the solve.
  * **information floor** -- the *minimum* gimme set that still solves the grid. The dual of
    the lemma: how few useful clues suffice, because the crossings carry the rest.
  * **difficulty curve** -- depth as a function of how many clues you withhold: the fair,
    controllable difficulty of *this exact grid*, decoupled from vocabulary.
  * **keystones** -- entries whose gimme-status is load-bearing (redact them and the grid
    deadlocks). The words a setter must clue gently.

Usage:
    uv run scripts/relational.py                 # 5x5 fully-checked cw, a few seeds
    uv run scripts/relational.py 5 90 4          # N, min-score, count
    uv run scripts/relational.py blocked 5 5 4   # blocked ROWS COLS NUM_BLACK
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from itertools import combinations

from puzzledesk.app.puzzle import FilledGrid, filled_from_blocked, filled_from_square
from puzzledesk.bootstrap import build
from puzzledesk.core.engines import backtrack, patterns
from puzzledesk.core.square import DoubleSquare

# --- the entry graph ------------------------------------------------------------------

EntryId = tuple[tuple[int, int], str]  # (start cell, "A"/"D"): the spatial TargetId


@dataclass(frozen=True)
class Entry:
    eid: EntryId
    label: str  # "3A" etc., for display
    answer: str
    cells: tuple[tuple[int, int], ...]


def _entries(grid: FilledGrid) -> list[Entry]:
    numbering = grid.numbering()
    out = []
    for t in grid.runs():
        num = numbering[t.cells[0]]
        out.append(Entry(t.id, f"{num}{t.kind}", t.answer, t.cells))
    return out


# --- the propagation model ------------------------------------------------------------


@dataclass(frozen=True)
class Propagation:
    """The forced-solve DAG replayed from a gimme set: which wave each entry fell in,
    and whether the grid solved at all (else the leftover is a Natick cluster)."""

    wave_of: dict[EntryId, int]  # entry -> the wave it was solved in (1-based)
    stuck: tuple[EntryId, ...]  # entries never solved (deadlock / Natick cluster)

    @property
    def solved(self) -> bool:
        return not self.stuck

    @property
    def depth(self) -> int:
        """Number of waves to solve (0 if nothing solved). The difficulty scalar."""
        return max(self.wave_of.values(), default=0)


def propagate(entries: list[Entry], gimmes: set[EntryId], n_candidates) -> Propagation:
    """Replay the cascade from ``gimmes``. ``n_candidates(answer, known_indices)`` counts
    the lexicon words fitting ``answer`` when the given cell *indices* are pinned (the
    ``Lexicon.n_candidates`` primitive). An entry solves when it is a gimme or its known
    cells force it (candidates == 1). Solves in parallel waves; deterministic."""
    known: set[tuple[int, int]] = set()
    wave_of: dict[EntryId, int] = {}
    solved: set[EntryId] = set()
    wave = 0
    while len(solved) < len(entries):
        wave += 1
        newly: list[Entry] = []
        for e in entries:
            if e.eid in solved:
                continue
            known_idx = frozenset(i for i, c in enumerate(e.cells) if c in known)
            if e.eid in gimmes or n_candidates(e.answer, known_idx) == 1:
                newly.append(e)
        if not newly:
            break  # deadlock: the rest is a Natick cluster under this gimme set
        for e in newly:
            wave_of[e.eid] = wave
            solved.add(e.eid)
        for e in newly:  # donate letters AFTER the wave, so a wave is truly simultaneous
            known.update(e.cells)
    stuck = tuple(e.eid for e in entries if e.eid not in solved)
    return Propagation(wave_of, stuck)


# --- derived analyses -----------------------------------------------------------------


def information_floor(entries: list[Entry], n_candidates) -> tuple[frozenset[EntryId], int] | None:
    """The smallest gimme set that still solves the grid, and the depth it yields.
    The dual of the lemma: the fewest clues that must be *useful* because the crossings
    carry the rest. Exhaustive by increasing size (minis have ~10-12 entries). None if
    even every-entry-a-gimme fails (should never happen -- gimmes always solve)."""
    ids = [e.eid for e in entries]
    n = len(ids)
    if n > 18:  # exhaustive gets expensive; fall back to greedy removal
        return _greedy_floor(entries, n_candidates)
    for size in range(0, n + 1):
        best: tuple[frozenset[EntryId], int] | None = None
        for combo in combinations(ids, size):
            g = frozenset(combo)
            p = propagate(entries, set(g), n_candidates)
            if p.solved and (best is None or p.depth > best[1]):
                best = (g, p.depth)
        if best is not None:
            return best
    return None


def _greedy_floor(entries: list[Entry], n_candidates) -> tuple[frozenset[EntryId], int] | None:
    """Greedy fallback for big grids: start all-gimme, drop entries while it still solves."""
    g = {e.eid for e in entries}
    if not propagate(entries, g, n_candidates).solved:
        return None
    changed = True
    while changed:
        changed = False
        for e in entries:
            if e.eid in g and propagate(entries, g - {e.eid}, n_candidates).solved:
                g.discard(e.eid)
                changed = True
    return frozenset(g), propagate(entries, g, n_candidates).depth


def keystones(entries: list[Entry], n_candidates) -> list[EntryId]:
    """Entries that are load-bearing under the all-gimme clue set: redact this one clue
    (make it non-gimme) and the grid deadlocks. The words a setter *must* clue gently."""
    allg = {e.eid for e in entries}
    out = []
    for e in entries:
        if not propagate(entries, allg - {e.eid}, n_candidates).solved:
            out.append(e.eid)
    return out


def difficulty_curve(entries: list[Entry], n_candidates) -> list[tuple[int, int | None]]:
    """For each gimme-set size k (from all entries down to the floor), the MAX depth a
    solvable set of that size reaches -- the fair difficulty curve of this exact grid,
    made purely by withholding clues (no vocabulary/Natick tricks). None == no solvable
    set of that size (below the information floor)."""
    ids = [e.eid for e in entries]
    n = len(ids)
    curve: list[tuple[int, int | None]] = []
    if n > 16:
        return curve  # skip the exhaustive sweep on big grids
    for k in range(n, -1, -1):
        best: int | None = None
        for combo in combinations(ids, k):
            p = propagate(entries, set(combo), n_candidates)
            if p.solved and (best is None or p.depth > best):
                best = p.depth
        curve.append((k, best))
    return curve


# --- reporting ------------------------------------------------------------------------


def _render(grid: FilledGrid) -> str:
    return "\n".join(
        " ".join(
            "#" if grid.cells[r][c] is None else str(grid.cells[r][c]).upper()
            for c in range(grid.cols)
        )
        for r in range(grid.rows)
    )


def _label_of(entries: list[Entry], eid: EntryId) -> str:
    return next(e.label for e in entries if e.eid == eid)


def analyze_grid(grid: FilledGrid, n_candidates) -> None:
    entries = _entries(grid)
    labels = {e.eid: e.label for e in entries}
    print(f"\n{_render(grid)}")
    print("  entries: " + ", ".join(f"{e.label}={e.answer.upper()}" for e in entries))

    allg = {e.eid for e in entries}
    p_all = propagate(entries, allg, n_candidates)
    print(f"  all-gimme depth: {p_all.depth} (every clue useful -> a bag of trivia clues)")

    floor = information_floor(entries, n_candidates)
    if floor is None:
        print("  information floor: UNSOLVABLE even all-gimme (degenerate)")
        return
    fset, fdepth = floor
    flabels = sorted(labels[i] for i in fset)
    print(
        f"  information floor: {len(fset)}/{len(entries)} clues suffice {flabels} -> depth {fdepth}"
    )
    print(
        f"    (the other {len(entries) - len(fset)} answers are forced by crossings alone -- "
        f"their clues can be useless)"
    )

    keys = keystones(entries, n_candidates)
    print(
        "  keystones (redact this one clue -> deadlock): "
        + (", ".join(sorted(labels[i] for i in keys)) if keys else "none (fully robust)")
    )

    curve = difficulty_curve(entries, n_candidates)
    if curve:
        pts = " ".join(f"{k}:{'x' if d is None else d}" for k, d in curve)
        print(f"  difficulty curve  k(useful clues):depth  {pts}")

    # The bottleneck at the information floor: the last wave's entries, most-forced last.
    floor_prop = propagate(entries, set(fset), n_candidates)
    last = [e for e in entries if floor_prop.wave_of.get(e.eid) == fdepth]
    if last:
        print(
            "    deepest gets (solved last, only via the cascade): "
            + ", ".join(f"{e.label}={e.answer.upper()}" for e in last)
        )


# --- drivers ---------------------------------------------------------------------------


def run_square(container, n=5, min_score=90.0, count=3, tries=400) -> None:
    full = container.lexicon.load("cw", n)
    print(f"=== {n}x{n} fully-checked [cw], score >= {min_score:g} ===")
    sq = DoubleSquare(full.filtered(min_score))

    def n_candidates(answer, known):
        return full.n_candidates(answer, known)

    solved = 0
    for seed in range(tries):
        if solved >= count:
            break
        state = backtrack.solve(sq, rng=container.rng_factory.create(seed), distinct=True)
        if state is None:
            continue
        solved += 1
        analyze_grid(filled_from_square(sq, state), n_candidates)


def run_blocked(container, rows=5, cols=5, num_black=4, min_score=75.0, count=3, tries=400) -> None:
    lengths = range(3, max(rows, cols) + 1)
    full = container.lexicon.load_multi("cw", lengths)
    gen = container.lexicon.load_multi("cw", lengths, min_score=min_score)
    print(f"=== {rows}x{cols} blocked [cw], {num_black} black, score >= {min_score:g} ===")

    def n_candidates(answer, known):
        return full.get(len(answer)).n_candidates(answer, known)

    solved = 0
    for seed in range(tries):
        if solved >= count:
            break
        found = patterns.fill_by_count(
            rows, cols, num_black, gen, rng_factory=container.rng_factory, seed=seed, distinct=True
        )
        if found is None:
            continue
        grid, assign = found
        solved += 1
        analyze_grid(filled_from_blocked(grid, assign), n_candidates)


if __name__ == "__main__":
    args = sys.argv[1:]
    c = build()
    if args and args[0] == "blocked":
        run_blocked(
            c,
            int(args[1]) if len(args) > 1 else 5,
            int(args[2]) if len(args) > 2 else 5,
            int(args[3]) if len(args) > 3 else 4,
            float(args[4]) if len(args) > 4 else 75.0,
        )
    else:
        run_square(
            c,
            int(args[0]) if args else 5,
            float(args[1]) if len(args) > 1 else 90.0,
            int(args[2]) if len(args) > 2 else 3,
        )
