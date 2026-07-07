# Architecture and invariants

Audience: an agent modifying this codebase. This documents the data model, the
invariants you must not break, the two engines, and the non-obvious details that
are easy to get wrong. Read `docs/decisions.md` for *why* it is shaped this way
and `docs/notes.md` for benchmarks/environment.

## Object being generated

A double word square of order N: an N x N grid, fully checked (no black cells),
where the N across (row) words and the N down (column) words are all real words.
The canonical NYT mini is N=5. A *valid* grid additionally must be *acceptable*:
see the acceptance test below.

Note the distinction: a symmetric grid (mirror across the main diagonal) has
across == down and is only a *word square*, not a genuine *double* word square.
We forbid that; see "distinctness invariant".

## Core representation (src/puzzledesk/square.py)

`state` is a 1-D numpy int array of length N. `state[i]` is an index into the
ROW lexicon's `words`/`letters`, naming the across word in row i. That is the
entire mutable state. Everything else is derived:

- `sq.grid(state)` -> (N,N) uint8 letter-index grid = `rows.letters[state]`.
- down word j = the string read down column j = `decode(grid[:, j])`.
- `energy(state)` = number of columns whose induced string is NOT in the column
  lexicon's wordset. `energy == 0` <=> every column is a real word <=> valid
  double word square (modulo acceptance).

Why state is only the across words: it makes the down words *induced* rather than
independently chosen, collapsing a 25-cell CSP into a 5-variable one and making
validity a handful of set lookups. This is load-bearing; do not "generalise" it
to a 25-cell representation without a strong reason.

`DoubleSquare(rows, cols=None)`: `rows` and `cols` are Lexicons. `cols` defaults
to `rows`, and in all current usage across and down draw from the SAME lexicon.
The code paths for `cols != rows` exist but are untested; if you use different
lexicons, re-verify. `rows.n == cols.n` is required.

## Lexicon (src/puzzledesk/lexicon.py)

Words of a single fixed length N. Three representations, each for a query shape:

- `wordset` (Python set): O(1) "is this string a word", used for column checks.
- `letters` (M,N uint8): letter indices 0..25, one row per word. Vectorised
  per-position pattern queries.
- `scores` (M float) + `score_map` (dict word->score): per-word quality.

Key methods:
- `from_file(path, length)`: plain word-per-line, scores default to 0.
- `from_scored_file(path, length)`: "word score" per line. BOTH data list
  families use this (see score-scale gotcha below).
- `filtered(min_score)`: sub-lexicon of words with score >= min_score. This is
  how a quality bar is applied: filter, then solve feasibility.
- `allowed_at(pattern)`: pattern is length-N with exactly one `None`; returns a
  26-bool mask of letters that fill the blank to make a real word. The per-cell
  "which letters keep this column alive" marginal.
- `allowed_and_scores_at(pattern)`: same, plus a 26-float array of the resulting
  word's score per letter (0 where invalid). Used by the sampler's quality move.
- `words_matching(allowed)`: allowed is a length-N list of 26-bool masks; returns
  indices of words whose letter at every position is permitted. The bitset-style
  intersection the backtracker uses to get legal row words directly.
- `matching(pattern)`: pattern is length-N of `int|None` (fixed letters + blanks,
  any number of blanks); returns indices of words that fit. The per-slot query for
  blocked-grid fill.

`MultiLexicon` (same file) buckets a `Lexicon` per length for blocked grids, whose
slots differ in length; `MultiLexicon.from_scored_files(path_for, lengths, bar)`
loads and bar-filters each length, keeping empty lengths as an unfillable bucket.

encode/decode map lowercase word <-> uint8 index array. `encode` uses
`np.frombuffer(word.encode('ascii'))` so inputs must be lowercase ascii a-z.

## The two engines

### backtrack.py — the PRIMARY engine, complete

`solve(sq, seed=0, randomize=True, distinct=True) -> state | None`.

Fills rows top to bottom. Before placing row r, each partial column
`cols[j]` (r letters so far) must remain a live prefix of some column word. A
`_PrefixIndex` over `sq.cols` maps prefix -> 26-bool mask of legal next letters.
Intersecting those masks against the row lexicon via `words_matching` yields
exactly the legal row words at depth r (no scan-and-reject). `randomize`
shuffles that candidate list per seed for grid diversity; it does NOT affect
completeness.

Completeness: if `solve` returns None, the search exhausted the tree and NO
acceptable grid exists for these lexicons at this filtering. That is a proof of
UNSAT, not a timeout. One run settles existence; multiple seeds only vary which
solution you get and measure diversity/timing.

`distinct=True` enforces the distinctness invariant (below): skips a candidate
whose across word is already used, and at the leaf (r==N) rejects the grid if the
N down words are not mutually distinct or collide with an across word.

### sampler.py — the SECONDARY engine (energy-based / stochastic)

`solve(sq, temperature=0.0, quality=0.0, distinct=False, guided=True,
max_steps, max_restarts, seed) -> Result`. Min-conflicts / annealed-Gibbs: from a
random filled grid, repeatedly re-choose one row's word to minimise invalid
columns. `_row_objective` scores every candidate row word by `BIG*(#columns made
valid) + quality*(across score + induced down scores) - DUP_WEIGHT*(#duplicate
word-pairs)`; `BIG` guarantees feasibility dominates both quality and
distinctness. `quality` folds word frequency into the move; `temperature>0`
samples instead of greedy. `Result` has `.state .energy .solved .steps .restarts`.

DISTINCTNESS (`distinct=True`): the sampler now enforces the distinctness
invariant, so it produces genuine double word squares (not just the raw-packing
default). `_distinct_penalty` computes, vectorised, the number of duplicate
word-pairs for every candidate row word (real words share ids via a string->id
map; throwaway non-words get fresh per-step ids), and the move subtracts
`DUP_WEIGHT` times that. The penalty is gated to near-feasible steps (`<=1`
invalid column) because it rebuilds N*26 column strings — with more invalid
columns `BIG*feasibility` dominates the argmax anyway. `guided=True` (default)
uses that penalty to walk off the symmetric basin; `guided=False` is the naive
"gate" baseline that just restarts on a degenerate valid grid (the basin is a
fixed point of the unguided move). See `scripts/samplers.py` for the head-to-head.

The sampler is ~50-80x slower than backtracking on distinct filtered lists and its
solve-rate collapses on the small/hard lists where backtracking stays complete, so
it is SECONDARY, kept for (a) genuinely soft preferences and (b) a sample
distribution. See open question "does the sampler earn its keep".

## Acceptance test (src/puzzledesk/validate.py)

`validate(sq, state, threshold) -> Verdict`. A grid is `ok` iff:
1. the WEAKEST of the 2N words has score >= threshold (a bottleneck/min test,
   NOT an average — one weak word fails the grid), AND
2. all 2N words are distinct (`n_distinct == 2N`).

`Verdict` fields: `ok, min_score, weakest, distinct, n_distinct, words`. This is
the feedback signal the whole design optimises against. `score_of` falls back to
0.0 for words not in the lexicon's score_map.

## Blocked grids (src/puzzledesk/blocked.py, fill.py)

The everything-above assumes a fully-checked square: every row and column is one
full-length word, so down words are induced by reading columns. Black cells break
that — the "load-bearing, do not generalise" note on the square representation is
exactly what black cells force you past. Rather than warp the square model, the
blocked case is a SEPARATE, coexisting representation:

- `BlockedGrid.parse(template, min_len)` reads a `.`/`#` pattern into **slots**
  (maximal white runs >= min_len, across and down) and records, per white cell,
  which across and down slot pass through it (`cell_slots`). The set of
  (across, down) pairs that share a cell is the crossing graph. `orphans` are
  white cells in no slot (a run shorter than min_len) — a malformed grid; fill
  refuses one. It also assigns conventional clue numbers.
- `MultiLexicon` (lexicon.py) holds a `Lexicon` per length, since slots no longer
  share one length; `Lexicon.matching(pattern)` answers the per-slot query "words
  that fit these already-fixed letters" (any number of blanks, unlike
  `allowed_at`'s exactly-one). A length with no words at the bar is an empty
  bucket (`_EmptyLexicon`), so such a slot is simply unfillable (UNSAT), not a
  crash.
- `fill.solve(grid, mlex, distinct, ...)` is complete backtracking over slots with
  **MRV** ordering (always extend the unfilled slot with the fewest candidates; a
  0-candidate slot is an immediate dead end). Distinctness is a grid-wide `used`
  set (crosswords never repeat an entry). Randomised candidate order gives
  per-seed diversity. None == exhausted tree == real UNSAT, same as `backtrack`.
  `enumerate_fills` is the tiny-grid ground truth (cf. `bruteforce.py`).

This reuses the whole thesis (complete search on a bar-filtered list) and the
Lexicon's pattern machinery; only the representation changed. `scripts/blackcells.py`
is the demo + ground-truth check. Word lists longer than 5 are still not built (the
data only covers 2..5, enough for slots up to length 5).

## Block-pattern generation (src/puzzledesk/patterns.py)

`blocked.py` takes the block pattern as INPUT. `patterns.py` makes it a PARAMETER:
from a shape and a *number* of black cells, generate the legal layouts (D13).

- `gen_patterns(rows, cols, num_black, min_len=3, symmetric=True, seed, randomize)`
  yields every legal `BlockedGrid` with exactly `num_black` blacks. Legal =
  (default) 180°-rotationally symmetric, *fully checked* (every white cell in an
  across AND a down run >= min_len; equivalently no white run has length
  1..min_len-1 — this subsumes `blocked.py`'s no-orphan rule), and white cells
  4-connected. Complete backtracking over cells, grouped into 180°-rotation ORBITS
  when symmetric (`_orbits`) so a whole orbit is blackened at once; `randomize`
  shuffles orbit order per seed for diversity without changing the reachable set.
  An empty generator is a PROOF no legal layout exists (e.g. a symmetric even-celled
  grid cannot take an odd black count — no centre cell; and a black centre in a 5x5
  is illegal, it makes length-2 runs). With `symmetric=False` each cell is its own
  unit (no orbits): the reachable set is every legal placement, which is how you get
  an odd count like 3 blacks on a 5x5 that no symmetric layout admits. Everything
  else (fully-checked, connected, completeness) is unchanged; `generate.py` exposes
  it as `--nonsymmetric`.
- `fill_by_count(rows, cols, num_black, mlex, ...)` composes the layout search with
  `fill.solve`: returns `(grid, assign)` for the first legal layout that admits a
  distinct fill, or None. Both stages complete, so None is a real UNSAT proof for
  the shape+count+lists (unless `max_patterns`/`node_budget` bound the search).

`patterns.py` produces only `BlockedGrid`s and reuses `fill.py` unchanged — the
square/blocked split (invariant 0) is intact. `scripts/generate.py` is the demo:
a small-grid property check (enumerate all layouts, assert the invariants) then
minis generated from a black-cell count.

## Invariants — do not break

0. TWO GRID MODELS COEXIST. The square (square.py: induced columns, invariants
   1-2) and the blocked grid (blocked.py/fill.py: explicit slot graph;
   patterns.py generates its layouts from a black-cell count). Invariants
   1-2 below are about the SQUARE model; the blocked model derives nothing from
   columns. Distinctness (3) and score-scale/lowercase (4-5) apply to both.
1. STATE = across-word indices. Down words are always derived, never stored.
2. ENERGY 0 == valid. Any change to what counts as "a word" must go through the
   column lexicon's wordset so energy stays meaningful.
3. DISTINCTNESS. Acceptable output has 2N distinct words. Enforced in `validate`
   (acceptance), `backtrack` (pruning + leaf), and `sampler` (duplicate-pair
   penalty, `distinct=True`). If you add a fourth code path that emits grids, it
   must enforce this or the symmetric basin returns. The sampler's raw-packing
   default (`distinct=False`) does NOT — it is not an output path.
4. SCORE SCALE IS PER-LIST. `scored_N.txt` scores are wordfreq Zipf (~0..8).
   `cw_N.txt` scores are crossword 0..100. A threshold is only meaningful
   relative to its list. Never reuse a Zipf threshold on the curated list or
   vice versa. `ceiling.py` picks default thresholds by list name for this
   reason.
5. LOWERCASE ASCII. Lexicon assumes a-z; the curated source is upper/mixed and
   is lowercased at ingestion (see notes.md, generation commands).

## Data flow for "generate a mini" (scripts/mini.py)

Lexicon.from_scored_file(cw_N) -> filtered(min_score) -> DoubleSquare ->
backtrack.solve(distinct=True) per seed -> validate (assert ok) -> render across
(state) and down (column_strings). Every emitted grid is distinct-words and
every word >= min_score by construction of the filter.

## Scripts (all under scripts/, add `src` to sys.path themselves)

- demo.py: correctness N=2..4. N=2 checks the sampler against brute-force ground
  truth (the only place we have ground truth); above N=2 validity is by
  construction. Run after touching the energy model or sampler.
- bench.py: order-N solve timing for the sampler (raw packing, distinct off).
- frontier.py: sweep the acceptance threshold with the sampler (distinct=True);
  where does packing into a genuine square stay feasible. Stochastic counterpart
  to ceiling.py's complete sweep.
- compare.py: sampler vs backtrack head-to-head on the same distinct problem.
- samplers.py: sampler strategy study — gate vs distinctness-penalty (+backtrack
  reference), same distinct problem.
- blackcells.py: blocked-grid fill — tiny-grid ground truth, filled grids from the
  curated list, and a quality ceiling (shortest slot's list runs dry first).
- generate.py: blocked minis from a black-cell COUNT (not a template) — layout
  property check on a tiny case, then `generate.py rows cols num_black min_score
  count` searches legal layouts and fills them.
- ceiling.py: sweep thresholds with the complete solver to find where it goes
  UNSAT. Generalised: `ceiling.py N listname thresholds...` (listname "scored"
  or "cw"; default thresholds chosen per list).
- mini.py: the generator. `mini.py N min_score count`.
- gen_scored.py: regenerate `scored_N.txt` from `words_N.txt` via wordfreq. Only
  needed if you change the weak list; requires the wordfreq package.

## bruteforce.py

Exhaustive enumeration for tiny N (ground truth at N=2; N=3+ explodes on a
permissive list — do not enumerate the full curated list). Prefix-pruned. Used
only by demo.py at N=2.
