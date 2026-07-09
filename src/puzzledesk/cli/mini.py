"""Tool: generate NYT-mini-style double word squares above a quality bar.

    uv run scripts/mini.py [N] [min_score] [count] [--max HI]
    uv run mini 5 70 3            # floor: every word score >= 70
    uv run mini 5 70 3 --max 85   # difficulty band: every word score in [70, 85]

Thin: parse argv, build the container, run :class:`MiniService`, present. Every
emitted grid is distinct with every word in the band (by construction of the
service). ``--max`` turns the floor into a two-sided difficulty band (D20): a bounded
band draws from the obscure end rather than merely lowering the floor.
"""

from __future__ import annotations

import sys

from ..bootstrap import build
from . import present


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    max_score: float | None = None
    if "--max" in args:
        i = args.index("--max")
        max_score = float(args[i + 1])
        args = args[:i] + args[i + 2 :]
    n = int(args[0]) if len(args) > 0 else 5
    min_score = float(args[1]) if len(args) > 1 else 70.0
    count = int(args[2]) if len(args) > 2 else 3

    container = build()
    batch = container.mini.generate(n, min_score=min_score, max_score=max_score, count=count)
    present.mini_batch(batch, container.writer)


if __name__ == "__main__":
    main()
