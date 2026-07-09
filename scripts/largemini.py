"""Large capped minis -- the 10x10+ spike (benchmark/demo driver, D24).

The problem: a mini bigger than 5x5 wants black cells placed so the *maximum*
entry length is controlled -- you do NOT want a row of ten 10-letter words. That
is exactly what makes it fillable from the word data we already have (lengths
2..5): cap every entry at <= max_len and no length-6+ list is needed.

This driver measures the cap-driven layout search (``patterns.gen_capped``):
  1. why the count-driven ``gen_patterns`` (D13) cannot do it (giant runs);
  2. the capped search's black-count distribution and timing;
  3. fill rate from the cw 2..5 lists across quality bars and grid sizes;
  4. a rendered example 10x10.

Run: uv run scripts/largemini.py
"""

import time
from collections import Counter

from puzzledesk.bootstrap import build
from puzzledesk.cli import present
from puzzledesk.core.engines import patterns


def _max_run(g):
    return max((s.length for s in g.slots), default=0)


def motivation(container):
    """The count-driven search produces giant runs; the cap-driven one does not."""
    print("=== why a cap is needed (10x10) ===")
    rng = container.rng_factory.create(0)
    t0 = time.perf_counter()
    g = next(patterns.gen_patterns(10, 10, 20, rng=rng, min_len=3), None)
    dt = time.perf_counter() - t0
    print(
        f"  gen_patterns(10x10, 20 black): first layout in {dt * 1e3:.0f} ms, "
        f"longest entry = {_max_run(g) if g else '-'} letters (uncapped -> a 10-letter word)"
    )
    t0 = time.perf_counter()
    gc = next(patterns.gen_capped(10, 10, rng=container.rng_factory.create(0), max_len=5), None)
    dt = time.perf_counter() - t0
    print(
        f"  gen_capped(10x10, max_len=5): first layout in {dt * 1e3:.0f} ms, "
        f"longest entry = {_max_run(gc) if gc else '-'} letters"
    )


def layout_stats(container, rows, cols, max_len, n=40):
    """Black-count distribution and timing for the diversified capped search."""
    print(f"\n=== capped layouts {rows}x{cols}, max_len={max_len} ({n} seeds) ===")
    counts, times, bad = Counter(), [], 0
    for seed in range(n):
        t0 = time.perf_counter()
        rng = container.rng_factory.create(seed)
        g = next(patterns.gen_capped(rows, cols, rng=rng, max_len=max_len), None)
        times.append(time.perf_counter() - t0)
        if g is None:
            bad += 1
            continue
        nb = sum(g.block[r][c] for r in range(rows) for c in range(cols))
        counts[nb] += 1
        assert not g.orphans and _max_run(g) <= max_len  # fully checked, capped
    med = sorted(times)[len(times) // 2] * 1e3
    lo, hi = min(counts), max(counts)
    print(f"  {n - bad}/{n} found; black cells range {lo}..{hi} ({lo}-{hi}% of the grid)")
    print(f"  layout search: median {med:.1f} ms, max {max(times) * 1e3:.1f} ms")


def fill_rate(container, rows, cols, max_len, bars=(50, 60, 70, 75), seeds=10):
    """Fill rate + timing from cw 2..max_len across quality bars."""
    print(f"\n=== fill rate {rows}x{cols}, max_len={max_len}, cw list ===")
    for bar in bars:
        solved, ftimes, entries = 0, [], 0
        for seed in range(seeds):
            t0 = time.perf_counter()
            res = container.blocked.fill_capped_once(
                rows, cols, max_len=max_len, min_score=bar, seed=seed
            )
            ftimes.append(time.perf_counter() - t0)
            if res is not None:
                solved += 1
                entries = len(res.across) + len(res.down)
        med = sorted(ftimes)[len(ftimes) // 2] * 1e3
        print(f"  bar>={bar}: {solved}/{seeds} filled ({entries} entries), median {med:.0f} ms")


def example(container, rows, cols, max_len, bar):
    print(f"\n=== example {rows}x{cols} mini, max_len={max_len}, bar>={bar} ===")
    for seed in range(20):
        res = container.blocked.fill_capped_once(
            rows, cols, max_len=max_len, min_score=bar, seed=seed
        )
        if res is not None:
            present.blocked_result(res, container.writer)
            return
    print("  (no fill in the seed budget)")


def main():
    container = build()
    motivation(container)
    # 10x10 is the target and 12x12 still comfortable; 13x13+ is the frontier
    # (the leaf-only connectivity check makes the layout search backtrack heavily
    # -- the "pruning before 15x15" follow-up in docs/open-questions).
    for rows, cols, ml in ((10, 10, 5), (12, 12, 5)):
        layout_stats(container, rows, cols, ml)
        fill_rate(container, rows, cols, ml)
    example(container, 10, 10, 5, 70)


if __name__ == "__main__":
    main()
