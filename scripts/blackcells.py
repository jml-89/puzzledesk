"""Black-cell (blocked) crossword fill -- the spike that breaks the fully-checked
square model (benchmark/demo driver).

Parses a black-cell pattern into a slot/crossing graph (core.blocked), fills it as
a CSP over slots with complete MRV backtracking (core.engines.fill), drawing words
from a length-bucketed MultiLexicon filtered at the bar. The tiny-grid ground-truth
contract is also encoded as a test (tests/test_ground_truth.py).

Run: uv run scripts/blackcells.py
"""

import time

from puzzledesk.app.generate import result_of
from puzzledesk.bootstrap import build
from puzzledesk.cli import present
from puzzledesk.core.blocked import BlockedGrid
from puzzledesk.core.engines import fill


def show(container, g, mlex, assign):
    present.blocked_result(result_of(g, mlex, assign), container.writer)


def fill_demo(container, name, template, min_score=50.0, seed=0):
    g = BlockedGrid.parse(template, min_len=3)
    mlex = container.lexicon.load_multi("cw", g.lengths_needed(), min_score=min_score)
    sizes = {n: len(mlex.get(n)) for n in sorted(g.lengths_needed())}
    print(
        f"\n=== {name}  ({g.rows}x{g.cols}, {len(g.slots)} slots, "
        f"lengths {sorted(g.lengths_needed())}, list {sizes}, bar>={min_score:.0f}) ==="
    )
    t0 = time.perf_counter()
    assign = fill.solve(g, mlex, rng=container.rng_factory.create(seed), distinct=True)
    dt = time.perf_counter() - t0
    if assign is None:
        print(f"UNSAT (complete search, {dt * 1e3:.0f} ms)")
        return
    print(f"solved in {dt * 1e3:.0f} ms")
    show(container, g, mlex, assign)


def ground_truth_check(container):
    """Small-first: on a tiny blocked grid enumerate every distinct fill and
    assert the solver only ever emits one of them (cf. demo.py at N=2)."""
    g = BlockedGrid.parse(["...", "..#"], min_len=2)  # A3, A2, D2, D2, a real block
    mlex = container.lexicon.load_multi("scored", g.lengths_needed(), min_score=3.5)
    truth = {tuple(sorted(a.items())) for a in fill.enumerate_fills(g, mlex)}
    solved = bad = 0
    for seed in range(60):
        a = fill.solve(g, mlex, rng=container.rng_factory.create(seed), distinct=True)
        if a is None:
            continue
        solved += 1
        if tuple(sorted(a.items())) not in truth:
            bad += 1
    print("\n=== ground truth (2x3 blocked, weak list) ===")
    print(
        f"brute force: {len(truth)} distinct fills | "
        f"complete fill solver: {solved}/60 solved, {bad} outside ground truth"
    )
    assert bad == 0, "solver produced a fill not in the enumerated ground truth!"


def unsat_demo(container):
    """Quality ceiling on a fixed pattern: raise the bar until a fill no longer
    exists. Complete search REPORTS UNSAT (exhausted tree), not a timeout."""
    g = BlockedGrid.parse(["#...#", ".....", ".....", ".....", "#...#"], min_len=3)
    print("\n=== quality ceiling on the corner-block pattern ===")
    for bar in (50, 70, 85, 90, 92):
        mlex = container.lexicon.load_multi("cw", g.lengths_needed(), min_score=bar)
        sizes = {n: len(mlex.get(n)) for n in sorted(g.lengths_needed())}
        t0 = time.perf_counter()
        a = fill.solve(g, mlex, rng=container.rng_factory.create(0), distinct=True)
        dt = time.perf_counter() - t0
        verdict = "SAT" if a else "UNSAT"
        print(f"  bar>={bar}: list {sizes} -> {verdict:6s} ({dt * 1e3:6.0f} ms)")


def main():
    container = build()
    ground_truth_check(container)
    fill_demo(container, "corner blocks", ["#...#", ".....", ".....", ".....", "#...#"])
    fill_demo(
        container,
        "edge blocks (rotationally symmetric)",
        ["#....", ".....", ".....", ".....", "....#"],
        seed=2,
    )
    unsat_demo(container)


if __name__ == "__main__":
    main()
