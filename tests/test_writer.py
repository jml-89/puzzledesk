"""The ``app.ports.Writer`` adapter (adapters/writer.py), as a unit test.

DI, not integration: the text stream is an injected ``io.StringIO``, so the adapter
is exercised with no real stdout. It verifies the one contract -- ``line`` appends a
newline, and an empty call writes a bare newline (a blank separator line).
"""

from __future__ import annotations

import io

from puzzledesk.adapters.writer import StreamWriter


def test_line_writes_text_with_a_trailing_newline() -> None:
    buf = io.StringIO()
    StreamWriter(buf).line("hello")
    assert buf.getvalue() == "hello\n"


def test_line_with_no_argument_writes_a_blank_line() -> None:
    buf = io.StringIO()
    w = StreamWriter(buf)
    w.line("a")
    w.line()  # a separator
    w.line("b")
    assert buf.getvalue() == "a\n\nb\n"
