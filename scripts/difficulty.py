"""Structural difficulty of generated minis: where do the crossings go *open*? (benchmark)

Solves distinct minis at a score band, projects each to the canonical FilledGrid, and
runs ``app.difficulty.analyze`` against the *full* solving vocabulary (not the
generation-filtered list -- a solver knows every word, D20). An *open* crossing is a
cell whose shared letter neither crossing word pins: a Natick *risk*.

Openness and obscurity are orthogonal, and this is the point the driver makes: an open
crossing between two *common* words is fair (you get the words from their clues and the
crossing resolves), so the *unfair* Natick is open AND obscure. We flag a crossing
unfair only when a crossing word's score is below ``obscure_below`` (an absolute
per-list cutoff; on the cw scale higher == more common, so obscure == low).

    uv run scripts/difficulty.py [N] [listname] [min_score] [max_score] [obscure_below]

At a top-tier bar (cw score>=90) grids have open crossings but ~no unfair ones (the
words are common); pushing generation into an obscure band surfaces real Naticks.
Numbers go to docs/notes.md.
"""

import sys

from puzzledesk.app.difficulty import analyze
from puzzledesk.app.puzzle import filled_from_square
from puzzledesk.bootstrap import build
from puzzledesk.core.engines import backtrack
from puzzledesk.core.square import DoubleSquare


def report(container, n, listname, min_score, max_score, obscure_below, count=5, tries=300):
    full = container.lexicon.load(listname, n)  # the whole vocabulary a solver has
    band = f">= {min_score:g}" if max_score is None else f"in [{min_score:g}, {max_score:g}]"
    print(f"\n=== N={n} [{listname}] structural difficulty, score {band} ===")
    lex = full.filtered(min_score, max_score)
    print(
        f"generation list: {len(lex)} words; solving vocabulary: {len(full)} words; "
        f"obscure < {obscure_below:g}"
    )
    sq = DoubleSquare(lex)

    def options(answer, pos):
        return full.n_letters_at(answer, pos)

    solved, opens_per, unfair_per = 0, [], []
    for seed in range(tries):
        if solved >= count:
            break
        state = backtrack.solve(sq, rng=container.rng_factory.create(seed), distinct=True)
        if state is None:
            continue
        solved += 1
        diff = analyze(filled_from_square(sq, state), options)
        answers = [sq.rows.words[i] for i in state] + sq.column_strings(state)
        score = {w: full.score_map.get(w, 0.0) for w in answers}
        opens = diff.open_crossings
        # A Natick is an open crossing where *both* entries are obscure (neither the
        # vocabulary nor the crossing letter helps): max of the two scores < cutoff.
        unfair = [
            c
            for c in opens
            if max(score[_word(sq, state, c.across)], score[_word(sq, state, c.down)])
            < obscure_below
        ]
        opens_per.append(len(opens))
        unfair_per.append(len(unfair))
        print(f"\n{sq.render(state)}")
        print(
            f"  across: {', '.join(sq.rows.words[i] for i in state)}"
            f"  |  down: {', '.join(sq.column_strings(state))}"
        )
        print(
            f"  crossings: {len(diff.crossings)}  open: {len(opens)}  "
            f"unfair: {len(unfair)}  max ambiguity: {diff.max_ambiguity}"
        )
        for c in sorted(opens, key=lambda c: -c.ambiguity):
            aw, dw = _word(sq, state, c.across), _word(sq, state, c.down)
            flag = " <- unfair (obscure)" if c in unfair else ""
            print(
                f"    cell {c.cell}: {aw}({score[aw]:.0f}) x {dw}({score[dw]:.0f})  "
                f"opts {c.across_options}/{c.down_options}{flag}"
            )

    if opens_per:
        n_grids = len(opens_per)
        print(
            f"\nsummary: {n_grids} grids | open/grid avg {sum(opens_per) / n_grids:.1f} "
            f"(min {min(opens_per)} max {max(opens_per)}) | "
            f"unfair/grid avg {sum(unfair_per) / n_grids:.1f} (max {max(unfair_per)})"
        )
    else:
        print("\nno grid at this band (UNSAT or list too small)")


def _word(sq, state, target_id):
    """Recover the answer string for a target id ((start_cell, kind)) in a square."""
    (r, c), kind = target_id
    return sq.rows.words[state[r]] if kind == "A" else sq.column_strings(state)[c]


_OBSCURE = {
    "cw": 60.0,
    "scored": 3.0,
}  # per-list "below this is obscure" default (cw: below "solid")


if __name__ == "__main__":
    args = sys.argv[1:]
    n = int(args[0]) if args else 5
    listname = args[1] if len(args) > 1 else "cw"
    min_score = float(args[2]) if len(args) > 2 else 90.0
    max_score = float(args[3]) if len(args) > 3 else None
    obscure_below = float(args[4]) if len(args) > 4 else _OBSCURE.get(listname, 50.0)
    report(build(), n, listname, min_score, max_score, obscure_below)
