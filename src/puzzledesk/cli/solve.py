"""Tool: generate a clued puzzle, then have a Claude agent try to *solve* it, and
print the attempt -- including the agent's turn-by-turn reasoning (D24).

    uv run solve
    uv run solve --difficulty saturday --policy crossing --reveal
    uv run scripts/solve.py --black 2 --max-turns 20

This is the experimental difficulty probe: put a real solver in a feedback loop and
watch it. Two things make it a difficulty signal -- *whether* the agent completed the
grid, and *how it reasoned* to get there (or where it stalled). Compare that against
the analytical ``difficulty.solve_order`` model (``scripts/difficulty.py``): a solver
stalling where the model predicts a bottleneck is the model earning its keep.

Two live steps here (both need the ``clue`` extra + a key, see ``Config.clue_api_key_env``):
the clue generation to make a solvable puzzle, and the solving agent itself. The grid
*fill* has no LLM dependency. ``--policy`` is the solver-skill knob (cell/word/crossing/
none); ``cell`` (autocheck-on) is the default and the gentlest -- ``crossing``/``none``
are the sharper probes.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace

from ..app.clue import Difficulty
from ..app.solve import FeedbackPolicy
from ..bootstrap import Config, Container, build
from . import present

_DIFFICULTIES = [d.name.lower() for d in Difficulty]
_POLICIES = [p.value for p in FeedbackPolicy]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="solve",
        description="Generate a clued mini and have a Claude agent try to solve it.",
    )
    p.add_argument("--rows", type=int, default=5, help="grid rows (default: 5)")
    p.add_argument("--cols", type=int, default=5, help="grid columns (default: 5)")
    p.add_argument(
        "--black", type=int, default=4, metavar="N", help="black cells to place (default: 4)"
    )
    p.add_argument(
        "--min-score",
        type=float,
        default=75.0,
        metavar="SCORE",
        help="quality bar for the fill (default: 75)",
    )
    p.add_argument(
        "--max-score",
        type=float,
        default=None,
        metavar="SCORE",
        help="upper bar: makes the fill an obscurity band [min, max] -- harder words so the "
        "clues alone are insufficient and the grid carries the solve (default: none)",
    )
    p.add_argument(
        "--difficulty",
        choices=_DIFFICULTIES,
        default="wednesday",
        help="clue difficulty the puzzle is written at (default: wednesday)",
    )
    p.add_argument(
        "--policy",
        choices=_POLICIES,
        default=FeedbackPolicy.CELL.value,
        help="feedback the solver gets each turn -- the solver-skill knob (default: cell)",
    )
    p.add_argument(
        "--max-turns", type=int, default=None, metavar="N", help="solver turn budget (default: 12)"
    )
    p.add_argument(
        "--model",
        default=None,
        metavar="ID",
        help="solver model id (default: claude-opus-4-8) -- pit a weaker model to grade "
        "difficulty by reasoning spent",
    )
    p.add_argument(
        "--effort",
        default=None,
        choices=["low", "medium", "high"],
        help="adaptive-thinking effort for the solver (default: high)",
    )
    p.add_argument(
        "--thinking",
        default=None,
        choices=["adaptive", "enabled", "off"],
        help="thinking mode: adaptive (Opus 4.x), enabled (Haiku 4.x), or off (default: adaptive)",
    )
    p.add_argument("--seed", type=int, default=0, help="RNG seed for the fill (default: 0)")
    p.add_argument(
        "--symmetric",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="require 180-degree-symmetric black cells (default: on)",
    )
    p.add_argument(
        "--reveal", action="store_true", help="also print the answer key below the attempt"
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    config = Config.default()
    if args.model is not None:
        config = replace(config, solve_model=args.model)
    if args.effort is not None:
        config = replace(config, solve_effort=args.effort)
    if args.thinking is not None:
        config = replace(config, solve_thinking=args.thinking)
    _run(build(config), args)


def _run(c: Container, args: argparse.Namespace) -> None:
    puzzle = c.puzzle.generate(
        rows=args.rows,
        cols=args.cols,
        num_black=args.black,
        min_score=args.min_score,
        max_score=args.max_score,
        difficulty=Difficulty[args.difficulty.upper()],
        seed=args.seed,
        symmetric=args.symmetric,
    )
    if puzzle is None:
        c.writer.line(
            f"no puzzle to solve: nothing fills a {args.black}-black {args.rows}x{args.cols} "
            f"grid at score >= {args.min_score:.0f} (try a lower --min-score or fewer --black)."
        )
        return
    report = c.solve.solve(puzzle, policy=FeedbackPolicy(args.policy), max_turns=args.max_turns)
    present.solve_report(report, c.writer)
    if args.reveal:
        c.writer.line()
        c.writer.line("Answer key:")
        present.solution(puzzle.grid, c.writer)


if __name__ == "__main__":
    main()
