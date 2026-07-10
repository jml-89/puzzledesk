"""Blocked-generate service, driven with injected fakes (no files, no global RNG).

Covers the cap-driven path (``fill_capped_once``, D24): the search that places
black cells to hold every entry within a length cap, so a grid larger than the
word data still fills. Here a tiny in-memory multi-lexicon fills a 3x3 (the cap
does not bite yet, but the wiring, distinctness, and cap-within-lengths contract
do), and the odd-count-on-a-symmetric-even-grid proof is exercised.
"""

from __future__ import annotations

from fakes import InMemoryLexiconSource, RecordingRngFactory

from puzzledesk.app.blocked import BlockedGenerateService
from puzzledesk.core.lexicon import Lexicon, MultiLexicon

# A distinct 3x3 double word square lives in this 6-word length-3 list:
#   b a d      down: boy / ane / des
#   o n e
#   y e s
_LEX3 = Lexicon(["bad", "one", "yes", "boy", "ane", "des"], [90.0] * 6)


def _service() -> tuple[BlockedGenerateService, RecordingRngFactory]:
    source = InMemoryLexiconSource(multi=MultiLexicon({3: _LEX3}))
    rng = RecordingRngFactory()
    return BlockedGenerateService(source, rng), rng


def test_capped_fill_stays_within_the_length_cap_and_is_distinct() -> None:
    service, rng = _service()
    res = service.fill_capped_once(3, 3, max_len=3, min_score=0.0, seed=0, num_black=0)
    assert res is not None
    entries = res.across + res.down
    assert len(entries) == 6  # 3 across + 3 down
    assert all(len(e.word) <= 3 for e in entries)  # nothing exceeds the cap
    assert len({e.word for e in entries}) == 6  # all distinct (invariant 3)
    assert rng.seeds and rng.seeds[0] == 0  # used the injected factory


def test_capped_layout_existence_is_a_shape_property() -> None:
    service, _ = _service()
    # A 10x10 has no centre cell, so an odd black count admits no symmetric layout.
    assert not service.capped_layout_exists(10, 10, max_len=5, num_black=17)
    assert service.capped_layout_exists(10, 10, max_len=5, num_black=18)
