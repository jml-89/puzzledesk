"""Output adapters implementing ``app.ports.Writer``.

:class:`StreamWriter` writes lines to a text stream (stdout in production).
:class:`CapturingWriter` collects them in a list -- for tests, or for embedding a
generator in another program without spraying to stdout.
"""

from __future__ import annotations

import sys
from typing import TextIO


class StreamWriter:
    """Write one line at a time to a text stream (default: stdout)."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdout

    def line(self, text: str = "") -> None:
        self._stream.write(text + "\n")


class CapturingWriter:
    """Collect emitted lines instead of writing them -- test/embedding sink."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def line(self, text: str = "") -> None:
        self.lines.append(text)

    def text(self) -> str:
        """The captured output as one newline-joined string."""
        return "\n".join(self.lines)
