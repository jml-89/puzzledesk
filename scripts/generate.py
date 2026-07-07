"""Generate blocked minis from a black-cell COUNT, not a fixed template.

`blackcells.py` fills a block pattern you hand it. This script takes the layout
away as input: give it a shape and a number of black cells and it searches legal
layouts (180°-symmetric, fully checked at min length, connected white cells --
see patterns.py) for one that fills with distinct words above the quality bar.

    python3 scripts/generate.py [rows] [cols] [num_black] [min_score] [count]
    python3 scripts/generate.py 5 5 4 60 3

A ground-truth property check on a tiny grid runs first (small-first, cf.
blackcells.py): enumerate every legal layout and assert the invariants hold.
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


def property_check():
    """Small-first: on a 5x5 with 4 blacks, enumerate every legal layout, assert
    each satisfies the invariants and is unique, AND cross-check the whole set
    against brute force -- the layout analogue of fill.enumerate_fills."""
    rows = cols = 5
    num_black = 4
    grids = list(patterns.gen_patterns(rows, cols, num_black, min_len=3,
                                       symmetric=True, randomize=False))
    seen = set()
    for g in grids:
        assert _invariants_hold(g, rows, cols, num_black, 3, True), g.render()
        key = tuple(tuple(row) for row in g.block)
        assert key not in seen, "generator produced a duplicate layout"
        seen.add(key)
    truth = _brute_force_layouts(rows, cols, num_black, 3, True)
    assert seen == truth, "generator disagrees with brute-force ground truth"
    print("=== ground truth (5x5, 4 blacks, symmetric) ===")
    print(f"legal layouts: {len(grids)} enumerated, matching brute force exactly "
          f"(fully-checked, connected, symmetric, distinct)")


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


def main(rows=5, cols=5, num_black=4, min_score=60.0, count=3):
    lengths = range(3, max(rows, cols) + 1)
    mlex = MultiLexicon.from_scored_files(lambda n: DATA / f"cw_{n}.txt",
                                          lengths, min_score=min_score)
    print(f"\n{rows}x{cols} blocked minis, {num_black} black cells, every word "
          f"score >= {min_score:.0f}\n")

    # Structural feasibility first: does any legal layout exist at all? This is a
    # property of the shape + symmetry + min-length, independent of the word list.
    if next(patterns.gen_patterns(rows, cols, num_black, symmetric=True), None) is None:
        print(f"no legal {num_black}-black layout exists for a symmetric {rows}x{cols} "
              f"grid (min-length or symmetry forbids it).")
        if rows * cols % 2 == 0 and num_black % 2 == 1:
            print("  a symmetric grid with an even cell count cannot take an odd "
                  "black count (no centre cell to carry it).")
        return

    shown = 0
    for seed in range(count * 20):
        t0 = time.perf_counter()
        res = patterns.fill_by_count(rows, cols, num_black, mlex, seed=seed,
                                     distinct=True)
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
    rows = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    cols = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    nb = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    ms = float(sys.argv[4]) if len(sys.argv) > 4 else 60.0
    ct = int(sys.argv[5]) if len(sys.argv) > 5 else 3
    main(rows, cols, nb, ms, ct)
