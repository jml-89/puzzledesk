"""Shim: `uv run scripts/generate.py …` -> puzzledesk.cli.generate. Logic lives in
the package (typed, tested); this keeps the documented invocation working."""

from puzzledesk.cli.generate import main

if __name__ == "__main__":
    main()
