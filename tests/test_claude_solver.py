"""The Claude solver adapter's pure helpers -- prompt building and free-form parsing
(prose reasoning + a trailing JSON object). No SDK, no key, no network (the
``anthropic`` import is lazy; only the live ``messages.create`` call touches it)."""

from __future__ import annotations

from puzzledesk.adapters.claude_solver import (
    _build_prompt,
    _extract_json,
    _parse,
    _render_grid,
)
from puzzledesk.app.clue import Clue
from puzzledesk.app.cluing import CluedPuzzle
from puzzledesk.app.puzzle import FilledGrid
from puzzledesk.app.solve import Board, FeedbackPolicy, SolveState


def _view():
    grid = FilledGrid((("c", "a", "t"), ("a", "r", "e"), ("t", "e", "n")))
    texts = {"cat": "feline", "are": "exist", "ten": "a count", "art": "craft"}
    puzzle = CluedPuzzle(
        grid=grid, clues={t.id: Clue(texts[t.answer]) for t in grid.runs()}, unclued=()
    )
    return SolveState.initial(Board.of(puzzle)).view(FeedbackPolicy.CELL)


def test_render_grid_marks_black_blank_and_letters() -> None:
    grid = FilledGrid((("a", None), (None, "d")))
    puzzle = CluedPuzzle(grid=grid, clues={}, unclued=())
    view = SolveState.initial(Board.of(puzzle)).view(FeedbackPolicy.CELL)
    # nothing guessed yet: white cells are '.', black are '#'
    assert _render_grid(view) == ". #\n# ."


def test_prompt_carries_clues_but_no_answers() -> None:
    view = _view()
    prompt = _build_prompt(view)
    assert "feline" in prompt and "exist" in prompt  # clues present
    assert "Across:" in prompt and "Down:" in prompt
    for answer in ("CAT", "ARE", "TEN", "ART"):
        assert answer not in prompt  # the empty grid leaks no answer


def test_extract_json_finds_trailing_object_after_prose() -> None:
    text = (
        'I reason that 1A is CAT.\n{"placements": [{"number": 1, "direction": "A", "word": "cat"}]}'
    )
    obj = _extract_json(text)
    assert obj is not None and obj["placements"][0]["word"] == "cat"


def test_parse_prose_is_reasoning_json_is_placements() -> None:
    text = (
        "Working the crossings, 1A = CAT.\n"
        '{"placements": [{"number": 1, "direction": "A", "word": "cat"}]}'
    )
    move = _parse(text, reasoning_tokens=1234)
    assert len(move.placements) == 1
    p = move.placements[0]
    assert (p.number, p.direction, p.word) == (1, "A", "cat")
    assert move.reasoning.startswith("Working the crossings")  # prose kept as reasoning
    assert move.reasoning_tokens == 1234
    assert not move.give_up


def test_parse_drops_malformed_items_and_reads_give_up() -> None:
    text = (
        'stuck.\n{"placements": [{"number": 1, "direction": "X", "word": "no"}, '
        '{"number": "bad", "direction": "A", "word": "no"}], "give_up": true}'
    )
    move = _parse(text)
    assert move.placements == ()  # both items malformed
    assert move.give_up


def test_parse_survives_non_json() -> None:
    move = _parse("not json at all", reasoning_tokens=7)
    assert move.placements == ()
    assert move.reasoning == "not json at all"
    assert move.reasoning_tokens == 7
