"""Mint "one-spine wonders" -- the keeper Latent shape (docs/relational-difficulty.md,
"Scaling Latent"): a low-density 9x9 built around a single long across **spine** that carries
no clue and is *deduced* from its crossings.

This is the generator behind `site/build_latent_long.py`. Where `scan.py` ranks generic
capped/Gibbs fills by their weakest word, this ranks fills of the fixed staggered-spine layout by
the qualities that make the shape sing:

  * the spine is *deduced*, not clued (the unclued destination -- else it's a wasted long word);
  * the fill is clean (high weakest-word score -- invariant 4, the acceptance bottleneck), which is
    the primary ranking;
  * the cascade is fair (`minvis >= 3` -- no word pinned by fewer than three letters).

The search uses the fast `gravity_floor` (clue-shorts / deduce-longs) to confirm the spine is
deducible; the shipped page (`site/build_latent_long.py`) re-derives the exhaustive *min-count*
floor, which makes the spine's own deduction harder (the vis-6 "watch a whole word appear" moment).
Pick a seed off the ranked list, drop it into `build_latent_long.py` (SEED + hand clues, or wire the
`clue` extra), and you have a new one. The clues are the only manual step.

    uv run scripts/spine.py                 # rank 9-spine fills, cw >= 62, 400 seeds
    uv run scripts/spine.py 66 800 12       # min-score, seeds, how many to show
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from puzzledesk.app.puzzle import filled_from_blocked
from puzzledesk.bootstrap import build
from puzzledesk.core.blocked import BlockedGrid
from puzzledesk.core.engines import fill
from relational import _entries, gravity_floor

# The keeper layout: one 9-across spine (row 4), staggered 5-letter crossers, 180-symmetric.
SPINE_9 = [
    "....#####", "....#####", ".....####", ".....####", ".........",
    "####.....", "####.....", "#####....", "#####....",
]
SPINE_LEN = 9


def cascade(entries, clued, n_candidates):
    """Replay the forced solve; return per clueless entry (entry, wave, vis_at_force)."""
    known: set = set()
    solved: set = set()
    order: list = []
    wave = 0

    def forced(e):
        idx = frozenset(i for i, c in enumerate(e.cells) if c in known)
        return e.eid in clued or n_candidates(e.answer, idx) == 1

    while len(solved) < len(entries):
        wave += 1
        newly = [e for e in entries if e.eid not in solved and forced(e)]
        if not newly:
            return None
        for e in newly:
            if e.eid not in clued:
                order.append((e, wave, sum(1 for c in e.cells if c in known)))
        for e in newly:
            solved.add(e.eid)
            known.update(e.cells)
    return order


def rank(container, bar=62.0, seeds=400, show=8):
    g = BlockedGrid.parse(SPINE_9, min_len=3)
    assert not g.orphans, g.orphans
    maxlen = max(s.length for s in g.slots)
    full = container.lexicon.load_multi("cw", range(3, maxlen + 1))
    gen = container.lexicon.load_multi("cw", range(3, maxlen + 1), min_score=bar)
    smap = {length: full.get(length).score_map for length in range(3, maxlen + 1)}
    score = lambda w: smap[len(w)].get(w.lower(), 0.0)  # noqa: E731
    nc = lambda a, k: full.get(len(a)).n_candidates(a, k)  # noqa: E731

    print(f"=== one-spine wonders: {g.rows}x{g.cols}, {SPINE_LEN}-spine, "
          f"cw >= {bar:g}, {seeds} seeds ===")
    cands, seen = [], set()
    for seed in range(seeds):
        rng = container.rng_factory.create(seed)
        assign = fill.solve(g, gen, rng=rng, distinct=True, node_budget=200000)
        if assign is None:
            continue
        grid = filled_from_blocked(g, assign)
        entries = _entries(grid)
        key = tuple(sorted(e.answer for e in entries))
        if key in seen:
            continue
        seen.add(key)
        clued, depth = gravity_floor(entries, nc)  # greedy + deduces the longest first (fast)
        spine = next(e for e in entries if len(e.cells) == SPINE_LEN)
        if spine.eid in clued:  # spine must be the unclued destination
            continue
        casc = cascade(entries, clued, nc)
        if casc is None:
            continue
        minvis = min(v for _, _, v in casc)
        if minvis < 3:
            continue
        spine_score = score(spine.answer.upper())
        weakest = min(score(e.answer.upper()) for e in entries)
        cands.append((weakest, depth, seed, grid, entries, clued, spine, spine_score, minvis))
    cands.sort(key=lambda c: (c[0], c[1]), reverse=True)  # cleanest fill first, then deepest

    for weakest, depth, seed, grid, entries, clued, spine, spine_score, minvis in cands[:show]:
        lab = {e.eid: e.label for e in entries}
        rows = ["".join((grid.cells[r][col] or "#").upper() for col in range(grid.cols))
                for r in range(grid.rows)]
        print(f"\n  seed {seed}  weakest-word {weakest:.0f}  "
              f"spine {spine.label}={spine.answer.upper()} (cw {spine_score:.0f}, deduced)  "
              f"floor {len(clued)}/{len(entries)}  depth {depth}  minvis {minvis}")
        print("   " + "\n   ".join(rows))
        print("   clue (given, gravity floor): " + ", ".join(sorted(lab[i] for i in clued)))
        print("   words: " + " ".join(e.answer.upper() for e in entries))
    if not cands:
        print("  (no spine-deduced fill at this bar -- lower it or raise the seed count)")
    else:
        print(f"\n  {len(cands)} spine-deduced candidates; showing {min(show, len(cands))}, "
              f"cleanest first.\n  Pick a seed -> site/build_latent_long.py (set SEED + clues; it "
              f"re-derives the harder min-count floor).")


def main() -> None:
    args = sys.argv[1:]
    bar = float(args[0]) if len(args) > 0 else 62.0
    seeds = int(args[1]) if len(args) > 1 else 400
    show = int(args[2]) if len(args) > 2 else 8
    rank(build(), bar=bar, seeds=seeds, show=show)


if __name__ == "__main__":
    main()
