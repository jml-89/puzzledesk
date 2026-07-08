"""The Claude adapter's pure helpers -- prompt building and response parsing.

These need no SDK, no key, no network (the ``anthropic`` import is lazy and only
the live ``messages.create`` call touches it), so the logic that turns a grid into
a prompt and a JSON response back into clues is unit-tested here.
"""

from __future__ import annotations

import pytest

from puzzledesk.adapters.claude_clue import _build_prompt, _parse, _render_grid, _resolve_key
from puzzledesk.app.clue import Clue, ClueStyle, Difficulty
from puzzledesk.app.puzzle import FilledGrid
from puzzledesk.bootstrap.config import Config


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


def test_resolve_key_reads_the_configured_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOME_OFF_NORMAL_KEY", "sk-live-123")
    assert _resolve_key("SOME_OFF_NORMAL_KEY") == "sk-live-123"


def test_resolve_key_defers_to_the_sdk_when_var_absent_or_unnamed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # a name that resolves to nothing -> None (defer to SDK), never an empty key
    monkeypatch.delenv("MISSING_KEY", raising=False)
    assert _resolve_key("MISSING_KEY") is None
    monkeypatch.setenv("BLANK_KEY", "")
    assert _resolve_key("BLANK_KEY") is None
    # no env name configured at all -> None
    assert _resolve_key(None) is None


def test_config_default_names_the_off_normal_key_env() -> None:
    # the knob the composition root threads into the adapter (docs/decisions.md D17)
    assert Config.default().clue_api_key_env == "ANTHROPIC_API_KEY_TWO"
