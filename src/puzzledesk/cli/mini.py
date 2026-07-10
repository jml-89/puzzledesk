"""Tool: generate NYT-mini-style double word squares above a quality bar.

    uv run scripts/mini.py [N] [min_score] [count] [--max HI] [--hard K] [--gimme G]
    uv run mini 5 70 3                     # floor: every word score >= 70
    uv run mini 5 70 3 --max 85            # difficulty band: every word score in [70, 85]
    uv run mini 5 60 3 --max 90 --hard 6 --gimme 88   # a Saturday: >= 6 hard gets

Thin: parse argv (argparse -- positional ``N min_score count`` plus named flags, so
``--help`` and type validation come free), build the container, run
:class:`MiniService`, present. ``--max``
turns the floor into a two-sided difficulty band (D21). ``--hard K`` *targets a
difficulty* (D23): only grids the solve-order model says need >= K hard gets (read
under clue-difficulty ``--gimme G``, default 80) are kept, returned hardest-first. That
selection is best-of-budget, not a proof -- fewer than ``count`` means "not found in
the budget", so pair a high ``--hard`` with a high ``--gimme`` and/or a bounded band.
"""

from __future__ import annotations

import argparse
import sys

from puzzledesk.app.spec import FillSpec, GridSpec
from puzzledesk.bootstrap import build
from puzzledesk.cli import present


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="mini",
        description="Generate NYT-mini-style double word squares above a quality bar.",
    )
    # Positional, on purpose: N/min_score/count are the historical `mini 5 70 3` shape
    # (D20 keeps mini/generate positional). argparse just replaces the hand-rolled
    # parse -- it gains --help and type validation without changing the invocation.
    p.add_argument("n", type=int, nargs="?", default=5, help="word-square size N (default: 5)")
    p.add_argument(
        "min_score",
        type=float,
        nargs="?",
        default=70.0,
        help="quality floor: every word scores >= this (default: 70)",
    )
    p.add_argument(
        "count", type=int, nargs="?", default=3, help="how many grids to emit (default: 3)"
    )
    p.add_argument(
        "--max",
        type=float,
        default=None,
        metavar="SCORE",
        dest="max_score",
        help="upper bar: turns the floor into a difficulty band [min, max] (default: none)",
    )
    p.add_argument(
        "--hard",
        type=int,
        default=0,
        metavar="K",
        dest="min_hard_gets",
        help="target difficulty: keep only grids needing >= K hard gets, hardest-first "
        "(default: 0, off)",
    )
    p.add_argument(
        "--gimme",
        type=float,
        default=80.0,
        metavar="G",
        help="clue-difficulty read used by --hard: a word is a hard get below G (default: 80)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    container = build()
    grid = GridSpec(rows=args.n, cols=args.n, min_score=args.min_score, max_score=args.max_score)
    sel = FillSpec(min_hard_gets=args.min_hard_gets, gimme=args.gimme)
    batch = container.mini.generate(grid, sel, count=args.count)
    present.mini_batch(batch, container.writer)


if __name__ == "__main__":
    main()
