"""The Claude solver adapter -- the real (soft, generative) implementation of the
``app.solver.SolverAgent`` port.

This is the *second* LLM consumer D16 anticipated. We hold D16's line: the LLM does not
become an app-layer port. The app depends on ``SolverAgent`` (views and moves); the SDK,
the credential (resolved by the composition root from ``Config.clue_api_key_env`` and
injected), and the reasoning capture all live *here*, beside ``ClaudeClueProvider``.

**Reasoning is the measurement, so the call is shaped to expose it** (D24; verified live,
see notes.md "Agent solve loop"). The solver runs with **adaptive thinking**
(``thinking={"type":"adaptive"}`` + ``output_config={"effort":...}``) and, deliberately,
*without* a forced JSON schema: structured output suppresses the extended-thinking pass and
zeros ``thinking_tokens``, which is exactly the signal we are after -- for a model that
solves every mini, *how much it had to think* is the graded difficulty tell, not whether it
finished. So the model reasons freely in the text block (readable prose) and ends with a
JSON object we parse leniently; ``SolverMove.reasoning_tokens`` carries the thinking-token
count from ``usage``. (The thinking block itself is returned redacted/empty on current
models, so the readable reasoning is the text block; the token *count* is the scalar.)

``anthropic`` is the optional ``clue`` extra, imported lazily; the container builds without
it and only a live solve needs the SDK and a key. The pure helpers (render/prompt/parse) are
unit-tested; the one untestable-in-CI part is the live ``messages.create`` call.
"""

from __future__ import annotations

import json
from dataclasses import replace
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
            "Work through the clues and crossings. You may revise earlier guesses; use an "
            "empty word to erase an entry.",
            "When you are done reasoning, end your reply with a single JSON object on its own:",
            '{"placements": [{"number": <n>, "direction": "A"|"D", "word": "<letters>"}, ...], '
            '"give_up": false}',
            "Set give_up true only if you are truly stuck.",
        ]
    )


def _extract_json(text: str) -> dict[str, Any] | None:
    """The move object in ``text`` (the model reasons in prose, then emits the object).
    Tries every ``{`` start and returns the first parseable object that carries
    ``placements`` -- so a *nested* placement item (also valid JSON) is not mistaken for
    the whole move -- falling back to the first parseable object. Tolerant of prose, code
    fences, or trailing text around it."""
    decoder = json.JSONDecoder()
    fallback: dict[str, Any] | None = None
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[i:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            if "placements" in obj:
                return obj
            if fallback is None:
                fallback = obj
    return fallback


def _parse(text: str, reasoning_tokens: int | None = None) -> SolverMove:
    """Turn the free-form response into a :class:`SolverMove`: the prose is the readable
    reasoning, the trailing JSON gives the placements. Malformed items are dropped (the
    harness would reject them anyway); no JSON at all yields an empty move (the port stays
    total). ``reasoning_tokens`` is the thinking-token count from ``usage`` -- the tell."""
    reasoning = text.strip()
    data = _extract_json(text)
    if data is None:
        return SolverMove(reasoning=reasoning, reasoning_tokens=reasoning_tokens)
    placements = []
    for item in data.get("placements", []):
        if not isinstance(item, dict):
            continue
        number = item.get("number")
        direction = item.get("direction")
        word = item.get("word", "")
        if isinstance(number, int) and direction in ("A", "D") and isinstance(word, str):
            placements.append(Placement(number=number, direction=direction, word=word))
    return SolverMove(
        placements=tuple(placements),
        reasoning=reasoning,
        reasoning_tokens=reasoning_tokens,
        give_up=bool(data.get("give_up", False)),
    )


def _thinking_tokens(usage: Any) -> int | None:
    """The extended-thinking token count from a response's ``usage`` -- the amount of
    reasoning spent. ``None`` if the SDK does not surface it."""
    details = getattr(usage, "output_tokens_details", None)
    return getattr(details, "thinking_tokens", None) if details is not None else None


class ClaudeSolverAgent:
    """``app.solver.SolverAgent`` backed by the Anthropic SDK, running with adaptive
    thinking so the reasoning-token count (the difficulty tell) is exposed."""

    def __init__(
        self,
        *,
        model: str = _DEFAULT_MODEL,
        max_tokens: int = 32000,
        thinking_mode: str = "adaptive",
        effort: str = "high",
        thinking_budget: int = 4096,
        api_key: str | None = None,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._thinking_mode = thinking_mode
        self._effort = effort
        self._thinking_budget = thinking_budget
        self._api_key = api_key
        self._client: Any = None

    def _thinking_kwargs(self) -> dict[str, Any]:
        """The thinking/effort request keys for this model's thinking mode. Opus-family
        'adaptive' pairs with output_config.effort; Haiku-family 'enabled' takes a token
        budget; 'off' disables thinking. See Config.solve_thinking (verified live)."""
        if self._thinking_mode == "adaptive":
            return {"thinking": {"type": "adaptive"}, "output_config": {"effort": self._effort}}
        if self._thinking_mode == "enabled":
            return {"thinking": {"type": "enabled", "budget_tokens": self._thinking_budget}}
        return {}

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
            messages=[{"role": "user", "content": prompt}],
            **self._thinking_kwargs(),
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        move = _parse(text, _thinking_tokens(response.usage))
        # If the output budget ran out during the thinking pass, the model never emits its
        # move -- surface that as reasoning rather than returning a silent empty move the
        # harness would loop on (the artifact that inflated the obscure x Saturday cell, D24).
        if getattr(response, "stop_reason", None) == "max_tokens" and not move.placements:
            note = "[truncated: hit max_tokens before emitting a move; raise solve_max_tokens]"
            move = replace(move, reasoning=(move.reasoning + "\n" + note).strip())
        return move
