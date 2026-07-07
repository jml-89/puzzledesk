"""Generate blocked minis from a black-cell COUNT, not a fixed template.

`blackcells.py` fills a block pattern you hand it. This script takes the layout
away as input: give it a shape and a number of black cells and it searches legal
layouts (fully checked at min length, connected white cells -- see patterns.py)
for one that fills with distinct words above the quality bar.

By default the search is restricted to 180°-symmetric layouts (the crossword
convention). Pass ``--nonsymmetric`` (alias ``--asym``) to drop that constraint
and allow any legal placement -- which is the only way to get an *odd* black
count on an even-cell grid, or any count a centre-cell black would forbid (e.g.
3 blacks across a 5x5, where a symmetric layout would split the middle
row/column into sub-``min_len`` runs).

    python3 scripts/generate.py [rows] [cols] [num_black] [min_score] [count] [--nonsymmetric]
    python3 scripts/generate.py 5 5 4 60 3
    python3 scripts/generate.py 5 5 3 60 3 --nonsymmetric

A ground-truth property check on tiny grids runs first (small-first, cf.
blackcells.py): enumerate every legal layout -- symmetric and non-symmetric --
and assert the invariants hold and match brute force exactly.
"""

import sys
import time
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from puzzledesk import patterns
from puzzledesk.lexicon import MultiLexicon

DATA = Path(__file__).resolve().parent.parent / "data"


def _invariants_hold(g, rows, cols, num_black, min_len, symmetric):
    """Re-derive the legality conditions independently of the generator."""
    block = g.block
    if sum(block[r][c] for r in range(rows) for c in range(cols)) != num_black:
        return False
    if g.orphans:  # any white cell in no slot => a run shorter than min_len
        return False
    for cell, ds in g.cell_slots.items():  # fully checked: across AND down at every cell
        if "A" not in ds or "D" not in ds:
            return False
    if symmetric:
        for r in range(rows):
            for c in range(cols):
                if block[r][c] != block[rows - 1 - r][cols - 1 - c]:
                    return False
    return True


def _brute_force_layouts(rows, cols, num_black, min_len, symmetric):
    """Ground truth: every legal layout, found by testing all C(cells, num_black)
    black-cell subsets against the invariants directly (viable only for tiny grids,
    cf. bruteforce.py). Returns a set of block-tuples."""
    cells = [(r, c) for r in range(rows) for c in range(cols)]
    truth = set()
    for combo in combinations(cells, num_black):
        black = set(combo)
        g = patterns._to_grid([[(r, c) in black for c in range(cols)]
                               for r in range(rows)], rows, cols, min_len)
        if _invariants_hold(g, rows, cols, num_black, min_len, symmetric):
            truth.add(tuple(tuple(row) for row in g.block))
    return truth


def _check_case(rows, cols, num_black, symmetric):
    """Enumerate every legal layout for one case, assert each satisfies the
    invariants and is unique, AND cross-check the whole set against brute force
    -- the layout analogue of fill.enumerate_fills. Returns the layout count."""
    grids = list(patterns.gen_patterns(rows, cols, num_black, min_len=3,
                                       symmetric=symmetric, randomize=False))
    seen = set()
    for g in grids:
        assert _invariants_hold(g, rows, cols, num_black, 3, symmetric), g.render()
        key = tuple(tuple(row) for row in g.block)
        assert key not in seen, "generator produced a duplicate layout"
        seen.add(key)
    truth = _brute_force_layouts(rows, cols, num_black, 3, symmetric)
    assert seen == truth, "generator disagrees with brute-force ground truth"
    return len(grids)


def property_check():
    """Small-first: enumerate every legal layout and cross-check it against brute
    force, for BOTH the symmetric and non-symmetric searches. The non-symmetric
    case is checked at an odd black count -- one a symmetric 5x5 cannot take at
    all (a centre black splits the middle row/column into sub-min_len runs), so
    it exercises exactly what dropping symmetry buys."""
    print("=== ground truth (layout search vs brute force) ===")
    n_sym = _check_case(5, 5, 4, symmetric=True)
    print(f"5x5, 4 blacks, symmetric:     {n_sym} legal layouts, matching brute "
          f"force exactly")
    # Symmetric 5x5 cannot place 3 blacks at all; non-symmetric can.
    assert _check_case(5, 5, 3, symmetric=True) == 0
    n_asym = _check_case(5, 5, 3, symmetric=False)
    print(f"5x5, 3 blacks, non-symmetric: {n_asym} legal layouts, matching brute "
          f"force exactly (symmetric admits 0 -- odd count needs no centre split)")


def render(g, mlex, assign):
    from puzzledesk import fill
    print(g.render(fill.letters_of(g, assign)))
    across = sorted((s.number, mlex.get(s.length), assign[s.id])
                    for s in g.slots if s.direction == "A")
    down = sorted((s.number, mlex.get(s.length), assign[s.id])
                  for s in g.slots if s.direction == "D")
    a = "  ".join(f"{n}A {w}({lex.score_map[w]:.0f})" for n, lex, w in across)
    d = "  ".join(f"{n}D {w}({lex.score_map[w]:.0f})" for n, lex, w in down)
    print(f"  across: {a}")
    print(f"  down:   {d}")


def main(rows=5, cols=5, num_black=4, min_score=60.0, count=3, symmetric=True):
    lengths = range(3, max(rows, cols) + 1)
    mlex = MultiLexicon.from_scored_files(lambda n: DATA / f"cw_{n}.txt",
                                          lengths, min_score=min_score)
    kind = "symmetric" if symmetric else "non-symmetric"
    print(f"\n{rows}x{cols} {kind} blocked minis, {num_black} black cells, every "
          f"word score >= {min_score:.0f}\n")

    # Structural feasibility first: does any legal layout exist at all? This is a
    # property of the shape + symmetry + min-length, independent of the word list.
    if next(patterns.gen_patterns(rows, cols, num_black, symmetric=symmetric),
            None) is None:
        print(f"no legal {num_black}-black layout exists for a {kind} {rows}x{cols} "
              f"grid (min-length"
              f"{' or symmetry' if symmetric else ''} forbids it).")
        if symmetric and rows * cols % 2 == 0 and num_black % 2 == 1:
            print("  a symmetric grid with an even cell count cannot take an odd "
                  "black count (no centre cell to carry it) -- try --nonsymmetric.")
        elif symmetric and rows * cols % 2 == 1 and num_black % 2 == 1:
            print("  a symmetric odd-cell grid takes an odd black count only via a "
                  "centre black, which may split the middle row/column into "
                  "sub-min_len runs -- try --nonsymmetric.")
        return

    shown = 0
    for seed in range(count * 20):
        t0 = time.perf_counter()
        res = patterns.fill_by_count(rows, cols, num_black, mlex, seed=seed,
                                     symmetric=symmetric, distinct=True)
        dt = time.perf_counter() - t0
        if res is None:
            if seed == 0:  # complete search over layouts: one run settles it
                print(f"legal layouts exist, but none fills at score >= {min_score:.0f} "
                      f"(searched them in {dt*1e3:.0f} ms). Try a lower min_score.")
            break
        g, assign = res
        render(g, mlex, assign)
        print(f"  ({dt*1e3:.0f} ms)\n")
        shown += 1
        if shown >= count:
            break


if __name__ == "__main__":
    property_check()
    argv = sys.argv[1:]
    symmetric = True
    for flag in ("--nonsymmetric", "--asym"):
        if flag in argv:
            symmetric = False
            argv = [a for a in argv if a != flag]
    rows = int(argv[0]) if len(argv) > 0 else 5
    cols = int(argv[1]) if len(argv) > 1 else 5
    nb = int(argv[2]) if len(argv) > 2 else 4
    ms = float(argv[3]) if len(argv) > 3 else 60.0
    ct = int(argv[4]) if len(argv) > 4 else 3
    main(rows, cols, nb, ms, ct, symmetric=symmetric)
