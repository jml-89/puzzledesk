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
from puzzledesk.app.puzzle import FilledGrid, Target, TargetId
from puzzledesk.core.lexicon import Lexicon, MultiLexicon
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

    def load(self, name: str, length: int, *, min_score: float = 0.0) -> Lexicon:
        return self._single[length].filtered(min_score)

    def load_multi(
        self, name: str, lengths: Iterable[int], *, min_score: float = 0.0
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
