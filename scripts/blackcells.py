"""Black-cell (blocked) crossword fill -- the spike that breaks the fully-checked
square model.

Once cells can be black the induced-column trick dies: the grid is a set of slots
(maximal white runs, across and down) that cross at shared cells, with varying
lengths. We parse the block pattern into that slot graph (blocked.py), fill it as
a CSP over slots with the same complete backtracking that won for the square
(fill.py), and draw words from a length-bucketed MultiLexicon filtered at the
acceptance bar -- so every entry clears the bar by construction, exactly as
before.

Run: python3 scripts/blackcells.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from puzzledesk import fill
from puzzledesk.blocked import BlockedGrid
from puzzledesk.lexicon import MultiLexicon

DATA = Path(__file__).resolve().parent.parent / "data"


def show(g, mlex, assign):
    print(g.render(fill.letters_of(g, assign)))
    across = sorted((s.number, mlex.get(s.length), assign[s.id])
                    for s in g.slots if s.direction == "A")
    down = sorted((s.number, mlex.get(s.length), assign[s.id])
                  for s in g.slots if s.direction == "D")
    a = "  ".join(f"{n}A {w}({lex.score_map[w]:.0f})" for n, lex, w in across)
    d = "  ".join(f"{n}D {w}({lex.score_map[w]:.0f})" for n, lex, w in down)
    print(f"  across: {a}")
    print(f"  down:   {d}")


def fill_demo(name, template, min_score=50.0, seed=0):
    g = BlockedGrid.parse(template, min_len=3)
    mlex = MultiLexicon.from_scored_files(lambda n: DATA / f"cw_{n}.txt",
                                          g.lengths_needed(), min_score=min_score)
    sizes = {n: len(mlex.get(n)) for n in sorted(g.lengths_needed())}
    print(f"\n=== {name}  ({g.rows}x{g.cols}, {len(g.slots)} slots, "
          f"lengths {sorted(g.lengths_needed())}, list {sizes}, bar>={min_score:.0f}) ===")
    t0 = time.perf_counter()
    assign = fill.solve(g, mlex, seed=seed, distinct=True)
    dt = time.perf_counter() - t0
    if assign is None:
        print(f"UNSAT (complete search, {dt*1e3:.0f} ms)")
        return
    print(f"solved in {dt*1e3:.0f} ms")
    show(g, mlex, assign)


def ground_truth_check():
    """Small-first: on a tiny blocked grid enumerate every distinct fill and
    assert the solver only ever emits one of them (cf. demo.py at N=2)."""
    g = BlockedGrid.parse(["...", "..#"], min_len=2)  # A3, A2, D2, D2, a real block
    mlex = MultiLexicon.from_scored_files(lambda n: DATA / f"scored_{n}.txt",
                                          g.lengths_needed(), min_score=3.5)
    truth = {tuple(sorted(a.items())) for a in fill.enumerate_fills(g, mlex)}
    solved = bad = 0
    for seed in range(60):
        a = fill.solve(g, mlex, seed=seed, distinct=True)
        if a is None:
            continue
        solved += 1
        if tuple(sorted(a.items())) not in truth:
            bad += 1
    print(f"\n=== ground truth (2x3 blocked, weak list) ===")
    print(f"brute force: {len(truth)} distinct fills | "
          f"sampler-free solver: {solved}/60 solved, {bad} outside ground truth")
    assert bad == 0, "solver produced a fill not in the enumerated ground truth!"


def unsat_demo():
    """Quality ceiling on a fixed pattern: raise the bar until a fill no longer
    exists. Complete search REPORTS UNSAT (exhausted tree), not a timeout. As in
    the square case, the ceiling is set by the lexicon -- here the shortest slot
    (length 3) runs dry first, so watch its bucket size hit 0."""
    g = BlockedGrid.parse(["#...#", ".....", ".....", ".....", "#...#"], min_len=3)
    print(f"\n=== quality ceiling on the corner-block pattern ===")
    for bar in (50, 70, 85, 90, 92):
        mlex = MultiLexicon.from_scored_files(lambda n: DATA / f"cw_{n}.txt",
                                              g.lengths_needed(), min_score=bar)
        sizes = {n: len(mlex.get(n)) for n in sorted(g.lengths_needed())}
        t0 = time.perf_counter()
        a = fill.solve(g, mlex, seed=0, distinct=True)
        dt = time.perf_counter() - t0
        verdict = "SAT" if a else "UNSAT"
        print(f"  bar>={bar}: list {sizes} -> {verdict:6s} ({dt*1e3:6.0f} ms)")


def main():
    ground_truth_check()
    fill_demo("corner blocks", ["#...#", ".....", ".....", ".....", "#...#"])
    fill_demo("edge blocks (rotationally symmetric)",
              ["#....", ".....", ".....", ".....", "....#"], seed=2)
    unsat_demo()


if __name__ == "__main__":
    main()
