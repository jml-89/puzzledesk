"""Shim: `uv run scripts/puzzle.py …` -> puzzledesk.cli.puzzle. Logic lives in the
package (typed, tested); this keeps the documented invocation working."""

from puzzledesk.cli.puzzle import main

if __name__ == "__main__":
    main()
