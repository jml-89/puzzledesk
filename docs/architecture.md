# Architecture and invariants

Audience: an agent modifying this codebase. This documents the data model, the
invariants you must not break, the engines, and the non-obvious details that
are easy to get wrong. Read `docs/decisions.md` for *why* it is shaped this way
and `docs/notes.md` for benchmarks/environment.

## Layered architecture (hexagonal; D14)

`src/puzzledesk/` is a hexagon (ports & adapters) with a single **linear** import
stack, enforced by **import-linter** (`[tool.importlinter]` in `pyproject.toml`;
`uv run lint-imports`). A layer may import any layer *below* it, never one above:

    core  <  app  <  adapters  <  bootstrap  <  cli

Two contracts hold: the `layers` contract above (D14), and a `forbidden` contract
that keeps the OS out of the pure layers (see "OS reach is confined to init", below).

- **`core/`** — the pure kernel (this document's data model + engines + lexicon +
  `validate`). No I/O, deterministic given its inputs. Defines the one port its
  engines need, `core/rng.py::Rng`/`RngFactory` — randomness is *injected*, not
  constructed here (the engines take `rng=`; see the engines below).
- **`app/`** — use-case services (`MiniService`, `BlockedGenerateService`) and the
  ports they need from outside (`app/ports.py`: `LexiconSource`, `Writer`).
  Services orchestrate the core through ports and return structured results
  (`app/results.py`); they never import a concrete adapter, read a file, or print.
  Clue generation is fenced here too: `app/puzzle.py` is the canonical space-first
  `FilledGrid` (cells + occupation; runs/crossings derived), `app/clue.py::ClueProvider`
  is the port the soft/generative clue stage lives behind, and `app/cluing.py::ClueService`
  is the deterministic orchestration (hard constraints + selection) over it. The real
  provider is `adapters/claude_clue.py` (the Anthropic SDK, an optional `clue` extra;
  the LLM lives in the adapter, never as an app port). See D15 (interface) and D16
  (service + adapter).
- **`adapters/`** — infrastructure implementing the ports: `NumpyRngFactory` (the
  injected Prng; `np.random.default_rng` is confined here), `FileLexicon` (the disk
  read that used to sit in the kernel), `StreamWriter`/`CapturingWriter`. Adapters
  sit *above* `app` on purpose — they implement `app`'s ports — which is what makes
  one `layers` contract forbid `app → adapters` (the DI inversion) yet allow
  `adapters → app`.
- **`bootstrap/`** — the composition root: `build()` assembles a `Container` in
  three explicit stages (config → adapters → services).
- **`cli/`** — thin entry points: argv → `build()` → run a service → present via a
  `Writer`. `scripts/*.py` for the tools are two-line shims; benchmark drivers stay
  in `scripts/` but build the container and use its injected adapters.

Determinism is unchanged by the injection: `NumpyRngFactory.create(seed)` returns
`np.random.default_rng(seed)`, so a `(lists, seed)` pair still reproduces exactly
(invariant below). Tests (`tests/`, `uv run pytest`) drive the services with an
in-memory `LexiconSource` and a recording `RngFactory` — no files, no global RNG.

### OS reach is confined to init (D18)

The program's shape is **entry point → bootstrap → service container → steady state**:
a `cli` entry does argv → `build()` → run a service → present. `build()` (the
composition root) is the *one* place that touches the operating system at startup — it
reads the configured key env var (D17), fixes `Config.data_dir`, and resolves the
output stream — then hands back a frozen `Container` whose services run over ports
without reaching back out. This is the run-fast-and-exit tool's version of OpenBSD's
`pledge`/`unveil`: grab OS capabilities once at init, then stay confined. The
environment is grabbed only in `bootstrap`; filesystem access is *unveil*-shaped (the
directory is fixed at init, `FileLexicon` reads on demand but only under it); `core`
and `app` are pure functions over their inputs.

The `forbidden` import-linter contract fences this: `core` and `app` may not import
`os`, `io`, `sys`, `subprocess`, or `socket`. It is an import-time fence, not a sandbox
— it exempts `adapters`/`bootstrap`/`cli` (the OS edge) by design and does not stop a
runtime reflection trick — but it keeps the kernel honest, which is the point. See D18.

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

Key methods (all *pure* — the kernel parses text, it does not read files; the disk
read lives in the `FileLexicon` adapter, see "Layered architecture"):
- `from_words_text(text, length)`: parse a plain word-per-line body, scores 0.
- `from_scored_text(text, length)`: parse a "word score" per-line body. BOTH data
  list families use this (see score-scale gotcha below).
- `filtered(min_score, max_score=None)`: sub-lexicon of words with score in
  `[min_score, max_score]` (`max_score=None` == an open upper bound, the plain quality
  bar). A one-sided floor applies a quality bar (filter, then solve feasibility); a
  two-sided *band* applies a difficulty bar — "harder" draws from the obscure band, and
  a banded run still proves a difficulty ceiling because search stays complete (D20).
- `n_letters_at(word, pos)`: how many distinct letters this lexicon still admits at
  `pos` if that cell of `word` were blanked and the rest held fixed. `1` means the word
  alone forces the letter there. The primitive behind structural checkability (below).
- `words_matching(allowed)`: allowed is a length-N list of 26-bool masks; returns
  indices of words whose letter at every position is permitted. The bitset-style
  intersection the backtracker uses to get legal row words directly.
- `matching(pattern)`: pattern is length-N of `int|None` (fixed letters + blanks,
  any number of blanks); returns indices of words that fit. The per-slot query for
  blocked-grid fill.

`MultiLexicon` (same file) buckets a `Lexicon` per length for blocked grids, whose
slots differ in length; `MultiLexicon.from_scored_texts(text_for, lengths, bar)`
parses and bar-filters each length, keeping empty lengths as an unfillable bucket.
(The `FileLexicon` adapter supplies `text_for`/`path_for` by reading the files.)

encode/decode map lowercase word <-> uint8 index array. `encode` uses
`np.frombuffer(word.encode('ascii'))` so inputs must be lowercase ascii a-z.

## The square engine

Squares have one engine: complete propagation-backtracking. (An energy-based
stochastic `sampler` was the *original* engine and was removed once it lost the
head-to-head — see D19; the blocked model has its own engines, `fill`/`patterns`,
documented further below.)

### backtrack.py — the square engine, complete

`solve(sq, *, rng, randomize=True, distinct=True) -> state | None`. `rng` is an
injected `core.rng.Rng` (a fresh stream per seed, built at the composition root);
the engine no longer opens its own `default_rng`. `randomize=False` ignores it.

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

### The retired sampler (D19)

For its first several iterations the square also had a *secondary* engine: an
energy-based min-conflicts / annealed-Gibbs `sampler` (D3), the original engine,
kept on after D7 made backtracking primary. It was removed in D19 once measurement
settled the question: ~50-80× slower than backtracking on distinct filtered lists,
solve-rate collapsing on exactly the small/hard lists where backtracking stays
complete, and distinctness was never its bottleneck. Its stated reasons to survive
(soft preferences, a sample distribution) were hypothetical future needs, not
current ones, so it was recorded (D19 + the numbers in notes.md) rather than kept.
If a big-and-soft regime ever returns (a large list with genuine soft preferences —
themes, per-batch novelty), restoring it from git is a fresh spike; see D19's
reversal note and open-questions "Grid variety".

## Acceptance test (src/puzzledesk/validate.py)

`validate(sq, state, threshold) -> Verdict`. A grid is `ok` iff:
1. the WEAKEST of the 2N words has score >= threshold (a bottleneck/min test,
   NOT an average — one weak word fails the grid), AND
2. all 2N words are distinct (`n_distinct == 2N`).

`Verdict` fields: `ok, min_score, weakest, distinct, n_distinct, words`. This is
the feedback signal the whole design optimises against. `score_of` falls back to
0.0 for words not in the lexicon's score_map.

## Difficulty: checkability + solve order (src/puzzledesk/app/difficulty.py)

`validate` scores *quality* (per-word crowd score + distinctness). Difficulty is a
separate, layered thing (D20); the *complete, deterministic* slices live here — a
**static** snapshot (`analyze`) and a **dynamic** solve-order model (`solve_order`, D21).

`analyze(grid, options)` reads a `FilledGrid` (invariant 0: either grid
model projects into it) and reports, per crossing cell, whether the shared letter is
**forced** (one of the two words alone pins it) or **open** (neither does, so the
solver needs outside knowledge — the Natick pathology). `CrossingOpenness` carries
`across_options`/`down_options` (distinct letters each word admits at that cell) with
`forced`/`is_open`/`ambiguity`; `StructuralDifficulty` aggregates `open_crossings`,
`max_ambiguity`, `hardest`.

Two modelling choices (D20), both at the call site, not baked into the metric:
- **Full vocabulary, not the filtered list.** `options` is wired against the
  *unfiltered* lexicon — a solver knows every word, not only those above the
  generation bar. `Lexicon.n_letters_at` is the primitive; the driver supplies
  `options(answer, pos) = full_lex.n_letters_at(answer, pos)`.
- **Maximal support (final state).** The rest of each word is assumed known, so an
  open crossing is *unavoidably* hard regardless of solve order — a conservative
  signal, not a solve-trajectory simulation (that trajectory/BP model is a deferred
  spike, see open-questions "Difficulty").

`solve_order(grid, candidates, score, *, gimme)` (D21) is the *dynamic* reading: it
replays the known fill easiest-first and returns a `Trajectory` of `Step`s, each
classified **forced** (only one word fits its pattern now), **gimme** (`score >=
gimme` — known from the clue), or **hard** (stuck: obscure and still open). Solving an
entry reveals its cells, which force/ease its crossings next iteration (the cascade);
when stuck it attacks the most-supported entry first, so support drives the cascade.
`Trajectory.bottleneck` is the hardest hard-get — what makes a grid a Saturday. This
separates *obscure-but-forced* (fine) from *obscure-and-open* (a Natick), which
`analyze`'s maximal-support snapshot cannot. `gimme` is the soft, uncalibrated
clue-gettability knob (D20 layer B) — an input that lets the model bracket a solver,
not a claim to be one.

Both functions import nothing from `core` (they take the `options`/`candidates`/`score`
callables), so they are representation-agnostic and fakeable with plain dicts.
`scripts/difficulty.py` is the measurement driver: it solves minis (square or `blocked`),
projects to `FilledGrid`, and reports the static openness (cross-referenced with
per-word score, invariant 4, for the "unfair Natick" read) and the dynamic trajectory
side by side.

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
  that fit these already-fixed letters" (any number of blanks). A length with no
  words at the bar is an empty bucket (`_EmptyLexicon`), so such a slot is simply
  unfillable (UNSAT), not a crash.
- `fill.solve(grid, mlex, *, rng, distinct, ...)` is complete backtracking over
  slots with **MRV** ordering (`rng` injected as above; always extend the unfilled
  slot with the fewest candidates; a
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

- `gen_patterns(rows, cols, num_black, *, rng, min_len=3, symmetric=True, randomize)`
  yields every legal `BlockedGrid` with exactly `num_black` blacks (`rng` injected;
  `randomize=False` leaves orbit order fixed for the ground-truth check). Legal =
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
- `fill_by_count(rows, cols, num_black, mlex, *, rng_factory, seed=0, ...)` composes
  the layout search with `fill.solve`: returns `(grid, assign)` for the first legal
  layout that admits a distinct fill, or None. It re-seeds per attempt, so it takes
  an `RngFactory` (not a single stream) and a `seed`; the layout search and each
  fill get a fresh `rng_factory.create(seed)`. Both stages complete, so None is a
  real UNSAT proof for the shape+count+lists (unless `max_patterns`/`node_budget`
  bound the search).

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
   (acceptance), `backtrack` (pruning + leaf), and `fill` (grid-wide `used` set for
   blocked grids). If you add a new code path that emits grids, it must enforce this
   or the symmetric basin returns.
4. SCORE SCALE IS PER-LIST. `scored_N.txt` scores are wordfreq Zipf (~0..8).
   `cw_N.txt` scores are crossword 0..100. A threshold is only meaningful
   relative to its list. Never reuse a Zipf threshold on the curated list or
   vice versa. `ceiling.py` picks default thresholds by list name for this
   reason.
5. LOWERCASE ASCII. Lexicon assumes a-z; the curated source is upper/mixed and
   is lowercased at ingestion (see notes.md, generation commands).

## Data flow for "generate a mini" (`app.mini.MiniService`)

`FileLexicon.load("cw", N)` (reads `cw_N.txt`, parses via `Lexicon.from_scored_text`)
-> `full.filtered(min, max)` (the generation band) -> DoubleSquare ->
`backtrack.solve(rng=factory.create(seed), distinct=True)` per seed -> validate (assert
ok) -> shape a `MiniResult`. The `cli.mini` entry point + `cli.present` render it. Every
emitted grid is distinct-words and every word in the band by construction of the filter.
`cli.generate` + `BlockedGenerateService` are the blocked analogue.

**Difficulty targeting (D22).** With `min_hard_gets > 0`, each solved grid is scored by
`solve_order` (against the *full* vocabulary, under `gimme`) and kept only if it needs
that many hard gets; survivors return hardest-first with a `SolveDifficulty` attached.
This is best-of-a-seed-budget over a soft score, **not** a proof: a short return means
"not found in the budget", never "impossible" (unlike a backtracker `None`).

## Entry points

Tools (`cli/`, typed, over services; `scripts/{mini,generate}.py` are shims;
`mini`/`generate` are also `[project.scripts]` console commands):

- mini.py: the generator. `mini.py N min_score count [--max HI] [--hard K] [--gimme G]`.
  The positionals are unchanged (`mini 5 70 3` still means N=5, floor 70, 3 grids);
  `--max HI` turns the floor into a difficulty *band* `[min_score, HI]` (D20); `--hard K`
  *targets a difficulty* (D22) — keep only grids the solve-order model says need >= K hard
  gets, read under clue-difficulty `--gimme G` (default 80), returned hardest-first. E.g.
  `mini 5 60 3 --max 90 --hard 6 --gimme 88` emits Saturdays.
- generate.py: blocked minis from a black-cell COUNT (not a template). `generate.py
  rows cols num_black min_score count [--nonsymmetric]` searches legal layouts and
  fills them. (Its old inline layout property-check is now `tests/test_patterns.py`.)

Benchmark/demo drivers (`scripts/`, loose, ANN-exempt; each builds the container
and uses the injected `lexicon`/`rng_factory` adapters):

- demo.py: correctness N=2..4. N=2 checks `backtrack` against brute-force ground
  truth (`backtrack ⊆ bruteforce`); above N=2 validity is by construction. (Also
  encoded in `tests/test_ground_truth.py`.)
- blackcells.py: blocked-grid fill — tiny-grid ground truth, filled grids from the
  curated list, and a quality ceiling (shortest slot's list runs dry first).
- ceiling.py: sweep thresholds with the complete solver to find where it goes
  UNSAT. Generalised: `ceiling.py N listname thresholds...` (listname "scored"
  or "cw"; default thresholds chosen per list).
- difficulty.py: structural checkability of generated minis — solves at a score band
  and reports each grid's *open* crossings (Natick risk) via `app.difficulty.analyze`,
  cross-referenced with word obscurity (D20). `difficulty.py N listname min [max]
  [obscure_below]` for squares; `difficulty.py blocked R C K [min] [obscure_below]` for
  blocked grids (open rate bucketed by the weak side's slot length). Both paths share
  one reporter over `FilledGrid.runs()`, so the metric is model-agnostic.
- gen_scored.py: regenerate `scored_N.txt` from `words_N.txt` via wordfreq. Only
  needed if you change the weak list; requires the wordfreq package.

## bruteforce.py (`core/engines/`)

Exhaustive enumeration for tiny N (ground truth at N=2; N=3+ explodes on a
permissive list — do not enumerate the full curated list). Prefix-pruned. Used by
`demo.py` at N=2 and by `tests/test_ground_truth.py`.
