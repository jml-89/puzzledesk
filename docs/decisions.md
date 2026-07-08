# Decision log

Chronological record of design decisions, each with context, the decision, the
alternatives, and what would reverse it. Audience: an agent who needs to know why
the code is shaped this way before changing it. Newest decisions are appended at
the end. Wording is deliberately conventional/ADR-like.

## D1. Problem framing: double word square, small-first

Context: rebuild of a NYT-mini generator. A canonical mini is a 5x5 fully-checked
grid = a double word square of order 5 (five across, five down, all interlocked).
Decision: treat it as a constraint satisfaction problem and build small-first
(N=2 -> 3 -> 4 -> 5), validating each order before scaling. N=2 is brute-forceable
for ground truth. Rationale: dense interlock makes 5x5 hard to debug directly;
small orders isolate bugs. Reversal: none expected; this is scaffolding.

## D2. State = across words only; down words induced

Context: naive representation is 25 cells x 26 letters. Decision: represent state
as the N across words; derive down words from the columns; `energy = number of
invalid columns`. Rationale: collapses a 25-variable CSP to N variables and makes
validity N set-lookups. Alternatives: full 25-cell MRF (needed only if we ever
want per-cell soft factors that are not word-level). Reversal: reintroducing
per-cell learned factors (e.g. a diffusion model over letters) would want the
cell representation back.

## D3. Started with energy-based stochastic sampling

Context: user explicitly wanted post-classical CSP methods (sampling / message
passing / convolutional sample-space exploration), not deterministic backtracking,
motivated by (a) soft quality objectives and (b) grid diversity, and by prior pain
spending ~95% of effort tuning a search heuristic. Decision: first engine is
min-conflicts / annealed-Gibbs over the row variable, using the per-column
"allowed letters" marginal as the local move. Rationale: matches the stated
interest; energy-based framing unifies feasibility and quality as one objective;
gives a distribution of grids. Reversal: happened — see D7. The premise (soft
objective) was invalidated by D6.

## D4. Language/stack: Python + NumPy; JAX deferred

Context: choice between Go (repo vibe, fast core), Python (ecosystem), Rust, TS.
Decision: Python + NumPy; defer JAX until scale demands it. Rationale: the ceiling
we were reaching for (marginal-based / learned methods, parallel-chain
exploration) makes Python's numerical+ML ecosystem decisive, while small-N
correctness needs only NumPy. JAX would earn its place for parallel-chain sampling
IF soft preferences return. Reversal: JAX only becomes relevant again if the
sampler becomes primary (currently it is not — D7).

## D5. Weak word list first (dwyl + wordfreq), on purpose

Context: no wordlist in the environment. Decision: bring the solver up on a
deliberately weak/uncurated list — dwyl `words_alpha` filtered by length, scored
with wordfreq Zipf — before investing in a curated list. Rationale: separate the
packing problem from the word-quality problem; a weak list stresses packing and
lets us find the ceiling cheaply. Reversal: superseded for output by D8; the weak
list is retained as a baseline and for the packing/ceiling analysis.

## D6. Validator-first: acceptance is a bottleneck test, and it is a HARD bar

Context: initial quality metric was mean Zipf. That is wrong — a high average
hides one obscure word. Decision: the acceptance test is "every one of the 2N
words clears a threshold" — a minimum over words, not a mean — and it is a HARD
per-word bar. Consequence: acceptability collapses into feasibility on a
threshold-FILTERED list (filter to words >= T, solve feasibility, every result
passes by construction). This retired the soft-scoring machinery for the primary
path. Rationale: matches how a human judges a grid (one bad word ruins it), and
turns a fuzzy multi-objective into a clean feasibility question. Alternatives kept:
soft scoring still exists in the sampler for future genuinely-soft preferences,
and mini/ceiling pick the best-by-min-score among sampled grids. Reversal: if we
ever want to trade off "mostly great with one mediocre word" vs "all merely
acceptable", a soft objective returns — but the default is the hard bar.

## D7. Primary engine switched to complete propagation-backtracking

Context: D6 turned the task into feasibility on small, hard, filtered lists. On
those, min-conflicts wanders and restarts; measured 64-450x slower than
backtracking, and the gap GROWS as the list shrinks (i.e. exactly in the
high-quality regime). Decision: make prefix-pruned complete backtracking the
primary engine (`backtrack.py`); keep the sampler as secondary. Rationale:
systematic search is the right regime for small/hard; it is also COMPLETE, so it
can prove UNSAT (turn a ceiling into a theorem). Randomised candidate order
recovers per-seed diversity. Reversal: if the problem becomes big-and-soft again
(large list + genuine soft preferences), stochastic/parallel sampling could
retake primacy.

## D8. Enforce 10-distinct words (forbid the symmetric basin)

Context: the "best" high-quality 5x5 found was symmetric down the diagonal
(across == down), i.e. only N distinct words — a plain word square, an easy
degenerate basin the solver falls into because symmetry makes the down constraints
free. Decision: require all 2N words distinct, in both the acceptance test and the
backtracker's pruning/leaf check. Rationale: a genuine double word square (and a
real mini) never repeats a word; the symmetric basin was inflating both apparent
speed (17ms->420ms once removed) and apparent quality ceiling. Note: the SAMPLER
does not yet enforce this (D3 predates it). Reversal: none; this is a correctness
requirement for the object we claim to generate.

## D9. Curated lexicon swap confirmed the bottleneck

Context: after D6-D8 the analysis said "solver is done, the lexicon is the
bottleneck". Test: change ONLY the word list, no code changes. Decision: adopt the
Crossword-Nexus collaborative list (MIT licensed, scored 0-100 for
solver-enjoyment, includes proper nouns and de-spaced phrases) as the real list
(`cw_N.txt`); keep the weak list for analysis. Result: the honest distinct-5x5
ceiling moved from "provably UNSAT at Zipf>=4.0" (weak) to "every word scores
>=90" (curated). Rationale: this is the controlled experiment confirming the
difficulty was in the data, not the algorithm; it also fixes the proper-noun/phrase
texture. Note the SCORE SCALE CHANGED (Zipf 0..8 -> crossword 0..100); thresholds
are per-list. Reversal: a different curated/scored list could be swapped the same
way; the engine is list-agnostic via `from_scored_file`.

## D10. Ship as initial spike; promote branch to main, no PR

Context: repo was empty, so the working branch became the only branch and the
GitHub default. User wanted to wrap the spike with no ceremony. Decision: push the
spike HEAD as `main` (repo mainline) rather than opening a PR (no base branch
existed to merge into anyway). Rationale: minimal ceremony; establishes a
baseline. Follow-up (since done): GitHub's *default branch* setting, which had
pointed at `claude/empty-repo-review-0vagwh`, has been flipped to `main`.
Reversal: n/a.

## D11. Refine the sampler to enforce distinctness; pick its strategy by measurement

Context: after D8, `validate` and `backtrack` enforced distinctness but the
sampler (D3) did not. That left it emitting degenerate squares, and the two
scripts that validated sampler output (`compare.py`, `frontier.py`) asserted
`validate(...).ok` on non-distinct grids and crashed. The stated 64-450x
sampler-vs-backtrack figure was also measured distinctness-OFF, so it no longer
described the problem the system actually solves. Decision: make the sampler
enforce distinctness (`distinct=True`) via a vectorised duplicate-pair penalty in
the move (`_distinct_penalty`), weighted below one valid column so feasibility
still dominates; fix the two scripts to solve the distinct problem; and settle HOW
the sampler should enforce distinctness by measuring two strategies
(`scripts/samplers.py`): `gate` (restart on a degenerate valid grid) vs `penalty`
(guide off the basin). Result: on N=5 filtered lists the two are comparable —
penalty is never worse on solve rate but adds per-step overhead — because
distinctness is not the sampler's bottleneck (reaching feasibility is). Kept
penalty as the default (the principled "actively enforce" behaviour), gate as the
baseline. Re-measured on the distinct problem, backtracking is ~50-80x faster and
its solve-rate stays 10/10 where the sampler collapses to 2-3/10 — D7 reconfirmed.
Rationale: the sampler must produce the object we claim (a genuine double word
square) for the comparison and the scripts to be honest; the strategy choice is
made by data, not assertion. Reversal: if soft preferences return and the sampler
becomes primary, revisit whether the penalty overhead is worth vectorising
further (or move the whole thing to JAX parallel chains).

## D12. Spike black cells as a separate slot-graph model, not a warp of the square

Context: the fully-checked square is the mini's special case; real crosswords have
black cells. The square's power came from the induced-column trick (state = across
words, downs read off columns), explicitly flagged load-bearing. Black cells break
it: entries become variable-length slots that start/stop at blocks, so there is no
whole column to read. Decision: model the blocked case as a SEPARATE, coexisting
representation rather than generalising the square. `blocked.py` parses a `.`/`#`
pattern into a slot + crossing graph; `MultiLexicon` buckets words by length and
`Lexicon.matching(pattern)` answers the per-slot fit query; `fill.py` fills it with
the SAME complete backtracking that won for the square (D7), adding MRV ordering
(varying lengths make "fewest candidates first" pay off) and grid-wide distinctness
(crosswords never repeat an entry). Scope held deliberately tight for a spike: the
block PATTERN is input, not generated (legal-layout generation — symmetry,
connectivity, min-length — is its own problem); word lists cover lengths 2..5, so
demos use slots <= 5. Small-first kept: `enumerate_fills` is brute-force ground
truth on a tiny blocked grid, and the solver's output is asserted to be a subset
(cf. demo.py at N=2). Findings: (a) the curated list has no 2-letter entries above
any real bar, so grids with length-2 slots are UNSAT on it — the list, not the
solver, is again the limit; (b) on a fixed pattern the quality ceiling is set by
the SHORTEST slot's bucket emptying first (length-3 hits zero between bar 90 and
92), the blocked echo of "the lexicon is the bottleneck". Rationale: reuse the
proven engine and Lexicon machinery; change only what the geometry forces.
Reversal: none for the model; the tight scope items (pattern generation, longer
lists, themes) are follow-on spikes, see open-questions.

## D13. Black cells become a PARAMETER: generate the layout from a count

Context: D12's spike left the block PATTERN as input — you hand `blocked.py` the
exact `.`/`#` template. The open question ("Block-pattern generation") framed the
missing piece as its own CSP: rotational symmetry, full connectivity of the white
cells, minimum word length / no unchecked cells, and a black-cell target. Decision:
add `patterns.py` — given a shape and a *number* of black cells, generate the legal
layouts and let the search place the blacks, rather than committing a template. A
layout is legal iff it has exactly `num_black` blacks, is 180°-rotationally
symmetric (default; the American convention, toggleable), is *fully checked* (every
white cell lies in an across and a down run >= min_len — i.e. no white run has
length 1..min_len-1, which subsumes blocked.py's no-orphan condition), and its
white cells are 4-connected. Generation is complete backtracking over the cells,
grouped into 180°-rotation ORBITS when symmetric so the orbit is the unit of choice
(this is also why an odd black count needs a centre cell — even-celled grids reject
odd counts, and a black centre in an odd square like 5x5 is itself illegal because
it splits the middle row/column into sub-min_len runs). Randomised orbit order gives
per-seed diversity without changing the reachable set (verified: the enumerated set
is seed-invariant). `fill_by_count` composes the layout search with `fill.solve`:
first layout that admits a distinct fill wins. Rationale: this is the same thesis
as everywhere else — complete search on a bar-filtered list — extended one level up
from "fill this grid" to "find a grid and fill it", so a `None` result is a genuine
UNSAT proof (no legal K-black layout of this shape fills from these lists), not a
timeout. Kept the square/blocked split intact: `patterns.py` only produces
`BlockedGrid`s and reuses `fill.py` unchanged. Small-first preserved:
`scripts/generate.py` enumerates every legal layout on a tiny case and asserts the
invariants (symmetry, count, fully-checked, connected, duplicate-free) before the
demo, the layout analogue of D12's `enumerate_fills` ground truth. Alternatives
considered: a stochastic layout sampler (rejected for the same reason as D7 — small
hard search wants completeness); making symmetry mandatory (rejected — kept it a
default-on toggle so non-symmetric experiments stay possible). Reversal: none for
the model; a smarter layout enumeration (dedup by symmetry class, prune connectivity
incrementally) is a performance follow-up, not a design change.

## D14. Hexagonal layering, a DI container, and an injected Prng — enforced

Context: the engine and data model were clean, but the *structure around them* was
not. CLAUDE.md described four conceptual layers (kernel / shell / tools /
benchmarks) that existed only as convention: the "shell" was smeared into each
script's `__main__` (a repeated `DATA = Path(...)`, hand-rolled argv parsing, a
`render`/`show` function copied between `mini.py`, `generate.py`, `blackcells.py`);
every engine constructed its own `np.random.default_rng(seed)`, burying an effect
inside otherwise-pure code and making "inject a fake stream under test"
impossible; and file I/O lived in the kernel (`Lexicon.from_scored_file` read a
path). Nothing stopped a future change from importing stdout into `src/` or
calling a solver from the wrong place — the boundaries were review conventions, not
facts.

Decision: adopt a **hexagonal (ports & adapters) architecture** with a single
*linear* import stack, enforced mechanically by **import-linter**:

    core  <  app  <  adapters  <  bootstrap  <  cli

- **core** — the pure kernel (grid models, engines, lexicon, acceptance test).
  Deterministic, no I/O. It defines the one port its engines need from outside,
  `core.rng.Rng`/`RngFactory`, and takes randomness as a parameter instead of
  opening its own Generator. Lexicon file-reading is gone from here: the kernel now
  *parses text* (`Lexicon.from_scored_text`/`from_words_text`,
  `MultiLexicon.from_scored_texts`) and an adapter does the read.
- **app** — use-case services (`MiniService`, `BlockedGenerateService`) plus the
  ports they need from infrastructure (`LexiconSource`, `Writer`). Services
  orchestrate the core through ports and return structured results; they never
  touch a concrete adapter, stdout, or a file.
- **adapters** — the infrastructure that implements the ports: `NumpyRngFactory`
  (the injected Prng — `np.random.default_rng` lives in exactly one file now),
  `FileLexicon` (the filesystem read that used to sit in the kernel), `StreamWriter`
  /`CapturingWriter`. Adapters sit *above* app in the stack because they *implement*
  app's ports; that ordering is what lets one linear `layers` contract forbid
  `app → adapters` (the DI inversion) while allowing `adapters → app`.
- **bootstrap** — the composition root: `build()` assembles a `Container` in three
  explicit stages (config → adapters → services). The one place that knows every
  concrete type.
- **cli** — thin entry points: argv → build → run service (or, for benchmarks,
  drive the core engines directly through the container's adapters) → present.
  `scripts/*.py` for the tools became two-line shims; benchmark/demo drivers stay
  in `scripts/` (loose, ANN-exempt) but now build the container and use the
  injected adapters instead of a bare `default_rng`/`DATA` path.

The **Prng-as-a-service** is the load-bearing example: randomness is the kernel's
one impure dependency, so it is injected (`RngFactory` → a fresh `Rng` per seed) at
the composition root. Reproducibility is preserved *exactly* — `factory.create(seed)`
returns `np.random.default_rng(seed)`, so a `(lists, seed)` pair still reproduces a
result bit-for-bit (verified: the first `mini 5 70` grid is unchanged).

Testing was promoted from ad-hoc script asserts to a real **pytest suite** (added
to the `dev` group), and it *exploits* the DI: services are driven by an in-memory
`LexiconSource` and a recording `RngFactory` (no files, no global RNG). The
small-first ground-truth checks that lived inside `demo.py`/`generate.py`/
`blackcells.py` are now tests (`tests/test_ground_truth.py`, `test_patterns.py`);
the drivers keep runnable copies.

Rationale: make the layering a *fact*. import-linter turns "the kernel stays pure"
and "app does not depend on a concrete adapter" into a build-gate check (it fails
on a forbidden edge — verified). The DI makes wiring legible (one staged
composition root) and testing cheap (inject fakes). Scope held: the grid model,
engines, invariants (0–5), and every user-visible artifact are unchanged; this is a
structural refactor, not a behaviour change. Python floor stays `>=3.10` (no 3.11+
features introduced).

Alternatives considered: keep the path-based `from_scored_file` in the kernel as a
grandfathered exception (rejected — a true front/back split wants the read in an
adapter, and the kernel is more testable parsing text); a separate `ports` package
below everything (rejected — ports that reference core types belong *with* the
layer that owns them, which also keeps the import graph linear and the contract a
single `layers` rule); express `app`/`adapters` independence with an extra
`independence` contract (unnecessary once adapters sit above app — the linear
`layers` contract already forbids `app → adapters`). Reversal: the layering is
meant to stay; if the sampler ever becomes primary and moves to JAX parallel chains
(see D3/D7), the `Rng` port is exactly the seam to swap the randomness adapter
without touching the engines. The tool/benchmark *directory* split
(`scripts/tools` vs `scripts/bench`, console entry points for every driver) remains
a deliberate follow-up; `cli` now groups them by intent and adds `[project.scripts]`
for the two tools.

## D15. Clue generation: an interface, defined before the implementation

Context: the grid problem is finished; a mini is not a puzzle without clues. Clue
generation is the next spike, and it is a genuinely *different regime* from
everything the system does so far. The solver is complete and deterministic — its
`None` is a UNSAT proof; distinctness is a theorem. Clue writing is soft,
generative, subjective, with no completeness and no ground truth. Before writing a
line of it we designed the boundary: what does a clue provider *see*, and what does
it *return*? Getting that wrong pollutes the pure core with the softness or
forecloses whole styles of clue.

Decision: fence clue generation behind a single `ClueProvider` port in `app`
(`app/clue.py`), so all subjective/generative behaviour lives *behind* the port and
the application applies only deterministic constraints on top. The port is defined;
the impl (a Claude adapter, a ranking pass, an exporter) is deliberately deferred.
The shape, arrived at by iterating the boundary hard:

- **The port speaks the puzzle's canonical, space-first form.** `app/puzzle.py`
  defines `FilledGrid` — a grid of cells, each a string (a letter, or several for a
  rebus) or `None` for a black square. That is the whole truth. The across/down
  words (`runs()`), the crossing graph (`crossings()`), and the numbering are
  *derivations* computed on demand, never stored — the same way a Sudoku is a 9×9
  grid, not a pre-materialised `{rows, columns, boxes}` object.
- **"What to clue" is an explicit input, not a baked-in policy.** `clue(grid,
  targets, *, style, n)` takes the `Target`s to clue. A `Target` is an ordered run
  of cells + the answer they spell + a `kind` (`"A"`/`"D"`/`"meta"`), with spatial
  identity `(start_cell, kind)`. Entries come from `grid.runs()`; a puzzle-level
  META (the highlighted-cells-spell-the-answer lineage) is *just another target*
  over scattered cells — so metas need no interface change and no separate return
  channel. This also moves "clue every run" out of the adapter (a policy) and into
  the app (where policy belongs).
- **The `how` axis is a `ClueStyle`.** A comparable, sweepable `Difficulty` knob
  (Mon..Sat, `IntEnum`) plus free-form `instructions` for the long tail (tone,
  spelling, an imposed theme, taboo words). Output is `Mapping[TargetId,
  Sequence[Clue]]` — up to `n` candidates per target, keyed by spatial identity
  (never by answer value); a word the provider cannot clue maps to an empty
  sequence, so the port stays total.
- **Representation-agnostic projection (the anti-corruption layer).** Both core
  grid models render into `FilledGrid` (`filled_from_square`,
  `filled_from_blocked`), so the clue port never learns which model produced the
  fill — honouring invariant 0 (two coexisting grid models).

The design rule this crystallised, reusable beyond clues: **send the canonical
aggregate; derive views at the point of use; introduce a modelled structure only
where an external contract forces it.** The one structure beyond the grid is
`Target`, forced because the *output* of cluing is per-word, not per-cell.

Landed interface-only: `FilledGrid`/`Target`/`Crossing` + `runs()`/`crossings()`,
the `ClueProvider` port + `ClueStyle`/`Clue`/`Difficulty`, the two projections, and
a `FakeClueProvider` (tests/fakes.py) driving one mini end-to-end with no network —
the DI payoff again: the whole pipeline is exercised before any adapter exists. The
layers contract is untouched (`ClueProvider` sits in `app`).

Alternatives considered — each an iteration of the boundary:
- **Answer as a bare `str`** (per word): rejected — it does not merely drop
  metadata, it dissolves the aggregate's defining invariant (the interlock: crossing
  entries agree on the shared letter), and forecloses intersection-aware and
  difficulty-by-gettability cluing.
- **A semantic `Puzzle{entries, crossings}` aggregate**: rejected — that is
  data-first re-architecting of a *derivation* dressed as DDD; it pre-materialises
  a cache and privileges one reading of the grid.
- **Passing a core grid object** (`DoubleSquare+state` / `BlockedGrid+assign`):
  rejected — couples cluing to solver internals and to the two-model split.
- **Per-cell grid decoration + a separate puzzle-level meta return channel**:
  rejected in favour of the `Target` abstraction, which absorbs both with no extra
  structure. Purely *aesthetic* shading/circling (decoration that spells nothing)
  is an `.ipuz` **export** concern, added there when a puzzle type needs it.

Reversal: the port is the seam to swap providers — a live Claude adapter, a 50%-
cheaper Batch-API adapter, or the fake — without touching anything above or below.
Generating meta puzzles means constructing a meta `Target`; no interface change.
The soft objective that D6/D7 retired at the *fill* layer genuinely returns here at
the *clue* layer — quarantined behind this port, never in `core`.

## D16. Clue service + the Claude adapter: the LLM lives in the adapter, not the port

Context: D15 defined the `ClueProvider` port; this is the first implementation
behind it — the deterministic orchestration and the real (soft) provider — plus the
question the port raised: *the clue stage depends on a language model, so where does
the LLM interface go?*

Decision, split by half of D15's soft/deterministic line:

- **`app/cluing.py::ClueService` — the deterministic half.** Pure orchestration over
  the `ClueProvider` port: ask for candidates per target, keep the first that clears
  the **hard** constraints, report the rest as `unclued`. The hard set is minimal and
  universal — a clue is non-empty and must not contain its own answer (case-insensitive
  substring). Softer rules (no cross-answer leak, no duplicated clue form, difficulty
  calibration) are judgment calls left to the provider or a future `ClueRanker`, not
  baked in here. Selection is "first surviving candidate" (providers order best-first).
  A target whose every candidate is rejected is surfaced honestly (`CluedPuzzle.unclued`)
  rather than given a bad clue. Fully testable with the fake — no model, no network.

- **`adapters/claude_clue.py::ClaudeClueProvider` — the soft half, and the key call.**
  The LLM does **not** become a port at the app layer. The app depends on
  `ClueProvider`, which speaks grids and clues; a generic `LanguageModelProvider`
  dependency would leak infrastructure language (messages, tokens) up into the domain
  and undo the hexagon. Instead "don't reinvent the wheel" applies *inside* the
  adapter: it uses the Anthropic SDK for the client, retries, and structured outputs,
  and **lets the SDK resolve credentials from the environment** (`ANTHROPIC_API_KEY`,
  or an `ant auth login` profile) — we never read the key ourselves. `anthropic` is an
  **optional extra** (`clue`), imported lazily so the package installs, imports, and
  the container `build()`s without it; only a live clue call needs the SDK and a key.
  Structured output uses a raw JSON schema + `json.loads` (no `pydantic` dependency).
  The prompt/schema/parse helpers are pure and unit-tested; the live `messages.create`
  call is the one untestable-in-CI part. The default model is the latest Claude per
  repo policy.

- **DI: the container absorbs it unchanged.** `ClueService`'s dependency is the domain
  port; the LLM is a dependency of the *adapter*, one level down, exactly where
  `NumpyRngFactory`/`FileLexicon` sit. The staged `build()` grows one adapter with a
  lazy sub-dependency and a `Config.clue_model` knob — no new pattern, and no DI
  *framework* (the ~50-line hand-rolled composition root is a feature at this scale,
  not debt). `ClueService` never learns an LLM exists, which is the test that the
  boundary is right.

Alternatives considered:
- **A `LanguageModel`/`LanguageModelProvider` port at the app layer** (the tempting
  reading of "the LLM is an interface in our system"): rejected — it couples the
  domain to an infrastructure abstraction. Applying D15's own rule to *ports*:
  introduce a modelled interface only where a contract forces it. A single LLM-backed
  adapter forces nothing; a *second* consumer (a `ClueRanker`, a theme detector) would
  justify a minimal, our-own `LanguageModel` seam for adapter testability — and only
  then, wrapping the SDK, never a framework.
- **A cross-provider framework (LangChain / LiteLLM / Pydantic AI):** rejected — they
  buy provider-agnosticism we deliberately declined (repo policy = latest Claude), at
  the cost of weight and losing clean access to Claude-native features (Batch API,
  prompt caching, adaptive thinking). The "wheel" worth reusing is the SDK, in the
  adapter — not a portability layer we won't use.
- **`pydantic` for structured outputs:** rejected — the raw JSON-schema path via the
  SDK avoids a new runtime dependency for a single call site.
- **A DI container library (`dependency-injector`, `svcs`, …):** rejected — auto-wiring
  magic is a liability at this scale; the explicit composition root stays.

What is NOT done: no live round-trip is exercised (this environment has no key/egress);
the prompt is a first draft and clue *quality* is the next iteration. A 50%-cheaper
Batch-API adapter and an `.ipuz`/`.puz` exporter are the natural follow-ons, both
additive behind the existing ports.

Reversal: swap providers behind `ClueProvider` (batch adapter, a different vendor
adapter, the fake) with nothing above the adapter changing. The soft objective D6/D7
retired at the fill layer now lives, quarantined, at the clue layer — behind this
adapter, out of `core`.
