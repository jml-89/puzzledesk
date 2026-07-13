"""Sweep seeds for a capped/Gibbs grid and rank the fills by cleanliness.

The generation engines are complete/deterministic per ``(lists, seed)``, but *which*
grid a seed yields -- and how clean its fill reads -- varies. Picking a nice sample used
to mean hand-rolling a throwaway seed sweep every time; this driver is that sweep, made
reusable. For each seed it fills the requested grid and reports the **weakest word** (the
acceptance bottleneck, invariant 4 -- one weak entry fails the grid), the longest entry,
how many entries run past length 5, and the black-cell count, then prints them ranked by
weakest score (cleanest first) and echoes the winning grid.

It measures/selects; it does not emit product. Use it to find a seed, then feed that seed
to ``generate`` / a site spec. Both fill paths stay complete (capped) or budgeted (Gibbs),
so a seed that returns nothing is that engine's usual epistemics, not a bug here.

    uv run scripts/scan.py 9 9 6 60                     # cap-driven, 12 seeds, symmetric
    uv run scripts/scan.py 9 9 6 60 --gibbs --nonsym    # asymmetric Gibbs field
    uv run scripts/scan.py 7 7 6 70 --seeds 24          # widen the sweep
"""

from __future__ import annotations

import argparse

from puzzledesk.app.puzzle import filled_from_blocked
from puzzledesk.bootstrap import build
from puzzledesk.core.engines import gibbs_layout, patterns


def main() -> None:
    ap = argparse.ArgumentParser(description="Rank capped/Gibbs fills by cleanliness.")
    ap.add_argument("rows", type=int)
    ap.add_argument("cols", type=int)
    ap.add_argument("max_len", type=int, help="max entry length (raise past 5 for longer words)")
    ap.add_argument("min_score", type=int, help="quality floor (per-list scale, invariant 4)")
    ap.add_argument("--list", default="cw", help="word list family (default: cw)")
    ap.add_argument("--seeds", type=int, default=12, help="seeds to sweep (default: 12)")
    ap.add_argument("--gibbs", action="store_true", help="draw layout from the Gibbs field (D27)")
    ap.add_argument(
        "--nonsym",
        "--nonsymmetric",
        action="store_true",
        dest="nonsym",
        help="drop 180° symmetry (freeform layout)",
    )
    ap.add_argument("--max-black", type=int, default=None, help="cap-driven: bound black count")
    ap.add_argument("--black-fraction", type=float, default=0.16, help="Gibbs: target density")
    ap.add_argument("--budget", type=int, default=150_000, help="cap-driven: node budget")
    args = ap.parse_args()

    c = build()
    symmetric = not args.nonsym
    mlex = c.lexicon.load_multi(args.list, range(3, args.max_len + 1), min_score=args.min_score)
    score_maps = {
        length: c.lexicon.load(args.list, length).score_map for length in range(3, args.max_len + 1)
    }

    def score_of(word: str) -> float:
        return score_maps.get(len(word), {}).get(word, 0.0)

    rows = []
    for seed in range(args.seeds):
        if args.gibbs:
            found = gibbs_layout.fill_gibbs(
                args.rows,
                args.cols,
                mlex,
                rng_factory=c.rng_factory,
                params=gibbs_layout.FieldParams.from_fraction(
                    args.rows, args.cols, black_fraction=args.black_fraction, max_len=args.max_len
                ),
                seed=seed,
                symmetric=symmetric,
                distinct=True,
                budget=gibbs_layout.SampleBudget(max_layouts=60),
            )
        else:
            found = patterns.fill_capped(
                args.rows,
                args.cols,
                mlex,
                rng_factory=c.rng_factory,
                cap=patterns.CapSpec(
                    max_len=args.max_len, min_len=3, symmetric=symmetric, max_black=args.max_black
                ),
                seed=seed,
                distinct=True,
                budget=patterns.SearchBudget(layout_nodes=args.budget),
            )
        if found is None:
            print(f"  seed {seed:>2}: (none)")
            continue
        fg = filled_from_blocked(*found)
        entries = fg.runs()
        weak_score, weak_word = min((score_of(t.answer), t.answer) for t in entries)
        longest = max(len(t.answer) for t in entries)
        n_long = sum(1 for t in entries if len(t.answer) > 5)
        black = sum(1 for row in fg.cells for x in row if x is None)
        rows.append((weak_score, weak_word, longest, n_long, black, len(entries), seed, fg))
        print(
            f"  seed {seed:>2}: weakest {weak_word.upper()}({weak_score:.0f})  "
            f"longest={longest}  >5:{n_long}  black={black}  entries={len(entries)}"
        )

    if not rows:
        print("\nno seed filled -- loosen the floor, raise the cap, or widen --seeds")
        return

    rows.sort(key=lambda r: (-r[0], r[4]))  # cleanest (highest weakest score) first, fewer blacks
    best = rows[0]
    print(
        f"\ncleanest: seed {best[6]} (weakest {best[1].upper()} @ {best[0]:.0f}, "
        f"{best[3]} entries > 5 letters)"
    )
    for row in best[7].cells:
        print("  " + " ".join((x.upper() if x else "#") for x in row))


if __name__ == "__main__":
    main()
