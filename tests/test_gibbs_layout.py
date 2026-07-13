"""The Gibbs energy-field layout sampler (D27), as contracts.

The sampler is the *soft* counterpart to ``patterns.gen_capped``'s complete search:
it draws black-cell layouts from an energy field (local run-length legality, density,
anti-cluster, no-2x2) by annealed Gibbs, with symmetry by construction and
connectivity as a global reject. These tests pin what that must guarantee:

  * **legality** -- every sample is a member of the complete legal set ``gen_capped``
    enumerates (the ground-truth subset check, the layout analogue of
    ``backtrack ⊆ bruteforce``);
  * **the aesthetic contract that motivated the spike** -- no 2x2 black block, ever,
    though the legal set itself contains them;
  * **symmetry** by construction, and **reproducibility** from the seed;
  * **honesty** -- a miss is budget exhaustion, never a proof (that is
    ``capped_layout_exists``'s job).
"""

from __future__ import annotations

import numpy as np
from fakes import InMemoryLexiconSource, RecordingRngFactory

from puzzledesk.app.generate import GenerateService
from puzzledesk.app.spec import GibbsLayout, GridSpec
from puzzledesk.core.engines import gibbs_layout as gibbs
from puzzledesk.core.engines import patterns
from puzzledesk.core.lexicon import Lexicon, MultiLexicon


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def _key(g) -> tuple[tuple[bool, ...], ...]:
    return tuple(tuple(row) for row in g.block)


def _has_2x2(block: list[list[bool]]) -> bool:
    R, C = len(block), len(block[0])
    return any(
        block[r][c] and block[r + 1][c] and block[r][c + 1] and block[r + 1][c + 1]
        for r in range(R - 1)
        for c in range(C - 1)
    )


def _complete_legal(rows: int, cols: int, max_len: int) -> set:
    """Every legal capped layout, from the complete search -- the ground truth."""
    return {
        _key(g)
        for g in patterns.gen_capped(
            rows,
            cols,
            rng=_rng(0),
            cap=patterns.CapSpec(min_len=3, max_len=max_len, symmetric=True),
            randomize=False,
        )
    }


def _samples(rows: int, cols: int, max_len: int, *, seeds: int, frac: float = 0.12) -> list:
    out = []
    for seed in range(seeds):
        g = next(
            gibbs.gibbs_layouts(
                rows, cols, rng=_rng(seed), min_len=3, max_len=max_len, black_fraction=frac
            ),
            None,
        )
        if g is not None:
            out.append(g)
    return out


def test_gibbs_samples_are_a_subset_of_the_complete_legal_set() -> None:
    # 5x5 max_len=5 has 15 legal capped layouts; every Gibbs draw must be one of them
    # (legal by exactly gen_capped's definition -- the layout analogue of the fill
    # engine's `backtrack ⊆ bruteforce` ground truth). This is the correctness gate.
    legal = _complete_legal(5, 5, 5)
    got = _samples(5, 5, 5, seeds=40)
    assert got, "the sampler must produce some layouts on an easy shape"
    assert all(_key(g) in legal for g in got)


def test_gibbs_never_produces_a_2x2_black_block() -> None:
    # The aesthetic contract that motivated the spike: the no-2x2 rule is an explicit
    # energy term, so the field forbids the block by construction -- even though the
    # complete legal set contains layouts that have one (a defect gen_capped can emit).
    legal = _complete_legal(5, 5, 5)
    assert any(_has_2x2([list(r) for r in k]) for k in legal), "legal set should contain a 2x2"
    got = _samples(5, 5, 5, seeds=40)
    assert got
    assert not any(_has_2x2(g.block) for g in got)


def test_gibbs_samples_are_symmetric_by_construction() -> None:
    # Symmetry is global-but-free: the sampler colours whole 180deg orbits, so every
    # draw is symmetric with no penalty term for it.
    for g in _samples(10, 10, 5, seeds=6, frac=0.18):
        R, C = g.rows, g.cols
        assert all(
            g.block[r][c] == g.block[R - 1 - r][C - 1 - c] for r in range(R) for c in range(C)
        )


def test_gibbs_is_reproducible_from_the_seed() -> None:
    # A given seed stream reproduces the same layout, bit-for-bit (the reproducibility
    # invariant, preserved for the sampler as for every engine).
    a = next(gibbs.gibbs_layouts(10, 10, rng=_rng(3), min_len=3, max_len=5, black_fraction=0.18))
    b = next(gibbs.gibbs_layouts(10, 10, rng=_rng(3), min_len=3, max_len=5, black_fraction=0.18))
    assert _key(a) == _key(b)


def test_a_gibbs_miss_is_budget_exhaustion_not_a_proof() -> None:
    # The load-bearing epistemic line: a legal layout provably EXISTS (the complete
    # search finds one), yet a single-attempt anneal can still come up empty. A sampler
    # miss must never be read as UNSAT -- capped_layout_exists is the theorem, not this.
    assert (
        next(
            patterns.gen_capped(5, 5, rng=_rng(0), cap=patterns.CapSpec(min_len=3, max_len=4)), None
        )
        is not None
    )
    misses = [
        next(
            gibbs.gibbs_layouts(
                5,
                5,
                rng=_rng(seed),
                min_len=3,
                max_len=4,
                black_fraction=0.24,
                attempts_per_layout=1,
            ),
            None,
        )
        is None
        for seed in range(10)
    ]
    assert any(misses), "with a 1-anneal budget some seeds miss -- and a miss is not a proof"


# --- D28: the reject-reason study instrument -------------------------------------


def _params(max_len: int) -> gibbs.FieldParams:
    return gibbs.FieldParams(min_len=3, max_len=max_len, target_black=0)


def test_reject_reason_classifies_each_failure() -> None:
    # The study instrument (scripts/gibbs.py): reject_reason must name why _finalize would
    # reject a raw field, in _finalize's own predicate order
    # (degenerate < short_run < over_cap < disconnected).
    def blk(rows: list[str]) -> list[list[bool]]:
        return [[ch == "#" for ch in row] for row in rows]

    # legal: two symmetric corner blacks, every run in [3,5], connected.
    ok = blk(["#....", ".....", ".....", ".....", "....#"])
    assert gibbs.reject_reason(ok, 5, 5, _params(5)) == "ok"
    # a length-1 white run (top-left corner isolated by two blacks): short_run.
    short = blk([".#...", "#....", ".....", ".....", "....."])
    assert gibbs.reject_reason(short, 5, 5, _params(5)) == "short_run"
    # every run legal at min_len but a length-5 row exceeds a max_len of 4: over_cap.
    assert gibbs.reject_reason(ok, 5, 5, _params(4)) == "over_cap"
    # a full black column down the middle of a 3x7 splits it into two 3x3 blocks: the runs
    # are all legal (len 3) but the white cells are two regions: disconnected.
    split = blk(["...#...", "...#...", "...#..."])
    assert gibbs.reject_reason(split, 3, 7, _params(5)) == "disconnected"


# --- service wiring --------------------------------------------------------------

# The unique legal 5x5/max_len=4 layout is a black border around a 3x3 white core, so
# the same distinct 3x3 double word square the capped service test uses fills it:
#   b a d   down: boy / ane / des
#   o n e
#   y e s
_LEX3 = Lexicon(["bad", "one", "yes", "boy", "ane", "des"], [90.0] * 6)


def test_gibbs_service_fills_within_cap_distinct_and_uses_the_factory() -> None:
    source = InMemoryLexiconSource(multi=MultiLexicon({3: _LEX3}))
    rng = RecordingRngFactory()
    service = GenerateService(source, rng)
    # The sampler finds the bordered-3x3 layout on most seeds; the 3x3 lexicon fills it.
    # Loop a few seeds and require at least one honest success (others may miss -- budget).
    results = [
        service.fill(
            GridSpec(rows=5, cols=5, min_score=0.0, seed=seed),
            GibbsLayout(max_len=4, num_black=0),
        )
        for seed in range(8)
    ]
    filled = [r for r in results if r is not None]
    assert filled, "at least one seed should sample a fillable layout"
    for res in filled:
        entries = res.across + res.down
        assert len(entries) == 6
        assert all(len(e.word) <= 4 for e in entries)  # within the cap
        assert len({e.word for e in entries}) == 6  # distinct (invariant 3)
    assert rng.seeds and rng.seeds[0] == 0  # drove the injected factory
