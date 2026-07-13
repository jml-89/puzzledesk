"""Gibbs field sampler vs the complete cap-driven search -- the head-to-head (D27).

docs/open-questions.md argued for a long time that the black-cell *layout* is a soft,
local field (density, spread, no 2x2 block) -- the "big-and-soft" regime D19 reserved
for a sampler's return -- while ``patterns.gen_capped``'s complete search reaches those
aesthetics only *emergently* (a white bias, a black-cell ceiling; D25). This driver
measures the claim on the axis the spike targeted: **grid aesthetics** at the sizes
that already fill (10x10, 12x12). Both produce legal, symmetric, capped layouts; the
question is which controls density/spread/texture better, at what cost.

Metrics per method (many seeds):
  * black fraction range (density control);
  * clustering -- fraction of black cells touching another black (spread; lower = better);
  * 2x2 black blocks per grid (the American-grid rule gen_capped does not enforce);
  * distinct layouts / seeds (diversity);
  * layout-search time; and fill rate from the cw 2..max_len lists.

The D28 section adds the follow-up study: **how the sampler fares as we change basin
shape (grid size) and count (black density)**, using the anneal's *reject-reason* profile
as the instrument. The headline findings:
  * the failure mode SHIFTS with basin shape -- at 10x10 the sampler mostly fails on
    connectivity, but as the grid grows (12x12) toward the jamming density the cap forces
    short-run/over-cap LEGALITY failures the field cannot cheaply escape;
  * the count knob has a FLOOR (the feasibility density the cap forces): asking below it
    yields legality rejects, not a sparser legal grid -- the jamming boundary, sampler-side;
  * the reliable lever is the soft aesthetic weights (w_cluster reshapes spread cleanly).

A connectivity **repair** (whiten a bridge black to reconnect) was built and measured here
in a D28 spike; it is DEFEATED by the cap (the separating blacks are cap-load-bearing, so
whitening re-creates an over-cap run) and fixed ~0, so it was removed -- rejection is correct
for capped minis. The lesson lives in D28; the code is one `git show` away.

Run: uv run scripts/gibbs.py
"""

import time

from puzzledesk.app.generate import default_black_ceiling
from puzzledesk.app.spec import CappedLayout, GibbsLayout, GridSpec
from puzzledesk.bootstrap import build
from puzzledesk.cli import present
from puzzledesk.core.engines import gibbs_layout, patterns
from puzzledesk.core.engines.gibbs_layout import (
    AnnealSchedule,
    FieldParams,
    anneal_field,
    reject_reason,
    sample_layout,
)


def _stats(g, rows, cols):
    """(black_fraction, clustering, n_2x2_blocks) for one layout."""
    blk = g.block
    blacks = [(r, c) for r in range(rows) for c in range(cols) if blk[r][c]]
    nb = len(blacks)
    touch = sum(
        any(
            0 <= r + dr < rows and 0 <= c + dc < cols and blk[r + dr][c + dc]
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))
        )
        for r, c in blacks
    )
    n2x2 = sum(
        1
        for r in range(rows - 1)
        for c in range(cols - 1)
        if blk[r][c] and blk[r + 1][c] and blk[r][c + 1] and blk[r + 1][c + 1]
    )
    return nb / (rows * cols), (touch / nb if nb else 0.0), n2x2


def _capped_layout(container, rows, cols, max_len, seed):
    ceiling = default_black_ceiling(rows, cols)
    return next(
        patterns.gen_capped(
            rows,
            cols,
            rng=container.rng_factory.create(seed),
            cap=patterns.CapSpec(max_len=max_len, max_black=ceiling),
            node_budget=300_000,
        ),
        None,
    )


def _gibbs_layout(container, rows, cols, max_len, seed):
    frac = default_black_ceiling(rows, cols) / (rows * cols)
    return next(
        gibbs_layout.gibbs_layouts(
            rows, cols, rng=container.rng_factory.create(seed), max_len=max_len, black_fraction=frac
        ),
        None,
    )


def compare_layouts(container, rows, cols, max_len, n=30):
    print(f"\n=== layout aesthetics {rows}x{cols}, max_len={max_len} ({n} seeds) ===")
    header = f"  {'method':<14}{'black %':<12}{'cluster':<9}{'2x2/grid':<12}"
    print(header + f"{'distinct':<11}{'median ms'}")
    for name, gen in (("gen_capped", _capped_layout), ("gibbs_field", _gibbs_layout)):
        fracs, clus, b2, times, seen, misses = [], [], [], [], set(), 0
        for seed in range(n):
            t0 = time.perf_counter()
            g = gen(container, rows, cols, max_len, seed)
            times.append(time.perf_counter() - t0)
            if g is None:
                misses += 1
                continue
            f, c, b = _stats(g, rows, cols)
            fracs.append(f)
            clus.append(c)
            b2.append(b)
            seen.add(tuple(tuple(row) for row in g.block))
        if not fracs:
            print(f"  {name:<14}(no layout in {n} seeds)")
            continue
        med = sorted(times)[len(times) // 2] * 1e3
        blackpct = f"{min(fracs) * 100:.0f}-{max(fracs) * 100:.0f}%"
        b2str = f"{sum(b2) / len(b2):.2f} (max {max(b2)})"
        note = f"  [{misses} miss]" if misses else ""
        print(
            f"  {name:<14}{blackpct:<12}{sum(clus) / len(clus):<9.2f}"
            f"{b2str:<12}{len(seen)}/{n - misses:<8}{med:>6.0f}{note}"
        )


def compare_fill(container, rows, cols, max_len, bars=(60, 70), seeds=6):
    print(f"\n=== fill rate {rows}x{cols}, max_len={max_len}, cw list ===")
    for bar in bars:
        line = f"  bar>={bar}: "
        for name, make_layout in (
            ("gen_capped", lambda ml=max_len: CappedLayout(max_len=ml)),
            ("gibbs", lambda ml=max_len: GibbsLayout(max_len=ml)),
        ):
            solved, ftimes, entries = 0, [], 0
            for seed in range(seeds):
                t0 = time.perf_counter()
                res = container.generator.fill(
                    GridSpec(rows=rows, cols=cols, min_score=bar, seed=seed), make_layout()
                )
                ftimes.append(time.perf_counter() - t0)
                if res is not None:
                    solved += 1
                    entries = len(res.across) + len(res.down)
            med = sorted(ftimes)[len(ftimes) // 2] * 1e3
            line += f"{name} {solved}/{seeds} ({entries} entries, {med:.0f} ms)   "
        print(line)


def example(container, rows, cols, max_len, bar):
    print(f"\n=== example Gibbs-field {rows}x{cols} mini, max_len={max_len}, bar>={bar} ===")
    for seed in range(20):
        res = container.generator.fill(
            GridSpec(rows=rows, cols=cols, min_score=bar, seed=seed),
            GibbsLayout(max_len=max_len),
        )
        if res is not None:
            present.blocked_result(res, container.writer)
            return
    print("  (no fill in the seed budget)")


# --- D28 study: how the sampler fares as basin shape and count change ------------


def _reason_profile(container, rows, cols, max_len, target_black, *, n, sweeps):
    """Classify n raw anneals by reject reason -- the instrument for the basin study."""
    p = FieldParams(min_len=3, max_len=max_len, target_black=target_black)
    counts = {"ok": 0, "degenerate": 0, "short_run": 0, "over_cap": 0, "disconnected": 0}
    for seed in range(n):
        grid = anneal_field(
            rows,
            cols,
            rng=container.rng_factory.create(seed),
            params=p,
            schedule=AnnealSchedule(sweeps=sweeps),
        )
        counts[reject_reason(grid, rows, cols, p)] += 1
    return counts


def reject_by_shape(container, sizes, max_len=5, frac=0.20, n=25, sweeps=90):
    """As the grid grows the failure mode shifts from connectivity to legality (the cap
    forces the field into a jam it cannot legalize) -- the basin-shape axis."""
    print(f"\n=== D28: reject-reason profile by basin shape (frac={frac}, {n} anneals) ===")
    print(f"  {'shape':<9}{'ok':<6}{'short_run':<11}{'over_cap':<10}{'disconn':<9}{'target/floor'}")
    for rows, cols in sizes:
        tb = round(frac * rows * cols)
        c = _reason_profile(container, rows, cols, max_len, tb, n=n, sweeps=sweeps)
        # the complete search's own default ceiling ~= the feasibility floor for the shape
        floor = default_black_ceiling(rows, cols)
        print(
            f"  {f'{rows}x{cols}':<9}{c['ok']:<6}{c['short_run']:<11}{c['over_cap']:<10}"
            f"{c['disconnected']:<9}{tb} / ~{floor}"
        )


def count_sweep(container, rows, cols, max_len=5, fracs=(0.14, 0.18, 0.22, 0.26), n=25, sweeps=90):
    """Sweep the count (black density) from below the feasibility floor upward: the reject
    profile tracks the jamming boundary. `ok` peaks AT the cap-forced floor -- below it
    over_cap dominates (you cannot sample a sparser-than-feasible legal grid), above it
    disconnection (over-crowding)."""
    print(f"\n=== D28: count sweep {rows}x{cols}, max_len={max_len} ({n} anneals/frac) ===")
    print(f"  {'frac':<7}{'ok%':<6}{'short_run':<11}{'over_cap':<10}{'disconn'}")
    for frac in fracs:
        tb = round(frac * rows * cols)
        c = _reason_profile(container, rows, cols, max_len, tb, n=n, sweeps=sweeps)
        okpct = f"{100 * c['ok'] // n}%"
        print(f"  {frac:<7}{okpct:<6}{c['short_run']:<11}{c['over_cap']:<10}{c['disconnected']}")


def weights_sweep(container, rows, cols, max_len=5, wclusters=(0.0, 0.55, 1.2), n=25, sweeps=90):
    """The reliable lever: the anti-cluster weight reshapes the energy basin, trading spread
    for search cost -- the soft aesthetic knob the field gives that the heuristic cannot."""
    print(f"\n=== D28: basin reshape by w_cluster {rows}x{cols} ({n} anneals) ===")
    print(f"  {'w_cluster':<11}{'yield':<9}{'black %':<11}{'cluster':<9}{'2x2/grid'}")
    tb = default_black_ceiling(rows, cols)
    for wc in wclusters:
        p = FieldParams(min_len=3, max_len=max_len, target_black=tb, w_cluster=wc)
        got, fr, clus, b2 = 0, [], [], []
        for seed in range(n):
            g = sample_layout(
                rows,
                cols,
                rng=container.rng_factory.create(seed),
                params=p,
                schedule=AnnealSchedule(sweeps=sweeps),
            )
            if g is not None:
                got += 1
                f, cl, b = _stats(g, rows, cols)
                fr.append(f)
                clus.append(cl)
                b2.append(b)
        if not fr:
            print(f"  {wc:<11}0/{n}")
            continue
        blackpct = f"{min(fr) * 100:.0f}-{max(fr) * 100:.0f}%"
        print(
            f"  {wc:<11}{got}/{n:<7}{blackpct:<11}{sum(clus) / len(clus):<9.2f}"
            f"{sum(b2) / len(b2):.2f}"
        )


def main():
    container = build()
    # D27 head-to-head (aesthetics) -- the baseline the study extends.
    compare_layouts(container, 10, 10, 5)
    compare_fill(container, 10, 10, 5)
    example(container, 10, 10, 5, 70)
    compare_layouts(container, 12, 12, 5, n=15)
    # D28 study: basin shape x count.
    reject_by_shape(container, [(10, 10), (12, 12), (14, 14)])
    count_sweep(container, 10, 10)
    count_sweep(container, 12, 12)
    weights_sweep(container, 10, 10)


if __name__ == "__main__":
    main()
