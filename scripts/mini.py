"""Shim: `uv run scripts/mini.py …` -> puzzledesk.cli.mini. Logic lives in the
package (typed, tested); this keeps the documented invocation working."""

from puzzledesk.cli.mini import main

if __name__ == "__main__":
    main()
