"""Tool: generate blocked minis from a black-cell COUNT (not a fixed template).

    uv run scripts/generate.py [rows] [cols] [num_black] [min_score] [count] [--nonsymmetric]
    uv run generate 5 5 4 60 3
    uv run generate 5 5 3 60 3 --nonsymmetric

Searches legal layouts (fully checked, connected white cells; 180°-symmetric
unless ``--nonsymmetric``) for ones that fill with distinct words above the bar.
The layout-search property check that used to run first now lives in the pytest
suite (``tests/test_patterns.py``).

With ``--max-len K`` the search switches to the *cap-driven* path
(``patterns.gen_capped``): every entry is forced to length <= K by tactically
placed black cells, so a grid larger than the word data can fill -- e.g. a 10x10
from the 2..5 lists at ``--max-len 5``:

    uv run generate 10 10 0 60 3 --max-len 5

In cap mode the black-cell count is *derived* from the cap; the ``num_black``
positional is an optional target (``0`` = let the search choose).
"""

from __future__ import annotations

import sys
import time

from ..bootstrap import Container, build
from . import present


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    symmetric = True
    max_len: int | None = None
    positional: list[str] = []
    it = iter(args)
    for a in it:
        if a in ("--nonsymmetric", "--asym"):
            symmetric = False
        elif a == "--max-len":
            max_len = int(next(it))
        else:
            positional.append(a)
    rows = int(positional[0]) if len(positional) > 0 else 5
    cols = int(positional[1]) if len(positional) > 1 else 5
    num_black = int(positional[2]) if len(positional) > 2 else 4
    min_score = float(positional[3]) if len(positional) > 3 else 60.0
    count = int(positional[4]) if len(positional) > 4 else 3

    if max_len is not None:
        _run_capped(build(), rows, cols, max_len, num_black, min_score, count, symmetric)
    else:
        _run(build(), rows, cols, num_black, min_score, count, symmetric)


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
) -> None:
    """The cap-driven path: entries capped at ``max_len`` by black cells, so a grid
    bigger than the word data fills from the 2..5 lists."""
    w = c.writer.line
    kind = "symmetric" if symmetric else "non-symmetric"
    target = None if num_black <= 0 else num_black
    tgt = "" if target is None else f", {target} black cells"
    w()
    w(
        f"{rows}x{cols} {kind} capped minis, max entry length {max_len}{tgt}, "
        f"every word score >= {min_score:.0f}"
    )
    w()

    if not c.blocked.capped_layout_exists(
        rows, cols, max_len=max_len, symmetric=symmetric, num_black=target
    ):
        w(
            f"no legal length-<= {max_len} layout exists for a {kind} {rows}x{cols} grid"
            f"{tgt} (the cap or symmetry forbids it)."
        )
        return

    shown = 0
    # The capped layout space is large, so budget the seeds; a miss here is
    # exhaustion of the budget, not a UNSAT theorem (unlike the count-driven path).
    for seed in range(count * 20):
        t0 = time.perf_counter()
        res = c.blocked.fill_capped_once(
            rows,
            cols,
            max_len=max_len,
            min_score=min_score,
            seed=seed,
            symmetric=symmetric,
            num_black=target,
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
