"""The Claude adapter's pure helpers -- prompt building and response parsing.

These need no SDK, no key, no network (the ``anthropic`` import is lazy and only
the live ``messages.create`` call touches it), so the logic that turns a grid into
a prompt and a JSON response back into clues is unit-tested here.
"""

from __future__ import annotations

from puzzledesk.adapters.claude_clue import _build_prompt, _parse, _render_grid
from puzzledesk.app.clue import Clue, ClueStyle, Difficulty
from puzzledesk.app.puzzle import FilledGrid


def test_render_grid_uppercases_and_marks_black() -> None:
    grid = FilledGrid((("a", "b"), ("c", None)))
    assert _render_grid(grid) == "A B\nC #"


def test_prompt_carries_answers_difficulty_and_instructions() -> None:
    grid = FilledGrid((("a", "b"), ("c", "d")))
    targets = grid.runs()
    prompt = _build_prompt(
        grid, targets, ClueStyle(difficulty=Difficulty.FRIDAY, instructions="British spellings"), 2
    )
    assert "Friday" in prompt
    assert "British spellings" in prompt
    for t in targets:
        assert t.answer.upper() in prompt


def test_prompt_difficulty_controls_obliqueness() -> None:
    # the Mon..Sat label must actually shape the clue: Monday = direct, Saturday = oblique
    # and crossing-reliant (the D26 lever).
    grid = FilledGrid((("a", "b"), ("c", "d")))
    targets = grid.runs()
    monday = _build_prompt(grid, targets, ClueStyle(difficulty=Difficulty.MONDAY), 1)
    saturday = _build_prompt(grid, targets, ClueStyle(difficulty=Difficulty.SATURDAY), 1)
    assert "direct" in monday.lower() and "no wordplay" in monday.lower()
    assert "oblique" in saturday.lower() and "misdirection" in saturday.lower()
    assert "crossing" in saturday.lower()  # Saturday tells the writer to lean on crossings


def test_parse_maps_indices_back_to_targets() -> None:
    grid = FilledGrid((("a", "b"), ("c", "d")))
    targets = grid.runs()
    text = (
        '{"clues": [{"index": 0, "candidates": ["c1", "c2"]}, {"index": 1, "candidates": ["d1"]}]}'
    )
    parsed = _parse(text, targets)
    assert parsed[targets[0].id] == (Clue("c1"), Clue("c2"))
    assert parsed[targets[1].id] == (Clue("d1"),)


def test_parse_ignores_out_of_range_indices() -> None:
    grid = FilledGrid((("a", "b"),))
    targets = grid.runs()  # one across target
    text = '{"clues": [{"index": 0, "candidates": ["ok"]}, {"index": 99, "candidates": ["nope"]}]}'
    parsed = _parse(text, targets)
    assert set(parsed) == {targets[0].id}
