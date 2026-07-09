"""Structural difficulty of generated minis: where do the crossings go *open*? (benchmark)

Solves distinct minis at a score band, projects each to the canonical FilledGrid, and
runs ``app.difficulty.analyze`` against the *full* solving vocabulary (not the
generation-filtered list -- a solver knows every word, D20). An *open* crossing is a
cell whose shared letter neither crossing word pins: a Natick *risk*.

Openness and obscurity are orthogonal, and this is the point the driver makes: an open
crossing between two *common* words is fair (you get the words from their clues and the
crossing resolves), so the *unfair* Natick is open AND obscure. We flag a crossing
unfair only when *both* crossing words score below ``obscure_below`` (an absolute
per-list cutoff; on the cw scale higher == more common, so obscure == low).

    uv run scripts/difficulty.py [N] [listname] [min] [max] [obscure_below]   # square
    uv run scripts/difficulty.py blocked ROWS COLS NUM_BLACK [min] [obscure_below]

Two findings it demonstrates (see docs/notes.md):
  * Fully-checked squares: the open *rate* falls sharply with size (3x3 ~100%,
    5x5 ~38%) because openness is set by the *stem* length (word length - 1) -- longer
    words check each other better. Density (all cells crossed) is necessary but not
    sufficient; a 3x3 is maximally dense yet 100% open.
  * Blocked grids: black cells create short slots (3-letter), the weak-support pockets
    where Naticks concentrate -- the local "3x3 regime" inside a bigger grid.
"""

import sys

from puzzledesk.app.difficulty import analyze
from puzzledesk.app.puzzle import filled_from_blocked, filled_from_square
from puzzledesk.bootstrap import build
from puzzledesk.core.engines import backtrack, patterns
from puzzledesk.core.square import DoubleSquare

_OBSCURE = {"cw": 60.0, "scored": 3.0}  # per-list "below this is obscure" (cw: below "solid")


def _render(grid):
    return "\n".join(
        " ".join(
            "#" if grid.cells[r][c] is None else grid.cells[r][c].upper() for c in range(grid.cols)
        )
        for r in range(grid.rows)
    )


def _emit(grid, options, score_of, obscure_below, opens_per, unfair_per, bylen=None):
    """Analyze one FilledGrid (square or blocked), print it, accumulate the tallies.

    ``bylen`` (optional) collects ``(shorter_entry_length, is_open)`` per crossing, so a
    blocked run can report the open *rate* by the weak (shorter) side's length."""
    diff = analyze(grid, options)
    answer = {t.id: t.answer for t in grid.runs()}
    across = [t.answer for t in grid.runs() if t.kind == "A"]
    down = [t.answer for t in grid.runs() if t.kind == "D"]
    if bylen is not None:
        for c in diff.crossings:
            bylen.append((min(len(answer[c.across]), len(answer[c.down])), c.is_open))
    opens = diff.open_crossings
    # A Natick is an open crossing where *both* entries are obscure (neither the
    # vocabulary nor the crossing letter helps): max of the two scores < cutoff.
    unfair = [
        c
        for c in opens
        if max(score_of(answer[c.across]), score_of(answer[c.down])) < obscure_below
    ]
    opens_per.append(len(opens))
    unfair_per.append(len(unfair))
    rate = 100.0 * len(opens) / len(diff.crossings) if diff.crossings else 0.0
    print(f"\n{_render(grid)}")
    print(f"  across: {', '.join(across)}  |  down: {', '.join(down)}")
    print(
        f"  crossings: {len(diff.crossings)}  open: {len(opens)} ({rate:.0f}%)  "
        f"unfair: {len(unfair)}  max ambiguity: {diff.max_ambiguity}"
    )
    for c in sorted(opens, key=lambda c: -c.ambiguity):
        aw, dw = answer[c.across], answer[c.down]
        flag = " <- unfair (obscure)" if c in unfair else ""
        print(
            f"    cell {c.cell}: {aw}({score_of(aw):.0f}) x {dw}({score_of(dw):.0f})  "
            f"opts {c.across_options}/{c.down_options}{flag}"
        )


def _summary(opens_per, unfair_per):
    if not opens_per:
        print("\nno grid at this band (UNSAT or list too small)")
        return
    g = len(opens_per)
    print(
        f"\nsummary: {g} grids | open/grid avg {sum(opens_per) / g:.1f} "
        f"(min {min(opens_per)} max {max(opens_per)}) | "
        f"unfair/grid avg {sum(unfair_per) / g:.1f} (max {max(unfair_per)})"
    )


def report_square(container, n, listname, min_score, max_score, obscure_below, count=5, tries=300):
    full = container.lexicon.load(listname, n)  # the whole vocabulary a solver has
    band = f">= {min_score:g}" if max_score is None else f"in [{min_score:g}, {max_score:g}]"
    print(f"\n=== {n}x{n} fully-checked [{listname}] structural difficulty, score {band} ===")
    print(
        f"generation list: {len(full.filtered(min_score, max_score))} words; "
        f"solving vocabulary: {len(full)} words; obscure < {obscure_below:g}"
    )
    sq = DoubleSquare(full.filtered(min_score, max_score))
    opens_per, unfair_per, solved = [], [], 0
    for seed in range(tries):
        if solved >= count:
            break
        state = backtrack.solve(sq, rng=container.rng_factory.create(seed), distinct=True)
        if state is None:
            continue
        solved += 1
        _emit(
            filled_from_square(sq, state),
            lambda w, p: full.n_letters_at(w, p),
            lambda w: full.score_map.get(w, 0.0),
            obscure_below,
            opens_per,
            unfair_per,
        )
    _summary(opens_per, unfair_per)


def report_blocked(
    container, rows, cols, num_black, min_score, obscure_below, count=5, tries=400, min_len=3
):
    lengths = range(min_len, max(rows, cols) + 1)
    full = container.lexicon.load_multi("cw", lengths)  # full vocab, all lengths
    gen = container.lexicon.load_multi("cw", lengths, min_score=min_score)
    print(
        f"\n=== {rows}x{cols} blocked [cw] structural difficulty, {num_black} black, "
        f"score >= {min_score:g} ==="
    )
    print(
        f"solving vocabulary by length: "
        f"{ {n: len(full.get(n)) for n in lengths} }; obscure < {obscure_below:g}"
    )

    def options(word, pos):
        return full.get(len(word)).n_letters_at(word, pos)

    def score_of(word):
        return full.get(len(word)).score_map.get(word, 0.0)

    opens_per, unfair_per, bylen, solved = [], [], [], 0
    for seed in range(tries):
        if solved >= count:
            break
        found = patterns.fill_by_count(
            rows, cols, num_black, gen, rng_factory=container.rng_factory, seed=seed, distinct=True
        )
        if found is None:
            continue
        grid, assign = found
        solved += 1
        _emit(
            filled_from_blocked(grid, assign),
            options,
            score_of,
            obscure_below,
            opens_per,
            unfair_per,
            bylen,
        )
    _summary(opens_per, unfair_per)
    print("open rate by shorter-entry length (the weak side of each crossing):")
    for length in sorted({ln for ln, _ in bylen}):
        flags = [is_open for ln, is_open in bylen if ln == length]
        opened, total = sum(flags), len(flags)
        print(f"  len {length}: {opened:3d}/{total:3d} open ({100 * opened / total:.0f}%)")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "blocked":
        rows = int(args[1]) if len(args) > 1 else 5
        cols = int(args[2]) if len(args) > 2 else 5
        num_black = int(args[3]) if len(args) > 3 else 4
        min_score = float(args[4]) if len(args) > 4 else 60.0
        obscure_below = float(args[5]) if len(args) > 5 else _OBSCURE["cw"]
        report_blocked(build(), rows, cols, num_black, min_score, obscure_below)
    else:
        n = int(args[0]) if args else 5
        listname = args[1] if len(args) > 1 else "cw"
        min_score = float(args[2]) if len(args) > 2 else 90.0
        max_score = float(args[3]) if len(args) > 3 else None
        obscure_below = float(args[4]) if len(args) > 4 else _OBSCURE.get(listname, 60.0)
        report_square(build(), n, listname, min_score, max_score, obscure_below)
