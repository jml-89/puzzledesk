"""Tool: generate a complete, *clued* puzzle and present it as plain text to solve.

    uv run puzzle
    uv run puzzle --rows 5 --cols 5 --black 4 --min-score 75 --difficulty wednesday
    uv run puzzle --black 2 --difficulty saturday --reveal
    uv run scripts/puzzle.py --nonsymmetric --seed 3

This is the *developer* front end -- the quick, plain-text way to eyeball a whole
puzzle (blank numbered grid + Across/Down clues). The richer, solver-facing surface
will be a web server with its own entry point; this stays a thin terminal path.

Every knob is a **named flag**, not a positional argument, on purpose: unlike
``add(a, b)`` these arguments share no common semantic -- rows, a black-cell count, a
score bar, and a difficulty are different *kinds* of thing, and ``puzzle 5 5 4 75 3``
reads as line noise. ``--rows`` / ``--black`` / ``--min-score`` say what they mean at
the call site, and argparse gives ``--help`` and validation for free.

Thin by contract (like ``mini``/``generate``): parse argv, build the container, run
:class:`~puzzledesk.app.puzzle_service.PuzzleService`, present. Clue generation is the
one live step -- it needs the ``clue`` extra and a key (see ``Config.clue_api_key_env``);
the grid search itself has no LLM dependency.
"""

from __future__ import annotations

import argparse
import sys

from ..app.clue import Difficulty
from ..bootstrap import Container, build
from . import present

_DIFFICULTIES = [d.name.lower() for d in Difficulty]  # monday..saturday


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="puzzle",
        description="Generate a complete clued mini crossword and print it to solve.",
    )
    p.add_argument("--rows", type=int, default=5, help="grid rows (default: 5)")
    p.add_argument("--cols", type=int, default=5, help="grid columns (default: 5)")
    p.add_argument(
        "--black",
        type=int,
        default=4,
        metavar="N",
        help="number of black cells to place (default: 4)",
    )
    p.add_argument(
        "--min-score",
        type=float,
        default=75.0,
        metavar="SCORE",
        help="quality bar: every word scores >= this on the cw list (default: 75)",
    )
    p.add_argument(
        "--max-score",
        type=float,
        default=None,
        metavar="SCORE",
        help="upper bar: makes the fill an obscurity band [min, max] for a harder puzzle "
        "(default: none)",
    )
    p.add_argument(
        "--difficulty",
        choices=_DIFFICULTIES,
        default="wednesday",
        help="clue difficulty, NYT-week named (default: wednesday)",
    )
    p.add_argument(
        "--instructions",
        default="",
        metavar="TEXT",
        help="free-form clue guidance passed to the provider (tone, theme, taboo words)",
    )
    p.add_argument("--seed", type=int, default=0, help="RNG seed for the fill (default: 0)")
    p.add_argument(
        "--symmetric",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="require 180-degree-symmetric black cells (default: on; --no-symmetric to drop it)",
    )
    p.add_argument(
        "--reveal",
        action="store_true",
        help="also print the answer key (the filled grid) below the puzzle",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    _run(build(), args)


def _run(c: Container, args: argparse.Namespace) -> None:
    puzzle = c.puzzle.generate(
        rows=args.rows,
        cols=args.cols,
        num_black=args.black,
        min_score=args.min_score,
        max_score=args.max_score,
        difficulty=Difficulty[args.difficulty.upper()],
        instructions=args.instructions,
        seed=args.seed,
        symmetric=args.symmetric,
    )
    if puzzle is None:
        _explain_no_puzzle(c, args)
        return
    present.playable(puzzle, c.writer)
    if args.reveal:
        c.writer.line()
        c.writer.line("Answer key:")
        present.solution(puzzle.grid, c.writer)


def _explain_no_puzzle(c: Container, args: argparse.Namespace) -> None:
    """A ``None`` puzzle is a theorem, not a failure -- word *which* one. Either no
    legal layout exists for the shape at all, or legal layouts exist but none fills
    above the bar (complete search, so one attempt settles it)."""
    w = c.writer.line
    kind = "symmetric" if args.symmetric else "non-symmetric"
    if not c.blocked.layout_exists(args.rows, args.cols, args.black, symmetric=args.symmetric):
        w(
            f"no legal {args.black}-black layout exists for a {kind} {args.rows}x{args.cols} "
            f"grid (min-length{' or symmetry' if args.symmetric else ''} forbids it)."
        )
    else:
        w(
            f"legal layouts exist, but none fills at score >= {args.min_score:.0f}. "
            "Try a lower --min-score."
        )


if __name__ == "__main__":
    main()
