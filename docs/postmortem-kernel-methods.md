# Post-mortem — the kernel-methods review spike (D31)

**Status: tombstoned.** A final review-of-methods spike over the pure kernel. Two
complete/deterministic experiments were built, measured, and **removed from the shipped
kernel with their findings recorded here** — this repo's tombstone discipline (D19, D28,
D29). Neither earns a durable place in the engine: the counter's value was a *one-time
measurement* (recorded below), and the prune *failed outright*. The code is one `git show`
away (spike commit `e8ed33f` on `claude/kernel-methods-review-on6ixx`); this document is the
canonical memory.

This is the reference to read before re-attempting either idea, and a synthesis of the whole
methods arc for anyone new to the kernel.

---

## TL;DR

- **Solution counting worked, and told us the space is tiny at the top.** The curated
  list's top tier (score ≥ 90) admits **exactly 38 distinct 5×5 minis** — a theorem, by
  exhaustive count. The weak (Zipf) list collapses **56 → 8 → 0** distinct minis as the bar
  rises, refining the ceiling to **between Zipf 3.7 and 3.9**. This is the *denominator*
  batch-variety reasoning was missing: at the top the distinct pool is small, which is *why*
  top-tier fills repeat. **The finding survives the tombstone; the code need not.**
- **Early distinctness pruning failed.** A sound "forced-down" prune cut only **~2% of
  search nodes and was time-neutral**. "Measure before optimising" answered No.
- **Nothing in the kernel changed.** `backtrack.py` has `solve` only, as before the spike.

---

## Part 1 — the methods arc (why the kernel looks the way it does)

Three problems, and the recurring lesson that *complete search fits the hard-bar packing,
soft sampling fits the geometry and the soft difficulty axis*.

**Fill (assign words to slots).** The original engine was an energy-based stochastic
sampler (min-conflicts / annealed Gibbs, D3), chosen for a *soft* quality objective. D6
killed that premise — quality became a **hard per-word bar**, i.e. feasibility on a
threshold-filtered list — and D7 measured complete propagation-backtracking beating the
sampler 64–450×, with the sampler's solve-rate *collapsing* on exactly the small/hard lists a
high bar produces. The sampler was **retired** (D19). Backtracking's decisive payoff is
epistemic: `None` is a **UNSAT theorem**, not a timeout.

**Layout (place the black cells).** Three engines, and the interesting reversal. Count-driven
orbit search (D13) → cap-driven row-major search (D24/D25, the reframe that made big minis
work: *cap the max entry length, don't grow the word lists*) → a **Gibbs field sampler**
(D27/D28) that *returned and won, scoped*: it guarantees no-2×2 (which the complete search
structurally cannot), spreads blacks better, and stays productive at the 12×12
phase-transition frontier where the complete search's budget collapses. D28 then showed the
connectivity-repair is *defeated by the cap* (a clean negative result). Net: **stochastic
sampling lost the fill and won the layout** — a soft field for the blacks, a complete CSP for
the words.

**Difficulty & solving.** Analytical (`analyze` static openness, `solve_order` cascade, D21/
D22) plus an empirical LLM-agent probe (D26). Headline: **difficulty = clue obliqueness on
known words (the fair, graded axis); word obscurity is a structural *cliff* — unknown ×
unknown = a Natick — not a slope.** Confirmed three ways (Opus reasoning-tokens, Haiku
failures, a vocabulary-floor Natick reproduced empirically).

The through-line — **"None is a proof"**, the hard/soft seam (D15 clue port, D21 difficulty),
and *measure-then-record* (D19/D28 tombstones) — is exactly the frame this spike was run and
tombstoned under.

---

## Part 2 — the spike: two complete/deterministic experiments

The arc above is well-recorded, which made the genuinely *unexplored* kernel gaps easy to
spot. Both live in the house regime (filter, prove, measure); both are pure `core`.

### A. Solution counting — how *large* is the SAT space?

**Why.** Every ceiling number in the repo is time-to-*first*-grid or a UNSAT proof; nobody had
asked how *large* the solution space is. open-questions flagged it ("How many distinct minis
exist at score ≥ X is unknown … a different, larger computation"), and it is load-bearing for
the one big remaining *product* question — **batch variety** (you cannot reason about "don't
repeat oreo/erie across a batch" without a denominator).

**What.** A `backtrack.count(sq, *, distinct=True, limit=None)` that walks the same complete
tree and counts distinct double word squares, returning `(n, exact, nodes)`. The `exact` bit
carries the house epistemics: `exact=True` ⇔ the tree was exhausted, so `n` is the **exact
total (a theorem)** — an exact `0` *is* a UNSAT proof reached by counting — while a `limit`
hit reports `exact=False` (`≥ n`, budget exhaustion, never dressed as exact). Deterministic
(a full count is order-independent, so no `rng`). Ground-truthed against `enumerate_squares`
on tiny lists (exhaustive `count` == distinct-filtered brute-force enumeration).

**Findings (measured this container).** The space **collapses to a countable set** at the
ceiling.

Weak (Zipf) list, N = 5:

| bar (T) | words | distinct minis | nodes | time |
|--------:|------:|:---------------|------:|-----:|
| 3.5 | 1972 | **exactly 56** | 572,703 | ~26.5 s |
| 3.7 | 1601 | **exactly 8**  | 197,297 | ~7.8 s |
| 3.9 | 1257 | **UNSAT (exactly 0)** | 60,479 | ~2.1 s |
| 4.0 | 1113 | **UNSAT (exactly 0)** | 39,126 | ~1.2 s |

This *refines* the earlier ceiling read ("5×5 tops out ~Zipf ≥ 3.5; 4.0 provably UNSAT"): the
exhaustive count puts the true edge **between 3.7 and 3.9** (3.9 is already UNSAT), and the
last SAT rungs are a mere 8, then 56, grids.

Curated (cw 0–100) list, N = 5:

| bar (T) | words | distinct minis | nodes | time |
|--------:|------:|:---------------|------:|-----:|
| 90 | 2384 | **exactly 38** | 702,999 | ~36.8 s |

So the curated **top tier (score ≥ 90) admits exactly 38 distinct 5×5 minis** — the
denominator behind the ceiling note's "25 seeds found 18 distinct" (25 random runs hit 18 of
the 38 that exist). Above 90 the list has only 3 words (trivially UNSAT); below the top tier
the space is astronomically large (single-threaded Python walks ~40k nodes/s, so exhaustive
counting there is infeasible — you cap and report `≥`).

**Verdict: tombstoned, finding survives.** The counter *worked* — but its deliverable was a
*measurement*, and once the numbers are recorded, the code that produced them earns no
permanent place in the shipped kernel (D19's line: an idea can earn its place in the *arc*
without earning an *operational* place in the system). The batch-variety denominator (**38 at
the top tier**) is now known independently of the code. If counting is wanted again — the
blocked/`fill` space, or counting up to symmetry class for a bigger space — restore `count`
from git and extend it; you start from this verdict, not from scratch.

### B. Early distinctness pruning — the named perf follow-up

**Why.** Distinctness is the known inefficiency (~13 ms → 380 ms at 5×5): the down words are
only complete at the last row, so duplicates are caught *late*, at the `r == N` leaf.
open-questions asked whether we can "detect when a partial column can only complete to an
already-used word … measure before optimising."

**What.** A **forced-down prune**: if a column's partial prefix admits exactly *one* column
word, that down word is already *determined*, so if it is already an across word (or two
columns are forced to the same word) no distinct leaf exists below — reject at depth instead
of at the leaf. Sound (removes only branches with no distinct leaf; first-solution order and
the count are both unchanged). Counting exhausts the tree, which makes `nodes` the exact,
deterministic instrument for judging it.

**Findings.** It cut only **~2% of search nodes (2.1% weak, 2.6% curated), and was
time-neutral.** The forced-down condition almost never fires early — with hundreds/thousands
of words a column prefix stays multiply-completable until deep in the tree, by which point the
existing leaf check catches the duplicate anyway.

**Verdict: dropped.** A ~2%, time-neutral optimisation buys nothing its purpose (speed) wants.
Per D19/D28/D29, it is removed with the number recorded rather than kept as a rotting
off-by-default knob on the public signatures. "Measure before optimising" answered **No** —
which is the point of measuring first.

---

## Part 3 — what survives, what's still open

- **Survives (as recorded fact):** the solution-space *sizes* — 38 distinct minis at cw ≥ 90;
  the weak-list 56 → 8 → 0 collapse; the refined weak-list ceiling (edge between Zipf 3.7 and
  3.9). These are properties of the *data* (re-measure if the curated list updates upstream).
- **Still open:** counting the **blocked/`fill`** space (same pattern over `fill.solve`, when
  batch-variety wants a per-shape denominator); counting **up to symmetry class** if a larger
  space ever needs exhausting; and the broader batch-variety scheduler that a per-tier
  denominator now informs (see open-questions "Grid variety").
- **Dead ends (do not re-attempt without new information):** the forced-down early
  distinctness prune (measured, ~2%, time-neutral).

## Resurrection

The counter, `SolutionCount`, `scripts/count.py`, `tests/test_count.py`, and the
`early_distinct` prune (`_ForcedDown`/`_distinct_dead`) are all in git at spike commit
`e8ed33f`. `git show e8ed33f` or `git checkout e8ed33f -- <path>` brings any of them back. The
measurement is the memory; the code is recoverable but not carried.
