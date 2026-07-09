"""The playable presenter: a clued puzzle -> plain-text solving view.

Pure string-building over a ``CluedPuzzle`` and a recording ``Writer`` (no model,
no files) -- so the exact rendered layout is a contract we can assert on. Covers the
blank numbered grid, the Across/Down clue lists (with answer lengths), the honest
``unclued`` fallback, and that :func:`solution` reveals the letters.
"""

from __future__ import annotations

from puzzledesk.app.clue import Clue
from puzzledesk.app.cluing import CluedPuzzle
from puzzledesk.app.puzzle import FilledGrid
from puzzledesk.cli import present


class _Recorder:
    """A minimal ``app.ports.Writer``: keep every line so a test can read the layout."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def line(self, text: str = "") -> None:
        self.lines.append(text)


def _grid() -> FilledGrid:
    # The QA puzzle from this branch's session:
    #   # S O B S
    #   # W H A T
    #   H E A D Y
    #   E A R L #
    #   X R A Y #
    rows = [
        [None, "s", "o", "b", "s"],
        [None, "w", "h", "a", "t"],
        ["h", "e", "a", "d", "y"],
        ["e", "a", "r", "l", None],
        ["x", "r", "a", "y", None],
    ]
    return FilledGrid(tuple(tuple(row) for row in rows))


def _clued(grid: FilledGrid) -> CluedPuzzle:
    # A stable clue per entry, keyed by the entry's answer so the assertion is legible.
    texts = {
        "sobs": "Ugly cries",
        "what": "'Come again?'",
        "heady": "Intoxicating",
        "earl": "Grey of tea fame",
        "xray": "Radiology image",
        "swear": "Vow solemnly",
        "ohara": "Scarlett of Tara",
        "badly": "Poorly",
        "sty": "Pig's pen",
        "hex": "Witch's curse",
    }
    clues = {t.id: Clue(texts[t.answer]) for t in grid.runs()}
    return CluedPuzzle(grid=grid, clues=clues, unclued=())


def test_numbering_matches_the_standard_scheme() -> None:
    numbering = _grid().numbering()
    # reading-order numbering of run-start cells (see the grid above)
    assert numbering == {
        (0, 1): 1,
        (0, 2): 2,
        (0, 3): 3,
        (0, 4): 4,
        (1, 1): 5,
        (2, 0): 6,
        (3, 0): 7,
        (4, 0): 8,
    }


def test_playable_renders_blank_grid_and_clues() -> None:
    grid = _grid()
    rec = _Recorder()
    present.playable(_clued(grid), rec)
    out = "\n".join(rec.lines)

    assert out == "\n".join(
        [
            "+--+--+--+--+--+",
            "|##|1 |2 |3 |4 |",
            "+--+--+--+--+--+",
            "|##|5 |  |  |  |",
            "+--+--+--+--+--+",
            "|6 |  |  |  |  |",
            "+--+--+--+--+--+",
            "|7 |  |  |  |##|",
            "+--+--+--+--+--+",
            "|8 |  |  |  |##|",
            "+--+--+--+--+--+",
            "",
            "Across",
            "  1. Ugly cries (4)",
            "  5. 'Come again?' (4)",
            "  6. Intoxicating (5)",
            "  7. Grey of tea fame (4)",
            "  8. Radiology image (4)",
            "",
            "Down",
            "  1. Vow solemnly (5)",
            "  2. Scarlett of Tara (5)",
            "  3. Poorly (5)",
            "  4. Pig's pen (3)",
            "  6. Witch's curse (3)",
        ]
    )


def test_playable_never_leaks_answers() -> None:
    grid = _grid()
    rec = _Recorder()
    present.playable(_clued(grid), rec)
    out = "\n".join(rec.lines).lower()
    # the blank grid + clue text carry no answer letters spelled out
    for answer in ("sobs", "heady", "swear", "ohara"):
        assert answer not in out


def test_playable_reports_unclued_entries_honestly() -> None:
    grid = _grid()
    # clue everything except the first across entry
    runs = grid.runs()
    first = runs[0]
    clues = {t.id: Clue(f"clue for {t.kind}") for t in runs if t.id != first.id}
    rec = _Recorder()
    present.playable(CluedPuzzle(grid=grid, clues=clues, unclued=(first.id,)), rec)
    assert any(present._UNCLUED in line for line in rec.lines)


def test_solution_reveals_the_letters() -> None:
    rec = _Recorder()
    present.solution(_grid(), rec)
    assert rec.lines[0] == "# S O B S"
    assert rec.lines[-1] == "X R A Y #"
