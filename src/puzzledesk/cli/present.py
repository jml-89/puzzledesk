"""Presenters: turn service results into lines on a ``Writer``.

The formatting that used to live in each script's ``render``/``show`` function,
gathered in one place and driven by the structured results the services return.
Pure string-building plus ``writer.line`` calls -- no generation, no numpy.
"""

from __future__ import annotations

from ..app.ports import Writer
from ..app.results import BlockedResult, MiniBatch, MiniResult


def mini_batch(batch: MiniBatch, writer: Writer) -> None:
    """Render a batch of minis exactly as ``scripts/mini.py`` did."""
    bar = (
        f">= {batch.min_score:.0f}"
        if batch.max_score is None
        else f"in [{batch.min_score:.0f}, {batch.max_score:.0f}]"
    )
    writer.line(
        f"{batch.n}x{batch.n} minis, every word score {bar} (from {batch.eligible} eligible words)"
    )
    writer.line()
    if not batch.results:
        writer.line("no grid at this bar (try a lower min_score)")
        return
    for r in batch.results:
        _mini(r, writer)


def _mini(r: MiniResult, writer: Writer) -> None:
    for a in r.across:
        writer.line("  " + " ".join(ch.upper() for ch in a.word))
    writer.line("  across: " + ", ".join(f"{a.word}({a.score:.0f})" for a in r.across))
    writer.line("  down:   " + ", ".join(f"{d.word}({d.score:.0f})" for d in r.down))
    writer.line(f"  weakest word: {r.weakest.word} ({r.weakest.score:.0f})")
    writer.line()


def blocked_result(res: BlockedResult, writer: Writer) -> None:
    """Render a filled blocked grid: the letter grid, then the across/down entries
    with scores -- the shared format of ``blackcells.py`` and ``generate.py``."""
    writer.line(res.grid)
    across = "  ".join(f"{e.number}A {e.word}({e.score:.0f})" for e in res.across)
    down = "  ".join(f"{e.number}D {e.word}({e.score:.0f})" for e in res.down)
    writer.line(f"  across: {across}")
    writer.line(f"  down:   {down}")
