"""Generate NYT-mini-style 5x5 double word squares from the curated list.

Every one of the ten words (5 across + 5 down) is distinct and scores at or
above the target quality bar. Usage:

    python3 scripts/mini.py [N] [min_score] [count]
    python3 scripts/mini.py 5 70 3
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from puzzledesk import backtrack
from puzzledesk.lexicon import Lexicon
from puzzledesk.square import DoubleSquare
from puzzledesk.validate import validate

DATA = Path(__file__).resolve().parent.parent / "data"


def render(sq, state):
    across = [sq.rows.words[i] for i in state]
    down = sq.column_strings(state)
    grid = "\n".join("  " + " ".join(c.upper() for c in w) for w in across)
    a = ", ".join(f"{w}({sq.rows.score_map[w]:.0f})" for w in across)
    d = ", ".join(f"{w}({sq.cols.score_map[w]:.0f})" for w in down)
    return grid, a, d


def main(n=5, min_score=70.0, count=3):
    lex = Lexicon.from_scored_file(DATA / f"cw_{n}.txt", length=n).filtered(min_score)
    sq = DoubleSquare(lex)
    print(f"{n}x{n} minis, every word score >= {min_score:.0f} "
          f"(from {len(lex)} eligible words)\n")
    shown = 0
    for seed in range(count * 20):
        state = backtrack.solve(sq, seed=seed, distinct=True)
        if state is None:
            continue
        v = validate(sq, state, min_score)
        assert v.ok, v
        grid, a, d = render(sq, state)
        print(grid)
        print(f"  across: {a}")
        print(f"  down:   {d}")
        print(f"  weakest word: {v.weakest[0]} ({v.weakest[1]:.0f})\n")
        shown += 1
        if shown >= count:
            break
    if shown == 0:
        print("no grid at this bar (try a lower min_score)")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    ms = float(sys.argv[2]) if len(sys.argv) > 2 else 70.0
    c = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    main(n, ms, c)