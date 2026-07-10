"""The DI payoff: drive the application services with injected fakes.

No files, no stdout, no global RNG -- an in-memory lexicon source and a
seed-recording factory (fakes.py) stand in for the real adapters. This is what
"testing less chaotic" means concretely: the use-case logic is exercised in
isolation, and the result is a value we can assert on.
"""

from __future__ import annotations

from fakes import InMemoryLexiconSource, RecordingRngFactory

from puzzledesk.app.mini import MiniService
from puzzledesk.core.lexicon import Lexicon

# ab/cd across induce ac/bd down: a genuine distinct 2x2 double square exists.
_LEX = Lexicon(["ab", "cd", "ac", "bd"])


def _service() -> tuple[MiniService, RecordingRngFactory]:
    source = InMemoryLexiconSource(single={2: _LEX})
    rng = RecordingRngFactory()
    return MiniService(source, rng), rng


def test_service_emits_distinct_grids_above_the_bar() -> None:
    service, _ = _service()
    batch = service.generate(2, min_score=0.0, count=1)
    assert batch.eligible == len(_LEX)
    assert len(batch.results) == 1
    r = batch.results[0]
    words = [w.word for w in r.across] + [w.word for w in r.down]
    assert len(set(words)) == 2 * 2  # 2N distinct
    assert all(w.score >= 0.0 for w in r.across + r.down)


def test_batch_has_no_duplicate_grids() -> None:
    # Only a handful of distinct double squares exist on this tiny lexicon, so a
    # *complete* search returns the same fill under different seeds. The batch must
    # still never repeat a grid -- invariant 3 (distinctness) applied grid-wide across
    # the batch, not only within one grid.
    service, _ = _service()
    batch = service.generate(2, min_score=0.0, count=5)
    grids = [tuple(w.word for w in r.across) for r in batch.results]
    assert grids  # the lexicon admits at least one distinct square
    assert len(grids) == len(set(grids))  # ...and no grid is emitted twice


def test_service_uses_the_injected_factory() -> None:
    _, rng = _service()[0], _service()[1]
    service = MiniService(InMemoryLexiconSource(single={2: _LEX}), rng)
    service.generate(2, min_score=0.0, count=1)
    # The service pulled at least one stream from the injected factory, by seed.
    assert rng.seeds and rng.seeds[0] == 0


def test_service_is_reproducible() -> None:
    a = _service()[0].generate(2, min_score=0.0, count=1)
    b = _service()[0].generate(2, min_score=0.0, count=1)
    assert [w.word for w in a.results[0].across] == [w.word for w in b.results[0].across]
