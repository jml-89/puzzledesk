"""The mini-generator use-case: distinct double word squares above a quality bar.

Data flow (architecture.md "generate a mini"): load the curated list at length N,
filter to the bar, wrap in a DoubleSquare, and run the complete backtracker per
seed with ``distinct=True``; every solved grid is validated (>= bar and 2N
distinct) by construction, then shaped into a :class:`MiniResult`.

Everything impure is injected: the word list via a :class:`LexiconSource`, the
randomness via a :class:`RngFactory` (one fresh stream per seed, so results are
reproducible). The service itself is pure orchestration over the core.
"""

from __future__ import annotations

import numpy as np

from puzzledesk.app.difficulty import solve_order
from puzzledesk.app.ports import LexiconSource
from puzzledesk.app.puzzle import filled_from_square
from puzzledesk.app.results import MiniBatch, MiniResult, SolveDifficulty, WordScore
from puzzledesk.app.spec import FillSpec, GridSpec
from puzzledesk.core.engines import backtrack
from puzzledesk.core.rng import RngFactory
from puzzledesk.core.square import DoubleSquare
from puzzledesk.core.validate import Verdict, score_of, validate

# A frozen, shareable default so the ``generate`` signature can name it without a
# per-call construction (ruff B008); FillSpec is immutable, so one instance is safe.
_NO_TARGET = FillSpec()


class MiniService:
    """Generate a *batch* of distinct minis (double word squares) above a quality bar,
    with optional difficulty targeting.

    The square is the :class:`~puzzledesk.app.spec.FullSquare` layout of the generic
    generator; a *single* square flows through
    :meth:`~puzzledesk.app.generate.GenerateService.fill_grid` like any other grid. This
    service is the square's *batch + scoring* specialist: it keeps the ``DoubleSquare`` and
    the solved state so it can score every word (invariant 4) and read solve-order
    difficulty (D22/D23), which the model-agnostic ``FilledGrid`` cannot carry.
    """

    def __init__(
        self, lexicon: LexiconSource, rng_factory: RngFactory, *, list_name: str = "cw"
    ) -> None:
        self._lexicon = lexicon
        self._rng = rng_factory
        self._list_name = list_name

    def generate(self, grid: GridSpec, sel: FillSpec = _NO_TARGET, *, count: int = 3) -> MiniBatch:
        """Up to ``count`` distinct minis of order ``grid.rows`` with every word scoring in
        ``[grid.min_score, grid.max_score]`` (``max_score=None`` == an open floor, the plain
        quality bar; a two-sided band is the difficulty knob, D21). Backtracking is
        complete, so on a given band ``solve`` either yields a grid or proves none
        exists -- a ``None`` is that proof, not a seed artefact; the seed only varies
        *which* grid, for diversity. We sweep seeds up to a budget, dedupe by fill so the
        batch is distinct grid-wide (a complete search can return the same solution under
        different seeds), and stop at ``count``.

        With ``sel.min_hard_gets > 0`` the service *targets a difficulty* (D23): each solved
        grid is scored by ``solve_order`` (against the full vocabulary, under ``sel.gimme``)
        and kept only if it needs at least ``min_hard_gets`` hard gets; the survivors are
        returned hardest-first with a :class:`SolveDifficulty` attached. This selection
        is best-of-budget, **not** a proof: returning fewer than ``count`` means "not
        found in the seed budget", never "impossible" (unlike a backtracker ``None``).
        Pair a high ``min_hard_gets`` with a high ``gimme`` and/or an obscure band, or the
        target is rare and the budget is spent finding it."""
        n = grid.rows
        full = self._lexicon.load(self._list_name, n)  # full solving vocabulary (D22)
        lex = full.filtered(grid.min_score, grid.max_score)  # the generation band
        sq = DoubleSquare(lex)
        targeting = sel.min_hard_gets > 0

        def score(w: str) -> float:
            return full.score_map.get(w, 0.0)

        results: list[MiniResult] = []
        seen: set[tuple[str, ...]] = set()
        for seed in range(count * (40 if targeting else 20)):
            state = backtrack.solve(sq, rng=self._rng.create(seed), distinct=True)
            if state is None:
                continue
            words = tuple(sq.rows.words[i] for i in state)
            if words in seen:  # a batch never repeats a grid (invariant 3, grid-wide)
                continue
            v = validate(sq, state, grid.min_score)
            assert v.ok, v  # filtered list + distinct=True guarantee this
            difficulty = None
            if targeting:
                traj = solve_order(
                    filled_from_square(sq, state), full.n_candidates, score, gimme=sel.gimme
                )
                if len(traj.hard_gets) < sel.min_hard_gets:
                    continue
                b = traj.bottleneck
                difficulty = SolveDifficulty(
                    hard_gets=len(traj.hard_gets),
                    bottleneck_word=b.answer if b else None,
                    bottleneck_fits=b.candidates if b else 0,
                    gimme=sel.gimme,
                )
            seen.add(words)
            results.append(_to_result(sq, state, v, difficulty))
            if len(results) >= count:
                break
        if targeting:
            results.sort(
                key=lambda r: (r.difficulty.hard_gets, r.difficulty.bottleneck_fits),  # type: ignore[union-attr]
                reverse=True,
            )
        return MiniBatch(
            n=n,
            min_score=grid.min_score,
            max_score=grid.max_score,
            eligible=len(lex),
            results=results,
            min_hard_gets=sel.min_hard_gets,
            gimme=sel.gimme,
        )


def _to_result(
    sq: DoubleSquare, state: np.ndarray, v: Verdict, difficulty: SolveDifficulty | None = None
) -> MiniResult:
    across = [WordScore(sq.rows.words[i], float(sq.rows.scores[i])) for i in state]
    down = [WordScore(w, score_of(sq.cols, w)) for w in sq.column_strings(state)]
    return MiniResult(
        across=across,
        down=down,
        weakest=WordScore(v.weakest[0], v.weakest[1]),
        difficulty=difficulty,
    )
