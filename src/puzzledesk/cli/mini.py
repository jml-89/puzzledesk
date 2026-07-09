"""Tool: generate NYT-mini-style double word squares above a quality bar.

    uv run scripts/mini.py [N] [min_score] [count] [--max HI] [--hard K] [--gimme G]
    uv run mini 5 70 3                     # floor: every word score >= 70
    uv run mini 5 70 3 --max 85            # difficulty band: every word score in [70, 85]
    uv run mini 5 60 3 --max 90 --hard 6 --gimme 88   # a Saturday: >= 6 hard gets

Thin: parse argv, build the container, run :class:`MiniService`, present. ``--max``
turns the floor into a two-sided difficulty band (D20). ``--hard K`` *targets a
difficulty* (D22): only grids the solve-order model says need >= K hard gets (read
under clue-difficulty ``--gimme G``, default 80) are kept, returned hardest-first. That
selection is best-of-budget, not a proof -- fewer than ``count`` means "not found in
the budget", so pair a high ``--hard`` with a high ``--gimme`` and/or a bounded band.
"""

from __future__ import annotations

import sys

from ..bootstrap import build
from . import present


def _take(args: list[str], flag: str) -> tuple[list[str], str | None]:
    """Pull ``--flag VALUE`` out of ``args`` if present (returns the value or None)."""
    if flag not in args:
        return args, None
    i = args.index(flag)
    return args[:i] + args[i + 2 :], args[i + 1]


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    args, max_raw = _take(args, "--max")
    args, hard_raw = _take(args, "--hard")
    args, gimme_raw = _take(args, "--gimme")
    n = int(args[0]) if len(args) > 0 else 5
    min_score = float(args[1]) if len(args) > 1 else 70.0
    count = int(args[2]) if len(args) > 2 else 3

    container = build()
    batch = container.mini.generate(
        n,
        min_score=min_score,
        max_score=float(max_raw) if max_raw is not None else None,
        count=count,
        min_hard_gets=int(hard_raw) if hard_raw is not None else 0,
        gimme=float(gimme_raw) if gimme_raw is not None else 80.0,
    )
    present.mini_batch(batch, container.writer)


if __name__ == "__main__":
    main()
