"""The deterministic solve session: state, derivation, feedback policies, integrity.

Pure -- no model, no files. Covers the answer-key quarantine (a view never leaks an
unguessed answer), the per-entry guess model and its derived crossing *conflicts* (a
signal that needs no key), and each :class:`FeedbackPolicy`'s reveal.
"""

from __future__ import annotations

from puzzledesk.app.clue import Clue
from puzzledesk.app.cluing import CluedPuzzle
from puzzledesk.app.puzzle import FilledGrid
from puzzledesk.app.solve import Board, FeedbackPolicy, SolveState


def _clued(grid: FilledGrid, texts: dict[str, str]) -> CluedPuzzle:
    clues = {t.id: Clue(texts[t.answer]) for t in grid.runs()}
    return CluedPuzzle(grid=grid, clues=clues, unclued=())


def _grid2x2() -> FilledGrid:
    # across: 1A=ab, 3A=cd ; down: 1D=ac, 2D=bd
    return FilledGrid((("a", "b"), ("c", "d")))


def _clued2x2() -> CluedPuzzle:
    return _clued(
        _grid2x2(),
        {"ab": "one-two", "cd": "three-four", "ac": "one-three", "bd": "two-four"},
    )


def test_board_maps_refs_answers_and_clues() -> None:
    board = Board.of(_clued2x2())
    refs = {e.ref: e.answer for e in board.entries}
    assert refs == {(1, "A"): "ab", (3, "A"): "cd", (1, "D"): "ac", (2, "D"): "bd"}
    assert board.length_of((1, "A")) == 2
    assert board.length_of((9, "A")) is None  # unknown ref


def test_cell_derivation_and_crossing_conflict_needs_no_key() -> None:
    board = Board.of(_clued2x2())
    state = SolveState.initial(board)
    # agree at (0,0): 1A=ab and 1D=ac both put 'a' there
    ok = state.with_guess((1, "A"), "ab").with_guess((1, "D"), "ac")
    letters, conflicts = ok.cell_letters()
    assert letters[(0, 0)] == "a"
    assert conflicts == set()
    # disagree at (0,0): 1D=xc wants 'x' where 1A=ab wants 'a'
    clash = state.with_guess((1, "A"), "ab").with_guess((1, "D"), "xc")
    _, conflicts = clash.cell_letters()
    assert (0, 0) in conflicts


def test_feedback_cell_marks_own_letters_only() -> None:
    board = Board.of(_clued2x2())
    state = SolveState.initial(board).with_guess((1, "A"), "az")  # a correct, z wrong
    fb = state.feedback(FeedbackPolicy.CELL)
    assert (0, 0) in fb.correct_cells
    assert (0, 1) in fb.wrong_cells
    assert not fb.solved


def test_feedback_word_flags_whole_entries() -> None:
    board = Board.of(_clued2x2())
    state = SolveState.initial(board).with_guess((1, "A"), "ab").with_guess((3, "A"), "zz")
    fb = state.feedback(FeedbackPolicy.WORD)
    assert (1, "A") in fb.correct_entries
    assert (3, "A") in fb.wrong_entries


def test_feedback_crossing_reports_conflicts_only() -> None:
    board = Board.of(_clued2x2())
    state = SolveState.initial(board).with_guess((1, "A"), "ab").with_guess((1, "D"), "xc")
    fb = state.feedback(FeedbackPolicy.CROSSING)
    assert (0, 0) in fb.conflicts
    assert fb.correct_cells == () and fb.wrong_cells == ()


def test_feedback_none_reveals_only_solved() -> None:
    board = Board.of(_clued2x2())
    state = SolveState.initial(board).with_guess((1, "A"), "ab")
    fb = state.feedback(FeedbackPolicy.NONE)
    assert fb.correct_cells == () and fb.wrong_cells == () and fb.conflicts == ()
    assert fb.solved is False


def test_is_solved_only_when_all_entries_correct() -> None:
    board = Board.of(_clued2x2())
    state = SolveState.initial(board)
    for ref, word in [((1, "A"), "ab"), ((3, "A"), "cd"), ((1, "D"), "ac"), ((2, "D"), "bd")]:
        state = state.with_guess(ref, word)
    assert state.is_solved()
    assert state.feedback(FeedbackPolicy.NONE).solved


def test_view_never_leaks_unguessed_answers() -> None:
    # A distinctive 3x3 so answer substrings are unambiguous.
    grid = FilledGrid((("c", "a", "t"), ("a", "r", "e"), ("t", "e", "n")))
    puzzle = _clued(
        grid,
        {"cat": "feline", "are": "exist", "ten": "a count", "art": "craft"},
    )
    view = SolveState.initial(Board.of(puzzle)).view(FeedbackPolicy.CELL)
    # every cell blank, every entry pattern all-underscores
    assert all(ch == "" for row in view.letter_grid() for ch in row if ch is not None)
    for e in (*view.across, *view.down):
        assert set(e.pattern) == {"_"}
    # clues are present, but no answer letters are spelled anywhere in the view's entries
    joined = " ".join(e.clue for e in (*view.across, *view.down))
    for answer in ("cat", "are", "ten", "art"):
        assert answer not in joined
