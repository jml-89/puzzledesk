"""Shared test doubles.

The point of the refactor is that impure dependencies are injected, so tests can
drive the pure code with fakes instead of files and a global RNG. These are those
fakes: an in-memory :class:`LexiconSource` and a seed-recording ``RngFactory``.
Both satisfy the same ports the real adapters do, so a service cannot tell the
difference.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

import numpy as np

from puzzledesk.app.clue import Clue, ClueStyle
from puzzledesk.app.cluing import CluedPuzzle
from puzzledesk.app.puzzle import FilledGrid, Target, TargetId
from puzzledesk.app.solve import EntryRef, SolveView
from puzzledesk.app.solver import Placement, SolverMove
from puzzledesk.core.lexicon import Lexicon, MultiLexicon
from puzzledesk.core.probe import Event
from puzzledesk.core.rng import Rng


class InMemoryLexiconSource:
    """Implements ``app.ports.LexiconSource`` from lexicons held in memory -- no
    filesystem. Keyed by length; the list ``name`` is ignored (tests use one list)."""

    def __init__(
        self,
        single: dict[int, Lexicon] | None = None,
        multi: MultiLexicon | None = None,
    ) -> None:
        self._single = single or {}
        self._multi = multi

    def load(
        self, name: str, length: int, *, min_score: float = 0.0, max_score: float | None = None
    ) -> Lexicon:
        return self._single[length].filtered(min_score, max_score)

    def load_multi(
        self,
        name: str,
        lengths: Iterable[int],
        *,
        min_score: float = 0.0,
        max_score: float | None = None,
    ) -> MultiLexicon:
        assert self._multi is not None, "no multi-lexicon configured"
        return self._multi


class RecordingRngFactory:
    """Implements ``core.rng.RngFactory`` and records every seed requested -- so a
    test can assert the service used the injected factory (and how)."""

    def __init__(self) -> None:
        self.seeds: list[int] = []

    def create(self, seed: int) -> Rng:
        self.seeds.append(seed)
        return np.random.default_rng(seed)


class RecordingProbe:
    """Implements ``core.probe.Probe`` by appending every event to a list -- the
    observation analogue of ``RecordingRngFactory``. Lets a test assert *what* an
    engine reported (order, counts, the terminal reason) without any I/O, and
    (paired with a NULL_PROBE run) that observing did not change the result."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


class RecordingWriter:
    """A fake ``write`` sink (``str -> None``) that records every string written, so a
    test can assert exactly what a probe adapter rendered with no real stream. The
    output-side analogue of ``RecordingProbe``."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, s: str) -> None:
        self.lines.append(s)


class FakeClock:
    """A settable monotonic clock (``() -> float``) for an adapter's injected ``now``, so
    elapsed/rate are deterministic without the wall clock. Set ``.t`` between events."""

    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


class FakeClueProvider:
    """Implements ``app.clue.ClueProvider`` deterministically -- no LLM, no network.

    Clues reference the target's difficulty, kind and start cell -- never the answer
    (a real clue does not contain its answer), so they pass the service's hard
    constraint while still identifying the target, letting a test assert the right
    clue reached the right target. ``leak_answer=True`` instead produces clues that
    embed the answer, so a test can exercise the constraint's *reject* path (every
    target ends up unclued)."""

    def __init__(self, *, leak_answer: bool = False) -> None:
        self._leak = leak_answer

    def clue(
        self,
        grid: FilledGrid,
        targets: Sequence[Target],
        *,
        style: ClueStyle,
        n: int = 1,
    ) -> Mapping[TargetId, Sequence[Clue]]:
        out: dict[TargetId, Sequence[Clue]] = {}
        for t in targets:
            if self._leak:
                texts = [f"the word is {t.answer} #{i}" for i in range(n)]
            else:
                texts = [
                    f"[{style.difficulty.name}] {t.kind} at {t.cells[0]} #{i}" for i in range(n)
                ]
            out[t.id] = tuple(Clue(x) for x in texts)
        return out


def _answer_map(puzzle: CluedPuzzle) -> dict[EntryRef, str]:
    grid = puzzle.grid
    numbering = grid.numbering()
    return {(numbering[t.cells[0]], t.kind): t.answer for t in grid.runs()}


class FakeSolverAgent:
    """Implements ``app.solver.SolverAgent`` deterministically -- no LLM, no network.

    Two modes, the way ``FakeClueProvider`` has two:

      * **oracle** -- constructed with the ``CluedPuzzle`` (a test double is *allowed*
        to read the key the real agent never sees), it places the correct word for the
        next not-yet-correct entries, ``per_turn`` at a time, so the harness loop runs
        several turns and completes. Reasoning is a canned string, so a test can assert
        the transcript captured it.
      * **scripted** -- replays a fixed ``list[SolverMove]`` (then empty moves), for
        exercising wrong guesses, erasing, invalid placements, give-up, and budget
        exhaustion.
    """

    def __init__(
        self,
        *,
        oracle: CluedPuzzle | None = None,
        script: list[SolverMove] | None = None,
        per_turn: int = 1,
        reasoning: str = "considering the crossings",
    ) -> None:
        self._answers = _answer_map(oracle) if oracle is not None else {}
        self._script = list(script) if script is not None else None
        self._per_turn = per_turn
        self._reasoning = reasoning
        self._i = 0

    def act(self, view: SolveView) -> SolverMove:
        if self._script is not None:
            move = self._script[self._i] if self._i < len(self._script) else SolverMove()
            self._i += 1
            return move
        placements = []
        for e in (*view.across, *view.down):
            answer = self._answers.get((e.number, e.direction))
            current = "".join(ch or "\0" for ch in e.letters)
            if answer is None or current == answer:
                continue
            placements.append(Placement(e.number, e.direction, answer))
            if len(placements) >= self._per_turn:
                break
        return SolverMove(placements=tuple(placements), reasoning=self._reasoning)
