"""Experiment (D24): does a solver's *reasoning effort* track puzzle difficulty?

For a model that solves every mini, whether it finishes is a saturated signal; the tell
is *how much it had to think*. This driver sweeps a difficulty lever and reports the
solver's thinking-token spend, holding the grid fixed so only the lever moves.

    uv run --extra clue scripts/solve_effort.py                       # opus, mon vs sat, seeds 0-1
    uv run --extra clue scripts/solve_effort.py --seeds 0 1 2 --model claude-haiku-4-5-20251001
    uv run --extra clue scripts/solve_effort.py --policy cell monday saturday

For a fixed seed the *fill* is identical across clue difficulties (the grid is filled
before it is clued), so monday vs saturday differ only in the clues -- a clean read on
whether harder clues cost the solver more reasoning. Under `--policy none` the solver
gets no feedback, so the whole burden is on reasoning. It is a probe, not a proof:
thinking-token counts are noisy (clue generation and solving are both stochastic), so
read trends over a few seeds, not single cells.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace

from puzzledesk.app.clue import Difficulty
from puzzledesk.app.solve import FeedbackPolicy
from puzzledesk.bootstrap import Config, build


def _parse_args(argv):
    p = argparse.ArgumentParser(prog="solve_effort")
    p.add_argument("difficulties", nargs="*", default=["monday", "saturday"])
    p.add_argument("--seeds", type=int, nargs="+", default=[0, 1])
    p.add_argument("--black", type=int, default=4)
    p.add_argument("--min-score", type=float, default=75.0)
    p.add_argument("--max-score", type=float, default=None, help="obscurity-band upper bar")
    p.add_argument("--policy", default="none", choices=[p.value for p in FeedbackPolicy])
    p.add_argument("--model", default=None, help="solver model id (default: config's opus)")
    p.add_argument("--thinking", default=None, choices=["adaptive", "enabled", "off"])
    p.add_argument("--max-turns", type=int, default=8)
    return p.parse_args(argv)


def main(argv=None):
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    config = Config.default()
    if args.model is not None:
        config = replace(config, solve_model=args.model)
    if args.thinking is not None:
        config = replace(config, solve_thinking=args.thinking)
    c = build(config)
    policy = FeedbackPolicy(args.policy)

    print(
        f"model={config.solve_model} policy={args.policy} "
        f"black={args.black} min_score={args.min_score:.0f}"
    )
    cols = ("difficulty", "seed", "solved", "turns", "wrong", "think_tok")
    print(f"{cols[0]:<10} {cols[1]:>4} {cols[2]:>6} {cols[3]:>5} {cols[4]:>5} {cols[5]:>9}")
    for difficulty in args.difficulties:
        diff = Difficulty[difficulty.upper()]
        for seed in args.seeds:
            puzzle = c.puzzle.generate(
                rows=5,
                cols=5,
                num_black=args.black,
                min_score=args.min_score,
                max_score=args.max_score,
                difficulty=diff,
                seed=seed,
            )
            if puzzle is None:
                print(f"{difficulty:<10} {seed:>4}  (no puzzle at this bar)")
                continue
            report = c.solve.solve(puzzle, policy=policy, max_turns=args.max_turns)
            tok = report.total_reasoning_tokens
            tok_s = "?" if tok is None else str(tok)
            print(
                f"{difficulty:<10} {seed:>4} {report.solved!s:>6} {report.n_turns:>5} "
                f"{report.wrong_guesses:>5} {tok_s:>9}"
            )


if __name__ == "__main__":
    main()
