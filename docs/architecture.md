# Architecture and invariants

Audience: an agent modifying this codebase. This documents the data model, the
invariants you must not break, the engines, and the non-obvious details that
are easy to get wrong. Read `docs/decisions.md` for *why* it is shaped this way
and `docs/notes.md` for benchmarks/environment.

## Layered architecture (hexagonal; D14)

`src/puzzledesk/` is a hexagon (ports & adapters) with a single **linear** import
stack, enforced by **import-linter** (`[tool.importlinter]` in `pyproject.toml`;
`uv run lint-imports`). A layer may import any layer *below* it, never one above:

    core  <  app  <  adapters  <  bootstrap  <  cli  <  web

`cli` and `web` are sibling **entry points** (argv and HTTP respectively); the contract
stacks `web` above `cli` (neither imports the other, so any order is sound) — both do
input → `build()` → run a service → present.

Two contracts hold: the `layers` contract above (D14), and a `forbidden` contract
that keeps the OS out of the pure layers (see "OS reach is confined to init", below).

- **`core/`** — the pure kernel (this document's data model + engines + lexicon +
  `validate`). No I/O, deterministic given its inputs. Defines the one port its
  engines need, `core/rng.py::Rng`/`RngFactory` — randomness is *injected*, not
  constructed here (the engines take `rng=`; see the engines below).
- **`app/`** — use-case services (`MiniService`, `GenerateService`, `PuzzleService`)
  and the ports they need from outside (`app/ports.py`: `LexiconSource`, `Writer`).
  Services orchestrate the core through ports and return structured results
  (`app/results.py`); they never import a concrete adapter, read a file, or print.
  Generation *input* is modelled, not passed as loose kwargs: `app/spec.py` is the
  typed request algebra (`GridSpec` + the closed `LayoutStrategy` union + `FillSpec`,
  bundled as `PuzzleSpec`), dispatched with `match` + `assert_never` (D32; see
  "Generation specs" below).
  Clue generation is fenced here too: `app/puzzle.py` is the canonical space-first
  `FilledGrid` (cells + occupation; runs/crossings derived), `app/clue.py::ClueProvider`
  is the port the soft/generative clue stage lives behind, and `app/cluing.py::ClueService`
  is the deterministic orchestration (hard constraints + selection) over it. The real
  provider is `adapters/claude_clue.py` (the Anthropic SDK, an optional `clue` extra;
  the LLM lives in the adapter, never as an app port). See D15 (interface) and D16
  (service + adapter).
- **`adapters/`** — infrastructure implementing the ports: `NumpyRngFactory` (the
  injected Prng; `np.random.default_rng` is confined here), `FileLexicon` (the disk
  read that used to sit in the kernel), `StreamWriter`. Adapters
  sit *above* `app` on purpose — they implement `app`'s ports — which is what makes
  one `layers` contract forbid `app → adapters` (the DI inversion) yet allow
  `adapters → app`.
- **`bootstrap/`** — the composition root: `build()` assembles a `Container` in
  three explicit stages (config → adapters → services).
- **`cli/`** — thin entry points: argv → `build()` → run a service → present via a
  `Writer`. `scripts/*.py` for the tools are two-line shims; benchmark drivers stay
  in `scripts/` but build the container and use its injected adapters.
- **`web/`** — the HTTP entry point (D35), a sibling of `cli`: an HTTP body →
  `build()`'s container → a service → a JSON view. FastAPI behind a `web` optional
  extra, isolated exactly like `anthropic` behind `clue` (the package and the gate run
  without it; only `puzzledesk.web.*` imports FastAPI/Pydantic). Its Pydantic wire schema
  *parses into* `PuzzleSpec` and *renders* a stored puzzle — a separate object, never the
  app spec itself (D15). See "Data flow for serving a puzzle over HTTP" below.

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

## Core representation (src/puzzledesk/core/square.py)

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

## Lexicon (src/puzzledesk/core/lexicon.py)

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
  a banded run still proves a difficulty ceiling because search stays complete (D21).
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

(A `count`/model-counting extension of this engine — how *large* the solution space is
at a bar — was spiked, measured, and tombstoned; see D31 and
`docs/postmortem-kernel-methods.md` for what it found, chiefly that the curated top tier
admits exactly 38 distinct 5x5 minis.)

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

## Acceptance test (src/puzzledesk/core/validate.py)

`validate(sq, state, threshold) -> Verdict`. A grid is `ok` iff:
1. the WEAKEST of the 2N words has score >= threshold (a bottleneck/min test,
   NOT an average — one weak word fails the grid), AND
2. all 2N words are distinct (`n_distinct == 2N`).

`Verdict` fields: `ok, min_score, weakest, distinct, n_distinct, words`. This is
the feedback signal the whole design optimises against. `score_of` falls back to
0.0 for words not in the lexicon's score_map.

## Difficulty: checkability + solve order (src/puzzledesk/app/difficulty.py)

`validate` scores *quality* (per-word crowd score + distinctness). Difficulty is a
separate, layered thing (D21); the *complete, deterministic* slices live here — a
**static** snapshot (`analyze`) and a **dynamic** solve-order model (`solve_order`, D22).

`analyze(grid, options)` reads a `FilledGrid` (invariant 0: either grid
model projects into it) and reports, per crossing cell, whether the shared letter is
**forced** (one of the two words alone pins it) or **open** (neither does, so the
solver needs outside knowledge — the Natick pathology). `CrossingOpenness` carries
`across_options`/`down_options` (distinct letters each word admits at that cell) with
`forced`/`is_open`/`ambiguity`; `StructuralDifficulty` aggregates `open_crossings`,
`max_ambiguity`, `hardest`.

Two modelling choices (D21), both at the call site, not baked into the metric:
- **Full vocabulary, not the filtered list.** `options` is wired against the
  *unfiltered* lexicon — a solver knows every word, not only those above the
  generation bar. `Lexicon.n_letters_at` is the primitive; the driver supplies
  `options(answer, pos) = full_lex.n_letters_at(answer, pos)`.
- **Maximal support (final state).** The rest of each word is assumed known, so an
  open crossing is *unavoidably* hard regardless of solve order — a conservative
  signal, not a solve-trajectory simulation (that trajectory/BP model is a deferred
  spike, see open-questions "Difficulty").

`solve_order(grid, candidates, score, *, gimme)` (D22) is the *dynamic* reading: it
replays the known fill easiest-first and returns a `Trajectory` of `Step`s, each
classified **forced** (only one word fits its pattern now), **gimme** (`score >=
gimme` — known from the clue), or **hard** (stuck: obscure and still open). Solving an
entry reveals its cells, which force/ease its crossings next iteration (the cascade);
when stuck it attacks the most-supported entry first, so support drives the cascade.
`Trajectory.bottleneck` is the hardest hard-get — what makes a grid a Saturday. This
separates *obscure-but-forced* (fine) from *obscure-and-open* (a Natick), which
`analyze`'s maximal-support snapshot cannot. `gimme` is the soft, uncalibrated
clue-gettability knob (D21 layer B) — an input that lets the model bracket a solver,
not a claim to be one.

Both functions import nothing from `core` (they take the `options`/`candidates`/`score`
callables), so they are representation-agnostic and fakeable with plain dicts.
`scripts/difficulty.py` is the measurement driver: it solves minis (square or `blocked`),
projects to `FilledGrid`, and reports the static openness (cross-referenced with
per-word score, invariant 4, for the "unfair Natick" read) and the dynamic trajectory
side by side.

## Blocked grids (src/puzzledesk/core/blocked.py, core/engines/fill.py)

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
is the demo + ground-truth check. Word lists now cover **lengths 2..15** (D36):
`cw`/`scored`/`words` each ship a file per length, so a slot of any length up to 15 is
fillable — the earlier 2..5 ceiling was a data gap, not an engine limit, and it is closed.

## Block-pattern generation (src/puzzledesk/core/engines/patterns.py)

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
square/blocked split (invariant 0) is intact. `scripts/generate.py` is a thin shim
to the `generate` tool (`cli.generate`); the small-grid property check that used to
run inline (enumerate all layouts, assert the invariants) now lives in the pytest
suite (`tests/test_patterns.py`).

### Cap-driven layouts for large minis (D24)

`gen_patterns` above is *count-driven*: you fix the number of blacks and it caps only
the *minimum* entry length. A mini bigger than 5x5 wants the opposite knob — a cap on the
*maximum* entry length, so tactically placed black cells hold every entry short (a 10x10
built from 3–5-letter words, not ten-letter monsters). That cap is also what let a big
grid fill from short-word data alone — no length-6+ lists *required*. (Those lists now
exist, lengths 2..15 per D36, so a larger `max_len` is a supported knob too; the cap
remains the lever for *short-word* large grids, which is still usually what you want.)

- `gen_capped(rows, cols, *, rng, min_len=3, max_len=None, symmetric=True, num_black=None,
  max_black=None, node_budget=None, randomize=True)` yields every legal layout whose entries
  all have length in `[min_len, max_len]`. The *cap* is the governing parameter; the black
  count is derived. It searches **row-major** and prunes each partial row/column the instant a
  run is too long or too short (`_cell_ok`) — the run-aware pruning `gen_patterns`' orbit/leaf
  model structurally cannot do, and why a 10x10 is found in ~5 ms rather than never. Same
  legality otherwise (symmetric, fully checked, connected) and same completeness: an empty
  generator is a proof (an odd `num_black` on a symmetric 10x10 has no centre cell). With
  `max_len=None` + a fixed count it enumerates the *identical set* `gen_patterns` does
  (cross-tested) — a strict generalization.
  - **Density (D25).** `num_black` pins the count exactly; `max_black` bounds it above (still
    complete over "<= K blacks" — below the feasibility minimum it is a provable empty). The
    randomized order is **white-biased** (black-first only `_BLACK_FIRST_PCT` of the time) so
    the search prefers few, spread-out blacks; this only reorders which layout appears first.
    `node_budget` (like `fill.solve`'s) bails a search that a tight cap makes backtrack away —
    a *budgeted* empty is exhaustion, not a proof. The service defaults `max_black` to ~22% of
    the cells (`DEFAULT_BLACK_FRACTION`) so a capped mini reads like a real crossword.
- `fill_capped(rows, cols, mlex, *, max_len, ...)` is the cap-driven analogue of
  `fill_by_count`: first `gen_capped` layout that admits a distinct fill. Both searches are
  complete, but the capped layout space at 10x10 is astronomically large, so a `None` under
  a `max_patterns`/`node_budget` bound is *budget exhaustion, not a UNSAT theorem* (existence
  — e.g. the odd-count proof — is still exact). `scripts/largemini.py` is the measurement
  driver; `GenerateService.fill(grid, CappedLayout(max_len=K))` and `generate --max-len K`
  expose it.

### The layout field sampler — Gibbs, soft, coexisting (src/puzzledesk/core/engines/gibbs_layout.py, D27)

Everything above *searches* the layout (complete backtracking). The black-cell **layout** is
the one *soft, local field* regime the system has (docs/open-questions.md "Layout generation is
a soft, local field"): a translation-invariant grid with local run-length legality and a soft
objective — density, spread, no 2x2 block. `gibbs_layout.py` samples it, a **coexisting**
layout generator beside the complete `gen_capped` (the invariant-0 "two models coexist" move,
at the layout layer). It is the "big-and-soft" regime D19 reserved for a sampler's return — a
*new* spike (the layout, not the retired fill sampler).

- `gibbs_layouts(rows, cols, *, rng, max_len, min_len=3, black_fraction=.16, target_black=None,
  symmetric=True, params=None, sweeps, t0, t1, attempts_per_layout)` yields legal capped
  layouts drawn by **annealed Gibbs** over the binary field. The energy (`FieldParams`) is a sum
  of **local factors**: run-length legality (dominant), a density spring `(n_black-target)^2`,
  an anti-cluster pair penalty, and an explicit **no-2x2-black-block** term. A single-cell Gibbs
  step evaluates only the *affected rows/columns* + the *cluster touching the flipped orbit*
  (the rest cancels in the conditional), so it is cheap per step.
- **Symmetry is global-but-free** — it colours only the 180° orbit representatives (whole orbit
  at once), so every draw is symmetric by construction, no factor. **Connectivity is global and
  topological** — a local factor cannot express it, so it is *not* in the energy; it is a global
  **reject** at the end (`patterns._connected` BFS), the honest boundary open-questions flagged.
- **Not complete.** A yielded grid is legal by exactly `gen_capped`'s definition (the final gate
  reuses `patterns._fully_checked`/`_connected`), but "no sample after N attempts" is **budget
  exhaustion, never a UNSAT proof** — `GenerateService.layout_exists` (the `gen_capped`
  theorem) stays the sole existence proof. The epistemics survive the new engine.
- `fill_gibbs` / `GenerateService.fill(grid, GibbsLayout(...))` / `generate --gibbs` expose it;
  `scripts/gibbs.py` is the head-to-head driver. **Verdict (D27): kept, scoped to aesthetics** —
  at 10x10 it wins on spread (cluster 0.67 vs 0.85) and *guarantees* no 2x2 block (vs ~0.27/grid
  for `gen_capped`), and is far more productive at the 12x12 frontier where the complete search's
  node budget collapses; it loses on speed (~40x) and 10x10 diversity, and is not complete. So
  `gen_capped` stays the fast default + the proof engine; the field is the aesthetic alternative.
- This needed one **port extension**: `core.rng.Rng` gained `random()` (a uniform float for the
  Gibbs accept draw) — the seam D19's reversal note named; `numpy.random.Generator` already
  satisfies it, so no adapter changed.
- **The basin study (D28).** `anneal_field` (the raw sweep, split out of `sample_layout`) +
  `reject_reason` (`ok`/`short_run`/`over_cap`/`disconnected`) are the instruments for
  `scripts/gibbs.py`'s sweep of *basin shape × count*. Findings: the count knob has a **floor**
  (the cap-forced jamming density — D25's phase transition, sampler-side), the failure mode shifts
  from connectivity to run-length **legality** as the grid grows, and a **connectivity repair**
  (whiten a bridge black) was tried and **removed** — it is defeated by the cap (the separating
  blacks are cap-load-bearing, so whitening re-creates an over-cap run; it fixed ~0). The reliable
  lever is the soft weights (`w_cluster` reshapes spread cleanly). The soft/hard split re-derived
  inside the layout: the field owns the soft objective, complete search owns the hard legality.

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

## Generation specs — the typed request algebra (`app.spec`, D32)

Generation input is a modelled aggregate, not a bucket of keyword arguments. `app/spec.py`:

- `GridSpec` — the shape + quality band + seed every strategy shares (`rows`, `cols`,
  `min_score`, `max_score`, `seed`).
- `LayoutStrategy` — a **closed, tagged union**, one frozen record per layout engine,
  each carrying *only its own* knobs: `FullSquare` (the `DoubleSquare`, complete),
  `CountLayout` (D13, complete), `CappedLayout` (D24, budgeted), `GibbsLayout` (D27,
  sampled). Illegal knob combinations (`max_black` on the Gibbs field) are unrepresentable,
  and the epistemic tag — is a `None` a proof or budget exhaustion? — is `layout_is_complete`,
  a property of the variant, not lore in a method name.
- `FillSpec` — the fill *selection* knobs (`min_hard_gets`, `gimme`; D23). Distinctness
  (invariant 3) is not a knob — always on.
- `PuzzleSpec` — the whole-puzzle aggregate: `GridSpec + LayoutStrategy + FillSpec +
  ClueStyle`. The one object `PuzzleService` (and, next, a REST body) takes.

`GenerateService.fill_grid(grid, layout)` dispatches the layout+fill search on the strategy
(`match` + `assert_never`) and projects into a model-agnostic `FilledGrid` — square or
blocked, one call; `GenerateService.fill(grid, layout)` shapes the scored `BlockedResult`
for the blocked strategies. `GenerateService.layout_exists(grid, layout)` is the unbudgeted
existence proof. This is the D15 rule ("model only where a contract forces it") applied to
generation input: the serialized API surface is the contract; the internal call sites get
the clarity for free.

## Data flow for "generate a mini" (`app.mini.MiniService`)

`FileLexicon.load("cw", N)` (reads `cw_N.txt`, parses via `Lexicon.from_scored_text`)
-> `full.filtered(min, max)` (the generation band) -> DoubleSquare ->
`backtrack.solve(rng=factory.create(seed), distinct=True)` per seed -> validate (assert
ok) -> shape a `MiniResult`. `MiniService.generate(grid: GridSpec, sel: FillSpec, *, count)`
is the square's *batch + scoring* specialist (it keeps the `DoubleSquare`/state a
`FilledGrid` cannot carry); a *single* square instead flows through
`GenerateService.fill_grid(grid, FullSquare())` like any other grid. The `cli.mini` entry
point + `cli.present` render it. Every emitted grid is distinct-words and every word in the
band by construction of the filter. `cli.generate` + `GenerateService` are the blocked
analogue.

**Difficulty targeting (D23).** With `sel.min_hard_gets > 0`, each solved grid is scored by
`solve_order` (against the *full* vocabulary, under `sel.gimme`) and kept only if it needs
that many hard gets; survivors return hardest-first with a `SolveDifficulty` attached.
This is best-of-a-seed-budget over a soft score, **not** a proof: a short return means
"not found in the budget", never "impossible" (unlike a backtracker `None`).

## Data flow for "generate a whole puzzle" (`app.puzzle_service.PuzzleService`)

The end-to-end compose (D20): `PuzzleService.generate(spec: PuzzleSpec)` runs
`GenerateService.fill_grid(spec.grid, spec.layout)` — the same layout+fill search as
`generate`, for whichever strategy the spec names — projecting into the model-agnostic
`FilledGrid` (`app.puzzle`, invariant-0 anti-corruption layer) instead of a scored
`BlockedResult` -> `ClueService.clue(grid, style=spec.clue)` clues every entry through the
`ClueProvider` port (the one soft stage) -> a `CluedPuzzle`. `cli.present.playable`
renders it as a plain-text *solving* view: a blank numbered grid (numbering derived on
demand by `FilledGrid.numbering()`, never stored) plus Across/Down clue lists; the
answer key is the separate `present.solution`. A `None` grid short-circuits to a `None`
puzzle *before* any clue call — the completeness epistemics (a UNSAT theorem, not a
timeout) survive the compose. `cli.puzzle` is the entry point.

## Data flow for "solve a puzzle" (`app.solve_service.SolveService`, D26)

The empirical difficulty probe: put a *soft* solver (an LLM agent) in a feedback loop
against a generated puzzle and record how it goes. The mirror of the clue path — a
deterministic session with the model fenced behind a port — but pointed at *solving*
rather than *cluing*, and used as a proxy for the human solve-time signal the difficulty
work (D21/D22) is blocked on.

- `app/solve.py` is the deterministic **session** (the environment). `Board.of(puzzle)`
  extracts geometry + clues + the **answer key** from a `CluedPuzzle`; `SolveState` = board
  + the solver's per-*entry* guesses. Cell letters (and thus **crossing conflicts** — two
  crossing guesses disagreeing on a shared cell, a signal that needs *no* key) are **derived**
  from the guesses, never stored. `is_solved` is **cell-based** (the grid is right), not
  per-entry: filling the acrosses correctly already fills their crossing downs (the interlock).
- Feedback is a `FeedbackPolicy` knob — `CELL` (per-cell check, the default; the NYT
  autocheck button), `WORD` (whole-entry), `CROSSING` (conflicts only, key-free), `NONE`
  (only the terminal solved bit). **This knob is the solver-skill dial** — the empirical twin
  of `solve_order`'s `gimme` (D22); `CELL` is the most generous, so it compresses the signal
  and the stricter policies are the sharper probes.
- **Integrity invariant:** `SolveState.view(policy)` returns a `SolveView` that carries
  geometry, clues, the solver's own current letters, and the policy feedback — and **never an
  unguessed answer**. It is the solving-side anti-corruption boundary, the mirror of
  `FilledGrid` for cluing. A solver that could read the key measures nothing.
- `app/solver.py::SolverAgent` is the port (`act(view) -> SolverMove`, one-shot/stateless —
  the view *is* the observable state); `SolverMove` carries the agent's **reasoning**, because
  inspecting *how* it thought is the point. `app/solve_service.py::SolveService` is the harness
  (build view → act → validate+apply → check → record → repeat) and returns a `SolveReport`
  (the difficulty artifact). **A turn-budget miss is `exhausted`, never a proof** — the
  completeness epistemics (D23) restated on the solving side; only the fill engines prove UNSAT.
- `adapters/claude_solver.py` is the live agent behind the port (the *second* LLM consumer,
  D16/D26). It runs with thinking on (mode per model) and *without* a forced JSON schema, so
  `SolverMove.reasoning_tokens` can carry the model's thinking-token count — **the difficulty
  tell**: for a solver that finishes every mini, *how much it had to think* is the graded
  signal, not whether it solved (`SolveReport.total_reasoning_tokens` sums it). `cli/solve.py`
  composes it end to end (generate a clued puzzle, then solve it), `present.solve_report`
  renders the transcript. Tests drive the whole loop with a `FakeSolverAgent` — no model, no
  network. What difficulty this actually measures is recorded in notes.md (short version: clue
  obliqueness is the graded axis; word obscurity is a structural cliff, not a slope).

## Persistence: the `PuzzleRepository` port (`app.repository`, D35)

"Get a previously created puzzle" needs a place to keep one — the "Second adapters" seam,
finally exercised (D35, roadmap Phase 1). `app/repository.py` declares a **port**:
`PuzzleRepository` (`save(spec, puzzle) -> PuzzleId`, `get(id) -> StoredPuzzle | None`),
with `StoredPuzzle` carrying the `CluedPuzzle`, its originating `PuzzleSpec` (provenance),
and the assigned id. The port is **total** — `get` returns `None` for an unknown id, never
raises, so the caller words "no such puzzle" (the API's 404), the same shape as
`ClueProvider` returning empties.

Why store *data*, not a spec to re-run: the *fill* is reproducible from `(lists, spec,
seed)` (the complete engines are deterministic), but the *clues* are **soft** (an LLM), so
regenerating from the spec would not reproduce the same puzzle. `adapters/memory_repository.py`
(`InMemoryPuzzleRepository`, a dict + a counter) is the first implementation, wired in
`bootstrap` as a plain stage-2 adapter; `Container` gains a `repository` field. A database
adapter is a drop-in *second* implementation of the same port — nothing above `adapters`
changes when it lands, which is the point of the port.

## Data flow for "serve a puzzle over HTTP" (`web`, D35)

The HTTP mirror of `cli.puzzle`, and the first slice of the product loop (D34). A client
`POST /puzzles` with a JSON body → `web/schema.py::PuzzleRequest` (a Pydantic **wire
schema**: a discriminated union of layout bodies mirroring `LayoutStrategy`) validates it
and `to_spec()`s it into a canonical `PuzzleSpec` — a *separate* object that parses into the
app spec, never *is* it (D15) → `PuzzleService.generate(spec)` (the same fill+clue compose
`cli.puzzle` runs) → `PuzzleRepository.save` → `web/schema.py::puzzle_view` renders the
stored puzzle as player JSON (grid + derived numbering + clued Across/Down; a *view* beside
`present.playable`), returned `201`. `GET /puzzles/{id}` reads it back (`404` if absent).

`web/app.py::create_app(container)` is a **factory** over an assembled `Container` (so a
test hands it a fake-clued container via `dataclasses.replace`); `web/main.py` is the
uvicorn instance (`uv run --extra web uvicorn puzzledesk.web.main:app`). **The completeness
epistemics cross the HTTP boundary:** a `None` from generation becomes a `422` worded from
the spec's layout tag (`layout_is_complete`, D32) — `reason: "unsat"` when a *complete*
strategy proves no puzzle exists, `reason: "budget"` when a budgeted/sampled one merely
ran out — never a bland not-found. "None is a proof" (architecture, above) restated on the
wire. The answer key is embedded in the view for now (the static `site/` player's trust
model); a key-free *solving* view (the mirror of `SolveView`) is a Phase-2 concern.

## Entry points

Tools (`cli/`, typed, over services; `scripts/{mini,generate,puzzle,solve}.py` are shims;
`mini`/`generate`/`puzzle`/`solve` are also `[project.scripts]` console commands):

- mini.py: the generator. `mini.py N min_score count [--max HI] [--hard K] [--gimme G]`.
  The positionals are unchanged (`mini 5 70 3` still means N=5, floor 70, 3 grids);
  `--max HI` turns the floor into a difficulty *band* `[min_score, HI]` (D21); `--hard K`
  *targets a difficulty* (D23) — keep only grids the solve-order model says need >= K hard
  gets, read under clue-difficulty `--gimme G` (default 80), returned hardest-first. E.g.
  `mini 5 60 3 --max 90 --hard 6 --gimme 88` emits Saturdays.
- generate.py: blocked minis from a black-cell COUNT (not a template). `generate.py
  rows cols num_black min_score count [--nonsymmetric]` searches legal layouts and
  fills them. (Its old inline layout property-check is now `tests/test_patterns.py`.)
  With `--max-len K` it switches to the cap-driven path (D24): entries capped at K by
  black cells, so a grid bigger than the word data fills — e.g. `generate 10 10 0 60 3
  --max-len 5` (num_black `0` = let the cap choose the count). Adding `--gibbs` (cap mode
  only) draws the *layout* from the Gibbs energy field (D27) instead of the complete
  search: aesthetic-controlled density/spread and a guaranteed no-2x2-block texture, but
  not complete (a miss is budget exhaustion).
- puzzle.py: a whole *clued* puzzle as plain text to solve (grid + Across/Down clues).
  All **named flags**, not positional (D20): `puzzle --rows 5 --cols 5 --black 4
  --min-score 75 --difficulty wednesday [--no-symmetric] [--reveal]`. Clue generation
  is the one live step (the `clue` extra + a key); the grid search has no LLM
  dependency, and the UNSAT paths short-circuit before any clue call.
- solve.py: generate a clued puzzle, then have a Claude *agent* try to solve it and print
  the attempt with its turn-by-turn reasoning (D26) — the empirical difficulty probe. Named
  flags: `solve --difficulty saturday --policy crossing --max-turns 20 [--reveal]`. Two live
  steps (clues + solving; the `clue` extra + a key); the fill is LLM-free. `--policy` is the
  solver-skill knob (cell/word/crossing/none).

HTTP entry point (`web/`, D35; the `web` extra):

- `uv run --extra web uvicorn puzzledesk.web.main:app` serves `POST /puzzles` (generate a
  clued puzzle from a JSON `PuzzleRequest`, store it, return the `PuzzleView`) and
  `GET /puzzles/{id}` (read it back). Same fill+clue path as `cli.puzzle`; the `clue` extra
  + a key are needed only for real clue text (the grid search is LLM-free). See "Data flow
  for serving a puzzle over HTTP" above.

Benchmark/demo drivers (`scripts/`, loose, ANN-exempt; each builds the container
and uses the injected `lexicon`/`rng_factory` adapters):

- demo.py: correctness N=2..4. N=2 checks `backtrack` against brute-force ground
  truth (`backtrack ⊆ bruteforce`); above N=2 validity is by construction. (Also
  encoded in `tests/test_ground_truth.py`.)
- blackcells.py: blocked-grid fill — tiny-grid ground truth, filled grids from the
  curated list, and a quality ceiling (shortest slot's list runs dry first).
- largemini.py: the large capped-mini spike (D24) — why the count-driven search cannot
  cap entry length, the cap-driven search's black-count/timing, and fill rate from the
  cw 2..5 lists at 10x10 and 12x12.
- gibbs.py: the layout-sampler head-to-head (D27) — Gibbs energy field vs `gen_capped`'s
  complete search on density, spread, 2x2 blocks, diversity, and fill, at 10x10 and 12x12.
- scan.py: sweep seeds for a capped/Gibbs grid and rank the fills by cleanliness — reports
  each seed's *weakest word* (the acceptance bottleneck, invariant 4), longest entry, count
  of entries past length 5, and black count, then echoes the cleanest grid. A reusable form
  of the throwaway seed-sweep you'd otherwise write to pick a sample. `scan.py R C max_len
  min_score [--gibbs] [--nonsym] [--seeds N]`.
- ceiling.py: sweep thresholds with the complete solver to find where it goes
  UNSAT. Generalised: `ceiling.py N listname thresholds...` (listname "scored"
  or "cw"; default thresholds chosen per list).
- difficulty.py: structural checkability of generated minis — solves at a score band
  and reports each grid's *open* crossings (Natick risk) via `app.difficulty.analyze`,
  cross-referenced with word obscurity (D21). `difficulty.py N listname min [max]
  [obscure_below]` for squares; `difficulty.py blocked R C K [min] [obscure_below]` for
  blocked grids (open rate bucketed by the weak side's slot length). Both paths share
  one reporter over `FilledGrid.runs()`, so the metric is model-agnostic.
- solve_effort.py: the D26 experiment driver — does a solver's *reasoning effort* track
  puzzle difficulty? Sweeps a difficulty lever (clue Mon..Sat, model, policy) holding the
  grid fixed and reports the agent's thinking-token spend. Needs the `clue` extra + a key
  (it runs the live solver); numbers go to `docs/notes.md`.
- gen_scored.py: regenerate `scored_N.txt` from `words_N.txt` via wordfreq. Only
  needed if you change the weak list; requires the wordfreq package.

## bruteforce.py (`core/engines/`)

Exhaustive enumeration for tiny N (ground truth at N=2; N=3+ explodes on a
permissive list — do not enumerate the full curated list). Prefix-pruned. Used by
`demo.py` at N=2 and by `tests/test_ground_truth.py`.
