"""The Claude solver adapter -- the real (soft, generative) implementation of the
``app.solver.SolverAgent`` port.

This is the *second* LLM consumer D16 anticipated ("a second consumer would justify a
minimal, our-own seam... and only then"). We hold the line D16 drew: the LLM does not
become an app-layer port. The app depends on ``SolverAgent`` (which speaks views and
moves); the SDK, the credential, and the extended-thinking capture all live *here*,
one layer down -- exactly where ``ClaudeClueProvider`` sits. A shared ``LanguageModel``
seam between the two adapters is a reasonable next refactor, but two direct SDK callers
is not yet enough duplication to force it (D24 records the call).

The agent is prompted afresh each turn with the whole answer-free view (the port is
stateless by design -- see ``app/solver.py``), asked to reason and then emit its
placements. Reasoning capture is the point of the spike, so it is made **robust to how
the model surfaces thinking**: the ``reasoning`` field is part of the structured
**schema** (the model always articulates its deduction there), and any extended-thinking
blocks the response *does* carry are prepended. Structured outputs + adaptive thinking
suppress separate thinking blocks on current models, so the schema field is the reliable
channel; the block capture is a future-proof supplement. As with the clue adapter, the
pure helpers (render/prompt/parse) are unit-tested; the one untestable-in-CI part is the
live ``messages.create`` call.

Model note (verified live): ``claude-opus-4-8`` uses **adaptive** thinking
(``thinking={"type": "adaptive"}`` + ``output_config={"effort": ...}``), not the older
``{"type": "enabled", "budget_tokens": ...}`` form (which 400s on this model).

``anthropic`` is the optional ``clue`` extra, imported lazily; the container builds
without it and only a live solve needs the SDK and a key (resolved by the composition
root from ``Config.clue_api_key_env`` and injected, so this adapter stays a pure
value-taker).
"""

from __future__ import annotations

import json
from typing import Any

from ..app.solve import SolveView
from ..app.solver import Placement, SolverMove

_DEFAULT_MODEL = "claude-opus-4-8"


def _render_grid(view: SolveView) -> str:
    """The current grid as text: ``#`` black, ``.`` blank white, else the letter."""
    grid = view.letter_grid()
    rows = []
    for row in grid:
        cells = [("#" if ch is None else (ch.upper() if ch else ".")) for ch in row]
        rows.append(" ".join(cells))
    return "\n".join(rows)


def _render_feedback(view: SolveView) -> str:
    """The last policy feedback as a short human line -- what the solver just learned."""
    fb = view.feedback
    if fb.solved:
        return "SOLVED."
    parts = [f"feedback policy: {fb.policy.value}"]
    if fb.correct_cells:
        parts.append(f"correct cells: {sorted(fb.correct_cells)}")
    if fb.wrong_cells:
        parts.append(f"wrong cells: {sorted(fb.wrong_cells)}")
    if fb.correct_entries:
        parts.append(f"correct entries: {sorted(fb.correct_entries)}")
    if fb.wrong_entries:
        parts.append(f"wrong entries: {sorted(fb.wrong_entries)}")
    if fb.conflicts:
        parts.append(f"crossing conflicts at: {sorted(fb.conflicts)}")
    if len(parts) == 1:
        parts.append("(no per-guess check under this policy)")
    return "\n".join(parts)


def _render_clues(view: SolveView) -> str:
    lines = ["Across:"]
    for e in view.across:
        clue = e.clue or "(no clue)"
        lines.append(f"  {e.number}A [{e.pattern}] ({e.length}) {clue}")
    lines.append("Down:")
    for e in view.down:
        clue = e.clue or "(no clue)"
        lines.append(f"  {e.number}D [{e.pattern}] ({e.length}) {clue}")
    return "\n".join(lines)


def _build_prompt(view: SolveView) -> str:
    """Assemble the per-turn prompt from the answer-free view. Carries the grid, the
    clues with current fill patterns, and the last feedback -- never an answer."""
    return "\n".join(
        [
            "You are solving a crossword. Fill every entry so all crossings agree.",
            "",
            "Grid so far (# = black square, . = empty cell, letters = your current fill):",
            _render_grid(view),
            "",
            _render_clues(view),
            "",
            "What you just learned:",
            _render_feedback(view),
            "",
            "Think through the crossings, then give your next placements. You may revise "
            "earlier guesses. Use an empty word to erase an entry. Put your chain of "
            "deduction (which clues you got, how the crossings constrained the rest, what "
            "you are unsure of) in the 'reasoning' field -- it is read to judge how the "
            "puzzle solves. Set give_up true only if you are truly stuck.",
        ]
    )


def _schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "reasoning": {"type": "string"},
            "placements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "number": {"type": "integer"},
                        "direction": {"type": "string", "enum": ["A", "D"]},
                        "word": {"type": "string"},
                    },
                    "required": ["number", "direction", "word"],
                    "additionalProperties": False,
                },
            },
            "give_up": {"type": "boolean"},
        },
        "required": ["reasoning", "placements"],
        "additionalProperties": False,
    }


def _parse(text: str, thinking: str = "") -> SolverMove:
    """Turn the JSON response into a :class:`SolverMove`, combining any extended-thinking
    text with the schema's ``reasoning`` field. Malformed placement items are dropped (the
    harness would reject them anyway); a whole-response parse failure yields an empty move
    rather than raising, keeping the port total."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return SolverMove(reasoning=thinking)
    placements = []
    for item in data.get("placements", []):
        number = item.get("number")
        direction = item.get("direction")
        word = item.get("word", "")
        if isinstance(number, int) and direction in ("A", "D") and isinstance(word, str):
            placements.append(Placement(number=number, direction=direction, word=word))
    reasoning = "\n".join(part for part in (thinking, str(data.get("reasoning", ""))) if part)
    return SolverMove(
        placements=tuple(placements),
        reasoning=reasoning,
        give_up=bool(data.get("give_up", False)),
    )


def _extract_reasoning(blocks: Any) -> str:
    """Concatenate the extended-thinking blocks of a response into the reasoning trace."""
    out = []
    for block in blocks:
        if getattr(block, "type", None) == "thinking":
            out.append(getattr(block, "thinking", ""))
    return "\n".join(t for t in out if t)


class ClaudeSolverAgent:
    """``app.solver.SolverAgent`` backed by the Anthropic SDK, with extended thinking
    captured as the move's reasoning."""

    def __init__(
        self,
        *,
        model: str = _DEFAULT_MODEL,
        max_tokens: int = 8192,
        effort: str = "high",
        api_key: str | None = None,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._effort = effort
        self._api_key = api_key
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ModuleNotFoundError as e:  # pragma: no cover - env-dependent
                raise RuntimeError(
                    "solving needs the 'anthropic' SDK; install the 'clue' extra "
                    "(uv sync --extra clue) and provide a key (see Config.clue_api_key_env)"
                ) from e
            self._client = (
                anthropic.Anthropic(api_key=self._api_key)
                if self._api_key
                else anthropic.Anthropic()
            )
        return self._client

    def act(self, view: SolveView) -> SolverMove:
        prompt = _build_prompt(view)
        response = self._ensure_client().messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            thinking={"type": "adaptive"},
            output_config={
                "effort": self._effort,
                "format": {"type": "json_schema", "schema": _schema()},
            },
            messages=[{"role": "user", "content": prompt}],
        )
        thinking = _extract_reasoning(response.content)
        text = next(block.text for block in response.content if block.type == "text")
        return _parse(text, thinking)
