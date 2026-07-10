"""The Claude clue adapter -- the real (soft, generative) implementation of the
``app.clue.ClueProvider`` port.

"Don't reinvent the wheel" applies *here*, inside the adapter: it leans on the
Anthropic SDK for the client, retries, and structured outputs. The adapter takes an
explicit ``api_key`` -- mirroring ``anthropic.Anthropic(api_key=...)`` -- which the
composition root resolves from ``Config.clue_api_key_env`` and injects; when it is
``None`` the adapter defers to the SDK's own credential resolution
(``ANTHROPIC_API_KEY`` or an ``ant auth login`` profile). Reading the environment is
the composition root's job, so this adapter (like every other) is a pure value-taker.
The configurable env-var name exists because the standard ``ANTHROPIC_API_KEY`` is
auto-detected by other tooling in our environments; see docs/decisions.md D17. The
domain stays clean: the app depends on ``ClueProvider``, which speaks grids and clues,
not tokens -- credential wiring is construction, not part of the port's contract.

``anthropic`` is an **optional extra** (``uv sync --extra clue``), imported lazily
so the package installs, imports, and the container builds without it; only an
actual clue call needs the SDK and a key. The prompt/schema/parse helpers are pure
and unit-tested; the one untestable part is the live ``messages.create`` call.

The difficulty label is not decorative: ``_DIFFICULTY_GUIDANCE`` makes Mon..Sat control
clue **obliqueness** (how much the clue under-determines its answer), because that -- not
word obscurity -- is the lever that forces a solver onto the crossings (D26; validated
live, Monday clues cost the Opus solver ~1.1k reasoning tokens vs ~2.8k for Saturday on
the same grid). This is the clue-side (D21 layer B) counterpart to the fill's obscurity band.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from puzzledesk.app.clue import Clue, ClueStyle, Difficulty
from puzzledesk.app.puzzle import FilledGrid, Target, TargetId

_DEFAULT_MODEL = "claude-opus-4-8"
_KIND = {"A": "Across", "D": "Down", "meta": "Meta"}

# The Mon..Sat difficulty label is made to *mean something* by controlling clue
# **obliqueness** -- how much the clue under-determines its answer (D26 finding: clue
# ambiguity, not word obscurity, is the lever that forces a solver onto the crossings).
# The ladder runs from "the clue nearly hands over the answer" to "the answer is not
# determinable from the clue alone; the crossings must disambiguate". This is the
# clue-side (layer B, D21) counterpart to the word-obscurity band on the fill side.
_DIFFICULTY_GUIDANCE = {
    Difficulty.MONDAY: (
        "Monday (easiest): a direct, unambiguous definition. Anyone who knows the word "
        "should get it from the clue alone. No wordplay, no misdirection."
    ),
    Difficulty.TUESDAY: (
        "Tuesday: a straightforward definition from everyday knowledge, perhaps one small "
        "step of inference. Still no trickery."
    ),
    Difficulty.WEDNESDAY: (
        "Wednesday: a fair clue that takes a beat -- a less obvious synonym or angle, but "
        "the definition is still reachable from the clue alone."
    ),
    Difficulty.THURSDAY: (
        "Thursday: introduce wordplay and mild misdirection (puns, double meanings, a '?' "
        "clue). Do not hand over the answer; the solver often needs a crossing letter or two."
    ),
    Difficulty.FRIDAY: (
        "Friday (hard): oblique and tricky. Favour misdirection, slanted angles and wordplay "
        "over definition. The answer should usually NOT be gettable from the clue alone -- "
        "the solver must lean on the crossings."
    ),
    Difficulty.SATURDAY: (
        "Saturday (hardest): maximally oblique. Heavy misdirection, wordplay, deliberately "
        "broad or ambiguous phrasing; never a direct definition, never name the entity "
        "outright. The answer must NOT be determinable from the clue alone -- the crossing "
        "letters must disambiguate it."
    ),
}


def _render_grid(grid: FilledGrid) -> str:
    """The filled grid as text for the prompt (uppercase letters, ``#`` for black)."""
    return "\n".join(
        " ".join(cell.upper() if cell is not None else "#" for cell in row) for row in grid.cells
    )


def _build_prompt(grid: FilledGrid, targets: Sequence[Target], style: ClueStyle, n: int) -> str:
    lines = [
        "You are an expert crossword clue writer.",
        "",
        "Filled grid (uppercase = letters, # = black square):",
        _render_grid(grid),
        "",
        f"Target difficulty: {style.difficulty.name.title()} (Monday easiest, Saturday hardest).",
        _DIFFICULTY_GUIDANCE[style.difficulty],
    ]
    if style.instructions.strip():
        lines += ["", f"Additional instructions: {style.instructions.strip()}"]
    lines += [
        "",
        f"Write {n} distinct candidate clue(s) for each entry below, best first. "
        "A clue must never contain its own answer.",
        "",
    ]
    for i, t in enumerate(targets):
        lines.append(f"  [{i}] {_KIND.get(t.kind, t.kind)} -- answer {t.answer.upper()}")
    lines += [
        "",
        'Return JSON {"clues": [{"index": <i>, "candidates": ["clue", ...]}, ...]}, '
        "one item per target index above.",
    ]
    return "\n".join(lines)


def _schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "clues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "candidates": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["index", "candidates"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["clues"],
        "additionalProperties": False,
    }


def _parse(text: str, targets: Sequence[Target]) -> Mapping[TargetId, Sequence[Clue]]:
    data = json.loads(text)
    out: dict[TargetId, Sequence[Clue]] = {}
    for item in data.get("clues", []):
        i = item.get("index")
        if isinstance(i, int) and 0 <= i < len(targets):
            out[targets[i].id] = tuple(Clue(str(c)) for c in item.get("candidates", []))
    return out


class ClaudeClueProvider:
    """``app.clue.ClueProvider`` backed by the Anthropic SDK (structured outputs)."""

    def __init__(
        self,
        *,
        model: str = _DEFAULT_MODEL,
        max_tokens: int = 4096,
        api_key: str | None = None,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._api_key = api_key
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ModuleNotFoundError as e:  # pragma: no cover - env-dependent
                raise RuntimeError(
                    "clue generation needs the 'anthropic' SDK; install the 'clue' extra "
                    "(uv sync --extra clue) and provide a key (see Config.clue_api_key_env)"
                ) from e
            # An explicit key when the composition root resolved one; otherwise let the
            # SDK resolve credentials from its own environment / profile.
            self._client = (
                anthropic.Anthropic(api_key=self._api_key)
                if self._api_key
                else anthropic.Anthropic()
            )
        return self._client

    def clue(
        self,
        grid: FilledGrid,
        targets: Sequence[Target],
        *,
        style: ClueStyle,
        n: int = 1,
    ) -> Mapping[TargetId, Sequence[Clue]]:
        prompt = _build_prompt(grid, targets, style, n)
        response = self._ensure_client().messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            output_config={"format": {"type": "json_schema", "schema": _schema()}},
            messages=[{"role": "user", "content": prompt}],
        )
        text = next(block.text for block in response.content if block.type == "text")
        return _parse(text, targets)
