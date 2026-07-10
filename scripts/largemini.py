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

from puzzledesk.app.generate import default_black_ceiling
from puzzledesk.app.spec import CappedLayout, GridSpec
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


def _clustered(g, rows, cols):
    """Fraction of black cells touching another black cell (0 = spread, 1 = blobby)."""
    blk = g.block
    blacks = [(r, c) for r in range(rows) for c in range(cols) if blk[r][c]]
    if not blacks:
        return 0.0
    touch = sum(
        any(
            0 <= r + dr < rows and 0 <= c + dc < cols and blk[r + dr][c + dc]
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))
        )
        for r, c in blacks
    )
    return touch / len(blacks)


def layout_stats(container, rows, cols, max_len, n=40):
    """Black-count distribution, diversity, clustering and timing at the DEFAULT
    density (the ~22% ceiling users actually get, D25)."""
    ceiling = default_black_ceiling(rows, cols)
    print(
        f"\n=== capped layouts {rows}x{cols}, max_len={max_len}, "
        f"default <= {ceiling} black ({n} seeds) ==="
    )
    counts, times, clus, seen, bad = Counter(), [], [], set(), 0
    for seed in range(n):
        t0 = time.perf_counter()
        rng = container.rng_factory.create(seed)
        g = next(
            patterns.gen_capped(
                rows, cols, rng=rng, max_len=max_len, max_black=ceiling, node_budget=300_000
            ),
            None,
        )
        times.append(time.perf_counter() - t0)
        if g is None:
            bad += 1
            continue
        nb = sum(g.block[r][c] for r in range(rows) for c in range(cols))
        counts[nb] += 1
        clus.append(_clustered(g, rows, cols))
        seen.add(tuple(tuple(row) for row in g.block))
        assert not g.orphans and _max_run(g) <= max_len  # fully checked, capped
    med = sorted(times)[len(times) // 2] * 1e3
    cells = rows * cols
    if not counts:
        print(f"  0/{n} found within the node budget (a tight cap near the minimum -- D25)")
        return
    lo, hi = min(counts), max(counts)
    print(
        f"  {n - bad}/{n} found, {len(seen)} distinct; black {lo}..{hi} "
        f"({100 * lo // cells}-{100 * hi // cells}%), avg clustering {sum(clus) / len(clus):.2f}"
    )
    print(f"  layout search: median {med:.1f} ms, max {max(times) * 1e3:.1f} ms")


def fill_rate(container, rows, cols, max_len, bars=(50, 60, 70, 75), seeds=6):
    """Fill rate + timing from cw 2..max_len across quality bars."""
    print(f"\n=== fill rate {rows}x{cols}, max_len={max_len}, cw list ===")
    for bar in bars:
        solved, ftimes, entries = 0, [], 0
        for seed in range(seeds):
            t0 = time.perf_counter()
            res = container.generator.fill(
                GridSpec(rows=rows, cols=cols, min_score=bar, seed=seed),
                CappedLayout(max_len=max_len),
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
        res = container.generator.fill(
            GridSpec(rows=rows, cols=cols, min_score=bar, seed=seed),
            CappedLayout(max_len=max_len),
        )
        if res is not None:
            present.blocked_result(res, container.writer)
            return
    print("  (no fill in the seed budget)")


def main():
    container = build()
    motivation(container)
    # 10x10 is the target: clean ~22% density, diverse, fills 10/10.
    layout_stats(container, 10, 10, 5)
    fill_rate(container, 10, 10, 5)
    example(container, 10, 10, 5, 70)
    # 12x12 is the frontier: at the default (tight) cap the layout search is near its
    # feasibility minimum and backtracks hard, so the node budget bails most seeds --
    # loosen the cap (--max-black) or invest in smarter layout pruning (D25 scaling).
    layout_stats(container, 12, 12, 5, n=12)


if __name__ == "__main__":
    main()
