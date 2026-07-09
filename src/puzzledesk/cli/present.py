"""Presenters: turn service results into lines on a ``Writer``.

The formatting that used to live in each script's ``render``/``show`` function,
gathered in one place and driven by the structured results the services return.
Pure string-building plus ``writer.line`` calls -- no generation, no numpy.
"""

from __future__ import annotations

from ..app.cluing import CluedPuzzle
from ..app.ports import Writer
from ..app.puzzle import FilledGrid
from ..app.results import BlockedResult, MiniBatch, MiniResult
from ..app.solve import SolveView
from ..app.solve_service import SolveReport, SolveTurn


def mini_batch(batch: MiniBatch, writer: Writer) -> None:
    """Render a batch of minis exactly as ``scripts/mini.py`` did."""
    bar = (
        f">= {batch.min_score:.0f}"
        if batch.max_score is None
        else f"in [{batch.min_score:.0f}, {batch.max_score:.0f}]"
    )
    target = (
        f", targeting >= {batch.min_hard_gets} hard gets (gimme {batch.gimme:.0f})"
        if batch.min_hard_gets > 0
        else ""
    )
    writer.line(
        f"{batch.n}x{batch.n} minis, every word score {bar} "
        f"(from {batch.eligible} eligible words){target}"
    )
    writer.line()
    if not batch.results:
        writer.line(
            "no grid met the difficulty target in the seed budget "
            "(try a higher gimme or an obscurer band)"
            if batch.min_hard_gets > 0
            else "no grid at this bar (try a lower min_score)"
        )
        return
    for r in batch.results:
        _mini(r, writer)


def _mini(r: MiniResult, writer: Writer) -> None:
    for a in r.across:
        writer.line("  " + " ".join(ch.upper() for ch in a.word))
    writer.line("  across: " + ", ".join(f"{a.word}({a.score:.0f})" for a in r.across))
    writer.line("  down:   " + ", ".join(f"{d.word}({d.score:.0f})" for d in r.down))
    writer.line(f"  weakest word: {r.weakest.word} ({r.weakest.score:.0f})")
    if r.difficulty is not None:
        d = r.difficulty
        bn = (
            f"; bottleneck {d.bottleneck_word} ({d.bottleneck_fits} fits)"
            if d.bottleneck_word
            else ""
        )
        writer.line(f"  difficulty: {d.hard_gets} hard gets under gimme {d.gimme:.0f}{bn}")
    writer.line()


def blocked_result(res: BlockedResult, writer: Writer) -> None:
    """Render a filled blocked grid: the letter grid, then the across/down entries
    with scores -- the shared format of ``blackcells.py`` and ``generate.py``."""
    writer.line(res.grid)
    across = "  ".join(f"{e.number}A {e.word}({e.score:.0f})" for e in res.across)
    down = "  ".join(f"{e.number}D {e.word}({e.score:.0f})" for e in res.down)
    writer.line(f"  across: {across}")
    writer.line(f"  down:   {down}")


# --- Playable puzzle: the solver-facing plain-text view --------------------------
#
# The presenter the QA round wanted: a blank numbered grid plus numbered clue lists,
# i.e. a puzzle you can *solve* rather than the answer key the other presenters emit.
# Pure ASCII (``+ - | #`` and digits) so it renders identically in any terminal or
# pasted into any text box; box-drawing glyphs are deliberately avoided. All the
# structure -- numbering, entry lengths, across/down split -- is derived from the
# grid geometry (``FilledGrid``), never stored (D15).

_UNCLUED = "[no clue available]"


def playable(puzzle: CluedPuzzle, writer: Writer) -> None:
    """Render a clued puzzle for solving: the blank numbered grid, then the Across
    and Down clue lists. Answers are never shown -- use :func:`solution` for those."""
    grid = puzzle.grid
    numbering = grid.numbering()
    for line in _grid_lines(grid, numbering):
        writer.line(line)
    writer.line()
    _clue_block("Across", "A", puzzle, numbering, writer)
    writer.line()
    _clue_block("Down", "D", puzzle, numbering, writer)


def solution(grid: FilledGrid, writer: Writer) -> None:
    """Render the answer key: the filled letter grid (uppercase, ``#`` for black).
    The reveal companion to :func:`playable`, for QA and for ``--reveal``."""
    for row in grid.cells:
        writer.line(" ".join(cell.upper() if cell is not None else "#" for cell in row))


def _grid_lines(grid: FilledGrid, numbering: dict[tuple[int, int], int]) -> list[str]:
    """The blank grid as ASCII box rows: black cells filled with ``#``, white cells
    blank but carrying their clue number (if any) in the corner. Cell width grows to
    fit the largest number, so bigger grids stay aligned."""
    width = max(2, len(str(max(numbering.values(), default=0))))
    border = "+" + "+".join("-" * width for _ in range(grid.cols)) + "+"
    lines = [border]
    for r in range(grid.rows):
        cells = []
        for c in range(grid.cols):
            if grid.cells[r][c] is None:
                cells.append("#" * width)
            elif (n := numbering.get((r, c))) is not None:
                cells.append(str(n).ljust(width))
            else:
                cells.append(" " * width)
        lines.append("|" + "|".join(cells) + "|")
        lines.append(border)
    return lines


# --- Solve transcript: the agent's attempt, for inspecting its thinking -----------
#
# The difficulty artifact of the solving spike (D24). Renders whether the agent
# completed the grid, how many turns it took, and -- the point -- the per-turn
# reasoning it worked through. A budget miss is reported honestly as "not solved in N
# turns", never as a proof of unsolvability.


def board(view: SolveView, writer: Writer) -> None:
    """Render the current solve board: the grid with the solver's letters filled in
    (blank white cells as ``.``), black cells as ``#``."""
    grid = view.letter_grid()
    for row in grid:
        writer.line(" ".join("#" if ch is None else (ch.upper() if ch else ".") for ch in row))


def solve_report(report: SolveReport, writer: Writer) -> None:
    """Render a whole solve attempt: the outcome, then each turn's reasoning, moves,
    and feedback, then the final board."""
    if report.solved:
        outcome = f"SOLVED in {report.n_turns} turn(s)"
    elif report.gave_up:
        outcome = f"gave up after {report.n_turns} turn(s)"
    else:
        # Honest epistemics: a budget miss is not a proof (cf. D23). Never "impossible".
        outcome = (
            f"not solved in the {report.max_turns}-turn budget "
            "(budget exhausted -- not a proof the puzzle is unsolvable)"
        )
    writer.line(f"Solver result: {outcome}, policy={report.policy.value}")
    writer.line(f"Wrong guesses along the way: {report.wrong_guesses}")
    writer.line()
    for turn in report.turns:
        _solve_turn(turn, writer)
    writer.line("Final board:")
    board(report.final.view(report.policy), writer)


def _solve_turn(turn: SolveTurn, writer: Writer) -> None:
    writer.line(f"--- Turn {turn.index + 1} ---")
    if turn.reasoning.strip():
        writer.line("Reasoning:")
        for line in turn.reasoning.splitlines():
            writer.line(f"  {line}")
    moves = ", ".join(
        f"{p.number}{p.direction}={p.word.upper() or '(erase)'}" for p in turn.applied
    )
    writer.line(f"Played: {moves or '(nothing)'}")
    if turn.rejected:
        bad = ", ".join(f"{p.number}{p.direction}={p.word.upper()}" for p in turn.rejected)
        writer.line(f"Rejected (bad ref/length): {bad}")
    if turn.gave_up:
        writer.line("Agent gave up.")
    writer.line(f"Feedback: {_feedback_line(turn)}")
    writer.line()


def _feedback_line(turn: SolveTurn) -> str:
    fb = turn.feedback
    if fb.solved:
        return "solved!"
    bits = []
    if fb.correct_cells:
        bits.append(f"{len(fb.correct_cells)} cell(s) correct")
    if fb.wrong_cells:
        bits.append(f"{len(fb.wrong_cells)} cell(s) wrong")
    if fb.correct_entries:
        bits.append(f"{len(fb.correct_entries)} entry(ies) correct")
    if fb.wrong_entries:
        bits.append(f"{len(fb.wrong_entries)} entry(ies) wrong")
    if fb.conflicts:
        bits.append(f"conflicts at {sorted(fb.conflicts)}")
    return ", ".join(bits) if bits else "(no check under this policy)"


def _clue_block(
    title: str,
    kind: str,
    puzzle: CluedPuzzle,
    numbering: dict[tuple[int, int], int],
    writer: Writer,
) -> None:
    """One clue list ("Across"/"Down"): numbered entries in grid order, each with its
    clue text and answer length -- ``(no clue found)`` reported honestly if unclued."""
    writer.line(title)
    entries = sorted(
        (t for t in puzzle.grid.runs() if t.kind == kind),
        key=lambda t: numbering[t.cells[0]],
    )
    for t in entries:
        clue = puzzle.clues.get(t.id)
        text = clue.text if clue is not None else _UNCLUED
        writer.line(f"  {numbering[t.cells[0]]}. {text} ({len(t.cells)})")
