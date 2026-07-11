"""The observation port as a contract (core.probe).

The load-bearing property is **observe-only**: attaching a probe must not change what
the engine computes -- determinism and completeness cannot depend on whether anyone is
watching. The rest pins the event vocabulary: a run emits an ordered stream, the sampled
counters are monotonic, and the terminal ``reason`` carries the proof-vs-budget tag the
engines already distinguish.
"""

from __future__ import annotations

from itertools import product

import numpy as np
from fakes import RecordingProbe, RecordingRngFactory

from puzzledesk.core.engines import fill, patterns
from puzzledesk.core.lexicon import Lexicon, MultiLexicon
from puzzledesk.core.probe import (
    Finished,
    NullProbe,
    Probe,
    Progress,
    Solved,
)

# A tiny multi-lexicon that fills a 2x2 (four distinct 2-letter words) -- enough to drive
# fill.solve to a Solved, small enough to stay a unit test.
_FILLABLE = MultiLexicon({2: Lexicon(["ab", "cd", "ac", "bd"])})
_UNFILLABLE = MultiLexicon({2: Lexicon(["ab"])})  # only one word: no distinct fill


def _factory() -> RecordingRngFactory:
    return RecordingRngFactory()


def test_null_probe_satisfies_the_port() -> None:
    assert isinstance(NullProbe(), Probe)
    assert isinstance(RecordingProbe(), Probe)


def _white(rows: int, cols: int, min_len: int) -> object:
    """The single all-white layout of this shape (num_black=0)."""
    return next(patterns.gen_capped(rows, cols, rng=np.random.default_rng(0),
                                    min_len=min_len, max_len=min_len, num_black=0))


def test_probe_does_not_change_result() -> None:
    # The same 2x2 fill, once un-watched and once recorded, must return the identical grid.
    g = _white(2, 2, 2)
    quiet = fill.solve(g, _FILLABLE, rng=np.random.default_rng(3))
    watched = fill.solve(g, _FILLABLE, rng=np.random.default_rng(3), probe=RecordingProbe())
    assert quiet == watched is not None


def test_fill_emits_solved_on_success() -> None:
    probe = RecordingProbe()
    assert fill.solve(_white(2, 2, 2), _FILLABLE, rng=np.random.default_rng(3),
                      probe=probe) is not None
    assert any(isinstance(e, Solved) for e in probe.events)


def test_capped_run_emits_ordered_stream() -> None:
    probe = RecordingProbe()
    patterns.fill_capped(2, 2, _FILLABLE, rng_factory=_factory(), max_len=2, min_len=2,
                         num_black=0, probe=probe)
    kinds = [type(e).__name__ for e in probe.events]
    assert kinds[0] == "PhaseStarted"
    assert "Attempt" in kinds
    assert kinds[-1] == "Finished"
    # exactly one terminal event, and it is last
    assert sum(isinstance(e, Finished) for e in probe.events) == 1


def test_terminal_reason_is_solved_when_filled() -> None:
    probe = RecordingProbe()
    patterns.fill_capped(2, 2, _FILLABLE, rng_factory=_factory(), max_len=2, min_len=2,
                         num_black=0, probe=probe)
    (done,) = [e for e in probe.events if isinstance(e, Finished)]
    assert done.ok and done.reason == "solved" and done.attempts >= 1


def test_terminal_reason_exhausted_is_a_proof() -> None:
    # A complete search of a provably-empty layout space (an odd black count on an
    # even-celled symmetric grid has no centre cell) reports ``exhausted`` -- the UNSAT
    # theorem, not a timeout -- with zero attempts.
    probe = RecordingProbe()
    out = patterns.fill_capped(6, 6, _FILLABLE, rng_factory=_factory(), max_len=5,
                               num_black=1, symmetric=True, probe=probe)
    assert out is None
    (done,) = [e for e in probe.events if isinstance(e, Finished)]
    assert not done.ok and done.reason == "exhausted" and done.attempts == 0


def test_terminal_reason_budget_is_not_a_proof() -> None:
    # A layout that cannot fill distinctly, under a fill node budget: the miss is budget
    # exhaustion, so the reason is ``budget`` (a bounded search, not a theorem).
    probe = RecordingProbe()
    patterns.fill_capped(2, 2, _UNFILLABLE, rng_factory=_factory(), max_len=2, min_len=2,
                         num_black=0, node_budget=1, probe=probe)
    (done,) = [e for e in probe.events if isinstance(e, Finished)]
    assert not done.ok and done.reason == "budget"


def test_progress_counters_are_monotonic() -> None:
    # A search big enough to sample Progress (a 5x5 double square over a diverse length-5
    # lexicon that does not solve inside the budget): the node counter never decreases.
    words = ["".join(p) for p in product("abcde", repeat=5)][:150]
    mlex = MultiLexicon({5: Lexicon(words)})
    probe = RecordingProbe()
    fill.solve(_white(5, 5, 5), mlex, rng=np.random.default_rng(1),
               node_budget=20_000, probe=probe)
    fill_nodes = [e.nodes for e in probe.events if isinstance(e, Progress)]
    assert len(fill_nodes) >= 2, "expected sampled Progress events"
    assert fill_nodes == sorted(fill_nodes) and len(set(fill_nodes)) == len(fill_nodes)
