"""Tool: generate NYT-mini-style double word squares above a quality bar.

    uv run scripts/mini.py [N] [min_score] [count]
    uv run mini 5 70 3

Thin: parse argv, build the container, run :class:`MiniService`, present. Every
emitted grid is distinct with every word >= the bar (by construction of the
service).
"""

from __future__ import annotations

import sys

from ..bootstrap import build
from . import present


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    n = int(args[0]) if len(args) > 0 else 5
    min_score = float(args[1]) if len(args) > 1 else 70.0
    count = int(args[2]) if len(args) > 2 else 3

    container = build()
    batch = container.mini.generate(n, min_score=min_score, count=count)
    present.mini_batch(batch, container.writer)


if __name__ == "__main__":
    main()
