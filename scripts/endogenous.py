"""Endogenous cluing: does a real solver's effort track the RELATIONAL model? (live spike)

The relational model (`scripts/relational.py`) predicts that a mini's difficulty is a
property of the crossing graph and the *clue-power vector* -- which entries get a useful
(gimme) clue -- not of the words. Its sharp, falsifiable prediction:

  * **All clues useful** -> depth 1: the solver treats the grid as ten independent trivia
    lookups (the D26 finding), the interlock a mere formality. Low reasoning.
  * **Only the information-floor clues useful, the rest REDACTED** -> the solver must recover
    the redacted answers from crossing letters alone -- pure internal puzzle logic, no
    trivia. The grid *carries* the solve. Higher reasoning; still solvable (by construction).
  * **Below the floor** -> deadlock: the redacted answers form a Natick cluster no crossings
    can force. The solver should fail (or flail), and fail at the predicted cells.

A redacted (blank) clue is the purest *endogenous* clue: the answer is determined by the
puzzle's own logic, not by outside knowledge. This driver builds the three regimes on ONE
generated grid (precise Monday clues, so an un-redacted clue really is a gimme) and runs the
live Claude solver on each, reporting thinking-token spend -- closing the analytical<->
empirical loop the notes leave open.

    uv run --extra clue scripts/endogenous.py            # one blocked 5x5, seed 1
    uv run --extra clue scripts/endogenous.py --seed 3 --black 4
"""

from __future__ import annotations

import argparse
import sys

from puzzledesk.app.clue import ClueStyle, Difficulty
from puzzledesk.app.cluing import CluedPuzzle
from puzzledesk.app.solve import FeedbackPolicy
from puzzledesk.app.spec import CountLayout, GridSpec, PuzzleSpec
from puzzledesk.bootstrap import build
from relational import _entries, difficulty_curve, information_floor, propagate


def _redacted(puzzle: CluedPuzzle, keep: set) -> CluedPuzzle:
    """A copy of ``puzzle`` whose clues survive only for entries in ``keep`` (by TargetId).
    A dropped clue reads as blank to the solver -- an honest 'recover this from the grid'."""
    clues = {tid: c for tid, c in puzzle.clues.items() if tid in keep}
    return CluedPuzzle(grid=puzzle.grid, clues=clues, unclued=puzzle.unclued)


def _labels(entries, ids):
    m = {e.eid: e.label for e in entries}
    return sorted(m[i] for i in ids)


def main(argv=None):
    p = argparse.ArgumentParser(prog="endogenous")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--black", type=int, default=4)
    p.add_argument("--min-score", type=float, default=75.0)
    p.add_argument("--rows", type=int, default=5)
    p.add_argument("--cols", type=int, default=5)
    p.add_argument("--max-turns", type=int, default=6)
    args = p.parse_args(sys.argv[1:] if argv is None else argv)

    c = build()
    # Monday = precise clues, so an un-redacted clue is a genuine gimme (model assumption).
    spec = PuzzleSpec(
        grid=GridSpec(rows=args.rows, cols=args.cols, min_score=args.min_score, seed=args.seed),
        layout=CountLayout(num_black=args.black),
        clue=ClueStyle(difficulty=Difficulty.MONDAY),
    )
    print(f"generating+cluing (Monday) {args.rows}x{args.cols} {args.black}b seed {args.seed} ...")
    puzzle = c.puzzle.generate(spec)
    if puzzle is None:
        print("no puzzle at this bar")
        return

    grid = puzzle.grid
    entries = _entries(grid)
    lengths = range(3, max(args.rows, args.cols) + 1)
    full = c.lexicon.load_multi("cw", lengths)
    nc = lambda a, k: full.get(len(a)).n_candidates(a, k)  # noqa: E731

    floor_set, floor_depth = information_floor(entries, nc)
    curve = difficulty_curve(entries, nc)

    print("\n--- relational model (prediction) ---")
    for e in entries:
        clue = puzzle.clues.get(e.eid)
        print(f"  {e.label:>3} = {e.answer.upper():<6} clue: {clue.text if clue else '(unclued)'}")
    print(
        f"  information floor: {len(floor_set)}/{len(entries)} clues {_labels(entries, floor_set)} "
        f"-> depth {floor_depth}"
    )
    print(
        "  difficulty curve k:depth  "
        + " ".join(f"{k}:{'x' if d is None else d}" for k, d in curve)
    )

    all_ids = {e.eid for e in entries}
    # Below-floor: drop one more floor clue -> should deadlock (predict the stuck set).
    drop = sorted(floor_set)[0]
    below = set(floor_set) - {drop}
    below_prop = propagate(entries, below, nc)
    print(
        f"  below-floor stuck (predicted unsolvable cluster): {_labels(entries, below_prop.stuck)}"
    )

    regimes = [
        ("all-clues (trivia bag)", all_ids, 1),
        (f"floor-only ({len(floor_set)} clues, rest endogenous)", set(floor_set), floor_depth),
        (f"below-floor ({len(below)} clues)", below, None),
    ]
    print("\n--- live solver (claude, --policy none) ---")
    print(f"{'regime':<42} {'pred':>5} {'solved':>7} {'turns':>6} {'think_tok':>10}")
    for name, keep, pred in regimes:
        variant = _redacted(puzzle, keep)
        report = c.solve.solve(variant, policy=FeedbackPolicy.NONE, max_turns=args.max_turns)
        tok = report.total_reasoning_tokens
        predtxt = "dead" if pred is None else f"d{pred}"
        if pred is None:
            predtxt = f"dead({len(below_prop.stuck)})"
        print(
            f"{name:<42} {predtxt:>5} {report.solved!s:>7} {report.n_turns:>6} "
            f"{('?' if tok is None else tok):>10}"
        )


if __name__ == "__main__":
    main()
