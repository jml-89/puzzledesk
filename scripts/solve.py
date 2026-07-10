"""Shim: `uv run scripts/solve.py …` -> puzzledesk.cli.solve. Logic lives in the
package (typed, tested); this keeps the documented invocation working."""

from puzzledesk.cli.solve import main

if __name__ == "__main__":
    main()
