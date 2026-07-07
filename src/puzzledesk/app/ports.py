"""Driven ports the application layer needs from the outside world.

Hexagonal rule: the application *declares* the interfaces it needs; the
infrastructure (``adapters``) implements them. So these are ``Protocol``s owned by
``app``, referencing core types, with no filesystem or stdout in sight:

  * :class:`LexiconSource` -- "give me a lexicon / multi-lexicon for this named
    list, length(s), and quality bar". The one place file I/O used to leak into
    the kernel (``Lexicon.from_scored_file``); now the kernel only parses text and
    the *adapter* does the read.
  * :class:`Writer` -- the output sink, a line at a time. Keeps ``print``/stdout
    out of the services: a ``cli`` presenter formats a result and pushes lines
    through whatever ``Writer`` the composition root wired in (stdout in
    production, a capturing buffer under test).

The randomness port lives in the core (``core.rng``), because the engines -- not
the application -- are what consume it.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from ..core.lexicon import Lexicon, MultiLexicon


@runtime_checkable
class LexiconSource(Protocol):
    """Loads lexicons for a named word list (``"cw"``, ``"scored"``, ``"words"``).

    ``name`` selects the list family and its on-disk format; ``min_score`` applies
    the acceptance-bar filter (0.0 == the full list). The adapter owns the mapping
    from ``(name, length)`` to a file and the read; the kernel only parses.
    """

    def load(self, name: str, length: int, *, min_score: float = 0.0) -> Lexicon:
        """A single-length lexicon, filtered to words scoring >= ``min_score``."""
        ...

    def load_multi(
        self, name: str, lengths: Iterable[int], *, min_score: float = 0.0
    ) -> MultiLexicon:
        """A length-bucketed multi-lexicon (for blocked grids), bar-filtered."""
        ...


@runtime_checkable
class Writer(Protocol):
    """The output sink: one line at a time. A ``cli`` presenter formats results
    and writes them here, so services never touch stdout."""

    def line(self, text: str = "") -> None:
        """Emit one line (a trailing newline is added by the adapter)."""
        ...
