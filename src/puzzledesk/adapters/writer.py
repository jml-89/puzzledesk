"""Output adapters implementing ``app.ports.Writer``.

:class:`StreamWriter` writes lines to a text stream (stdout in production).
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
