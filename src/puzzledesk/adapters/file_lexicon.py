"""The filesystem lexicon adapter -- where the word-list I/O now lives.

The kernel parses text; this adapter does the ``read_text``. It owns the mapping
from a named list to a file (``<name>_<length>.txt`` under the data directory) and
the per-list format:

  * ``cw`` / ``scored`` -> "word score" lines (:meth:`Lexicon.from_scored_text`);
  * ``words``           -> plain word-per-line (:meth:`Lexicon.from_words_text`).

``min_score`` applies the acceptance-bar filter, so callers get a list where every
word already clears the bar (0.0 == unfiltered).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from puzzledesk.core.lexicon import Lexicon, MultiLexicon

_SCORED_LISTS = frozenset({"cw", "scored"})


class FileLexicon:
    """Implements ``app.ports.LexiconSource`` by reading ``data/<name>_<n>.txt``."""

    def __init__(self, data_dir: str | Path) -> None:
        self._dir = Path(data_dir)

    def _text(self, name: str, length: int) -> str:
        return (self._dir / f"{name}_{length}.txt").read_text()

    def load(
        self, name: str, length: int, *, min_score: float = 0.0, max_score: float | None = None
    ) -> Lexicon:
        if name in _SCORED_LISTS:
            lex = Lexicon.from_scored_text(self._text(name, length), length=length)
        else:
            lex = Lexicon.from_words_text(self._text(name, length), length=length)
        return lex.filtered(min_score, max_score)

    def load_multi(
        self,
        name: str,
        lengths: Iterable[int],
        *,
        min_score: float = 0.0,
        max_score: float | None = None,
    ) -> MultiLexicon:
        # Blocked grids always draw from a scored list (cw/scored); a plain-words
        # multi-lexicon has no use case, so we route every name through the scored
        # parser here (the length bucket is empty if the file has no such words).
        return MultiLexicon.from_scored_texts(
            lambda n: self._text(name, n), lengths, min_score=min_score, max_score=max_score
        )
