"""Generate service (blocked strategies), driven with injected fakes (no files, no
global RNG).

Covers the cap-driven path (:class:`CappedLayout`, D24): the search that places
black cells to hold every entry within a length cap, so a grid larger than the
word data still fills. Here a tiny in-memory multi-lexicon fills a 3x3 (the cap
does not bite yet, but the wiring, distinctness, and cap-within-lengths contract
do), and the odd-count-on-a-symmetric-even-grid proof is exercised via the unified
``layout_exists`` (D31).
"""

from __future__ import annotations

from fakes import InMemoryLexiconSource, RecordingRngFactory

from puzzledesk.app.generate import GenerateService
from puzzledesk.app.spec import CappedLayout, GridSpec
from puzzledesk.core.lexicon import Lexicon, MultiLexicon

# A distinct 3x3 double word square lives in this 6-word length-3 list:
#   b a d      down: boy / ane / des
#   o n e
#   y e s
_LEX3 = Lexicon(["bad", "one", "yes", "boy", "ane", "des"], [90.0] * 6)


def _service() -> tuple[GenerateService, RecordingRngFactory]:
    source = InMemoryLexiconSource(multi=MultiLexicon({3: _LEX3}))
    rng = RecordingRngFactory()
    return GenerateService(source, rng), rng


def test_capped_fill_stays_within_the_length_cap_and_is_distinct() -> None:
    service, rng = _service()
    res = service.fill(
        GridSpec(rows=3, cols=3, min_score=0.0), CappedLayout(max_len=3, num_black=0)
    )
    assert res is not None
    entries = res.across + res.down
    assert len(entries) == 6  # 3 across + 3 down
    assert all(len(e.word) <= 3 for e in entries)  # nothing exceeds the cap
    assert len({e.word for e in entries}) == 6  # all distinct (invariant 3)
    assert rng.seeds and rng.seeds[0] == 0  # used the injected factory


def test_capped_layout_existence_is_a_shape_property() -> None:
    service, _ = _service()
    grid = GridSpec(rows=10, cols=10)
    # A 10x10 has no centre cell, so an odd black count admits no symmetric layout.
    assert not service.layout_exists(grid, CappedLayout(max_len=5, num_black=17))
    assert service.layout_exists(grid, CappedLayout(max_len=5, num_black=18))
