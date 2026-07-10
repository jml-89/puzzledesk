"""Tool: generate blocked minis from a black-cell COUNT (not a fixed template).

    uv run scripts/generate.py [rows] [cols] [num_black] [min_score] [count] [--nonsymmetric]
    uv run generate 5 5 4 60 3
    uv run generate 5 5 3 60 3 --nonsymmetric

Searches legal layouts (fully checked, connected white cells; 180°-symmetric
unless ``--nonsymmetric``) for ones that fill with distinct words above the bar.
The layout-search property check that used to run first now lives in the pytest
suite (``tests/test_patterns.py``).

Argv is parsed with argparse -- the ``rows cols num_black min_score count`` shape is
kept positional (D20), so ``--help`` and type validation come for free without
changing the documented invocation.

With ``--max-len K`` the search switches to the *cap-driven* path
(``patterns.gen_capped``): every entry is forced to length <= K by tactically
placed black cells, so a grid larger than the word data can fill -- e.g. a 10x10
from the 2..5 lists at ``--max-len 5``:

    uv run generate 10 10 0 60 3 --max-len 5

In cap mode the black-cell count is *derived* from the cap; the ``num_black``
positional is an optional exact target (``0`` = let the search choose, defaulting to
~20% black). ``--max-black K`` bounds the count above for a specific density (D25).

Adding ``--gibbs`` (cap mode only) draws the *layout* from the Gibbs energy field
(D27) instead of the complete cap-driven search: aesthetic-controlled density and
spread and a guaranteed no-2x2-black-block texture, at the cost of speed and
completeness (a miss is budget exhaustion, never a proof). The fill is unchanged.

    uv run generate 10 10 0 60 3 --max-len 5 --gibbs
"""

from __future__ import annotations

import argparse
import sys
import time

from puzzledesk.app import blocked
from puzzledesk.bootstrap import Container, build
from puzzledesk.cli import present


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="generate",
        description="Generate blocked minis from a black-cell count (or a length cap).",
    )
    # Positional, on purpose: rows/cols/num_black/min_score/count is the historical
    # `generate 5 5 4 60 3` shape (D20 keeps mini/generate positional). argparse just
    # replaces the hand-rolled scan -- --help and type validation come for free.
    p.add_argument("rows", type=int, nargs="?", default=5, help="grid rows (default: 5)")
    p.add_argument("cols", type=int, nargs="?", default=5, help="grid columns (default: 5)")
    p.add_argument(
        "num_black",
        type=int,
        nargs="?",
        default=4,
        help="black cells to place; in --max-len mode 0 lets the search choose (default: 4)",
    )
    p.add_argument(
        "min_score",
        type=float,
        nargs="?",
        default=60.0,
        help="quality floor: every word scores >= this (default: 60)",
    )
    p.add_argument(
        "count", type=int, nargs="?", default=3, help="how many grids to emit (default: 3)"
    )
    p.add_argument(
        "--nonsymmetric",
        "--asym",
        dest="symmetric",
        action="store_false",
        help="drop the 180-degree black-cell symmetry requirement (default: symmetric)",
    )
    p.add_argument(
        "--max-len",
        type=int,
        default=None,
        metavar="K",
        help="cap every entry at length K via black cells -- the cap-driven path (D24)",
    )
    p.add_argument(
        "--max-black",
        type=int,
        default=None,
        metavar="K",
        help="upper bound on the black-cell count in --max-len mode (D25)",
    )
    p.add_argument(
        "--gibbs",
        action="store_true",
        help="draw the layout from the Gibbs energy field instead of the complete search "
        "(cap mode only; a sampler, not complete -- D27)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    if args.max_len is not None:
        _run_capped(
            build(),
            args.rows,
            args.cols,
            args.max_len,
            args.num_black,
            args.min_score,
            args.count,
            args.symmetric,
            args.max_black,
            args.gibbs,
        )
    else:
        _run(
            build(),
            args.rows,
            args.cols,
            args.num_black,
            args.min_score,
            args.count,
            args.symmetric,
        )


def _run(
    c: Container,
    rows: int,
    cols: int,
    num_black: int,
    min_score: float,
    count: int,
    symmetric: bool,
) -> None:
    w = c.writer.line
    kind = "symmetric" if symmetric else "non-symmetric"
    w()
    w(
        f"{rows}x{cols} {kind} blocked minis, {num_black} black cells, every "
        f"word score >= {min_score:.0f}"
    )
    w()

    # Structural feasibility first: does any legal layout exist at all? A property
    # of the shape + symmetry + min-length, independent of the word list.
    if not c.blocked.layout_exists(rows, cols, num_black, symmetric=symmetric):
        w(
            f"no legal {num_black}-black layout exists for a {kind} {rows}x{cols} "
            f"grid (min-length{' or symmetry' if symmetric else ''} forbids it)."
        )
        if symmetric and rows * cols % 2 == 0 and num_black % 2 == 1:
            w(
                "  a symmetric grid with an even cell count cannot take an odd "
                "black count (no centre cell to carry it) -- try --nonsymmetric."
            )
        elif symmetric and rows * cols % 2 == 1 and num_black % 2 == 1:
            w(
                "  a symmetric odd-cell grid takes an odd black count only via a "
                "centre black, which may split the middle row/column into "
                "sub-min_len runs -- try --nonsymmetric."
            )
        return

    for seed in range(count * 20):
        t0 = time.perf_counter()
        res = c.blocked.fill_once(
            rows, cols, num_black, min_score=min_score, seed=seed, symmetric=symmetric
        )
        dt = time.perf_counter() - t0
        if res is None:
            if seed == 0:  # complete search over layouts: one run settles it
                w(
                    f"legal layouts exist, but none fills at score >= {min_score:.0f} "
                    f"(searched them in {dt * 1e3:.0f} ms). Try a lower min_score."
                )
            break
        present.blocked_result(res, c.writer)
        w(f"  ({dt * 1e3:.0f} ms)")
        w()
        if seed + 1 >= count:  # shown `count` grids (a None result already broke above)
            break


def _run_capped(
    c: Container,
    rows: int,
    cols: int,
    max_len: int,
    num_black: int,
    min_score: float,
    count: int,
    symmetric: bool,
    max_black: int | None,
    gibbs: bool = False,
) -> None:
    """The cap-driven path: entries capped at ``max_len`` by black cells, so a grid
    bigger than the word data fills from the 2..5 lists. ``num_black`` (positional) > 0
    pins the count; ``0`` lets the search choose (density defaults to ~20% via
    ``--max-black``, D25). ``gibbs`` swaps the complete layout search for the Gibbs
    energy-field sampler (D27): aesthetic-controlled, but not complete."""
    w = c.writer.line
    kind = "symmetric" if symmetric else "non-symmetric"
    target = None if num_black <= 0 else num_black
    if target is not None:
        density = f", {target} black cells"
    elif max_black is not None:
        density = f", <= {max_black} black cells"
    else:
        density = f", ~{blocked.default_black_ceiling(rows, cols)} black cells (default)"
    source = " [Gibbs field]" if gibbs else ""
    w()
    w(
        f"{rows}x{cols} {kind} capped minis{source}, max entry length {max_len}{density}, "
        f"every word score >= {min_score:.0f}"
    )
    w()

    if not c.blocked.capped_layout_exists(
        rows, cols, max_len=max_len, symmetric=symmetric, num_black=target, max_black=max_black
    ):
        w(
            f"no legal length-<= {max_len} layout exists for a {kind} {rows}x{cols} grid"
            f"{density} (the cap, count bound, or symmetry forbids it)."
        )
        return

    shown = 0
    # The capped layout space is large, so budget the seeds; a miss here is
    # exhaustion of the budget, not a UNSAT theorem (unlike the count-driven path).
    # The Gibbs path is a sampler, so it is a budget for the same reason -- more so.
    for seed in range(count * 20):
        t0 = time.perf_counter()
        if gibbs:
            res = c.blocked.fill_capped_gibbs_once(
                rows,
                cols,
                max_len=max_len,
                min_score=min_score,
                seed=seed,
                symmetric=symmetric,
                num_black=target,
            )
        else:
            res = c.blocked.fill_capped_once(
                rows,
                cols,
                max_len=max_len,
                min_score=min_score,
                seed=seed,
                symmetric=symmetric,
                num_black=target,
                max_black=max_black,
            )
        dt = time.perf_counter() - t0
        if res is None:
            continue
        present.blocked_result(res, c.writer)
        w(f"  ({dt * 1e3:.0f} ms)")
        w()
        shown += 1
        if shown >= count:
            break
    if shown == 0:
        w(f"legal layouts exist, but none filled at score >= {min_score:.0f} in the seed budget.")


if __name__ == "__main__":
    main()
