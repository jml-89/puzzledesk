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

## D17. The clue key: a configurable, off-normal env var, resolved in the composition root

Context: the Claude adapter (D16) let the SDK resolve credentials from the standard
`ANTHROPIC_API_KEY`. In our environments that name is *auto-detected by other tooling*,
and that coupling has caused trouble — the key gets picked up where we don't want it.
We want the clue key to live under a name nothing else claims, wired the same way as
every other piece of configuration — not through a bespoke path.

Decision: `Config.clue_api_key_env` names the env var (default `ANTHROPIC_API_KEY_TWO`);
the **composition root** reads it and injects the resolved value into the adapter as a
plain `api_key`.

- **The name is a `Config` knob, not a port change.** `Config.clue_api_key_env` is
  threaded through `build()`; the `ClueProvider` *port* is untouched — it defines a
  capability (`clue(...)`), and credential wiring is *construction*, not part of that
  contract. The knob rides on the adapter's `__init__` beside `model`/`max_tokens`, one
  layer down from the service that never learns a key exists (D15's "model only where a
  contract forces it", applied to the port).
- **The composition root owns the environment boundary; the adapter is a pure
  value-taker.** `build()` resolves the name → value (`_resolve_api_key`) and passes
  `ClaudeClueProvider(api_key=...)`, whose constructor now mirrors the SDK's own
  `anthropic.Anthropic(api_key=...)`. When the key is `None` (var unset/blank, or name
  `None`) the adapter defers to the SDK's own resolution, so normal setups still work.
  This keeps the clue adapter uniform with `FileLexicon`/`StreamWriter`/`NumpyRngFactory`
  — none reach into ambient global state; each takes its dependency as a constructor arg
  — and keeps the environment read in exactly one place. The container still builds
  without a key (the read yields `None` harmlessly) and still imports the SDK only on a
  live call. `_resolve_api_key` is pure and unit-tested.

Alternatives considered:
- **Keep the SDK's `ANTHROPIC_API_KEY` default (D16 as-is):** rejected — it is exactly
  the auto-detected name whose side effects we are avoiding.
- **Have the adapter read `os.environ` itself (the first cut of this change):**
  rejected on review — it made the clue adapter the only one reaching into ambient
  global env, unlike every other adapter. Resolving at the composition-root boundary and
  injecting a value is the more conventional DI shape, leaves the adapter trivially
  testable (no env monkeypatching), and makes its constructor read like the SDK's. The
  "read eagerly at `build()` breaks laziness" worry was unfounded: the read yields `None`
  when unset, so the container still builds keyless and still imports the SDK only on a
  live call.
- **A second meta env var to name the key var (`PUZZLEDESK_CLUE_KEY_ENV`):** rejected —
  it trades a code-level default for more env plumbing to manage; the `Config` default is
  the simpler seam and the fallback keeps it safe.

Reversal: set `Config.clue_api_key_env` to `None` (or `"ANTHROPIC_API_KEY"`) to return
to the SDK's own resolution; the port and services are unaffected.

## D18. OS reach is confined to init — the entry-point → bootstrap → container shape, fenced by import-linter

Context: D17 moved the one environment read into the composition root. That is an
instance of a broader discipline worth naming and holding to. There are two kinds of
program — the long-lived daemon and the run-fast-and-exit tool — and ours is firmly the
latter. For that camp the OpenBSD `pledge(2)`/`unveil(2)` model is a clean fit: grab
the operating-system capabilities you need *at startup*, then run the rest of the
program confined, without reaching back out. We want to (a) formalise the shape that
already does this, and (b) stop the pure layers from quietly reaching the OS later.

Decision, two parts — a stated pattern and a mechanical fence:

- **The pattern: entry point → bootstrap → service container → steady state.** A `cli`
  entry point does argv → `build()` → run a service → present. `build()` (the
  composition root, `bootstrap/`) is the *only* place that touches the environment: it
  reads the configured key var (D17), fixes `Config.data_dir`, and resolves the output
  stream — the "init grab". It hands back a frozen `Container`; from there the services
  run in steady state over ports, reaching the OS only through capabilities declared at
  init. The environment is grabbed once and never again; filesystem access is
  *unveil*-shaped — the directory is fixed at init, and `FileLexicon` reads on demand
  but only under it. `core`/`app` are pure functions over their inputs.

- **The fence: an import-linter `forbidden` contract.** `core` and `app` may not import
  `os`, `io`, `sys`, `subprocess`, or `socket` (`[tool.importlinter]`, alongside the
  D14 `layers` contract; `include_external_packages` lets the contract name stdlib). A
  planted `import os` in a `core` submodule is caught, so the rule is enforced, not just
  asserted — the same "the linter is what keeps them so" stance as D14.

Honest about what it is *not*: an import-time fence, not a sandbox. It does not stop a
runtime reflection trick (`__import__("os")`, `getattr`), it exempts
`adapters`/`bootstrap`/`cli` by necessity (they *are* the OS edge), and it does not
touch the Anthropic SDK's own fallback env resolution (D17, vendor-side, opt-in). It is
a nice start that gets the idea across and keeps the kernel honest — no more.

Alternatives considered:
- **Runtime capability-dropping (a literal `pledge`):** rejected — no portable Python
  equivalent, and the payoff for a short-lived batch tool doesn't justify the machinery.
  The import fence buys most of the intent at compile time for free.
- **Forbid the OS modules in `adapters` too:** rejected — adapters are exactly where the
  disk read, the streams, and (in `bootstrap`) the env grab must live. The fence targets
  the *pure* layers, which is where "reaches the OS" is a real bug.

Reversal: drop the `forbidden` contract (and `include_external_packages`); the `layers`
contract, the composition-root pattern, and all code are unaffected.

## D19. Retire the sampler — a spike that was measured, lost, and is now recorded not kept

Context: the stochastic sampler (`sampler.py`) was the *original* engine (D3): energy-based
min-conflicts / annealed-Gibbs, chosen because the user wanted post-classical CSP methods and
because the premise was a **soft** quality objective plus grid diversity. Two later decisions
undercut that premise. D6 reframed quality as *feasibility on a threshold-filtered list* — a
hard bar, no soft objective left to sample against. D7 then measured complete backtracking as
64–450× faster on exactly the small/hard/filtered lists high bars produce, and made it primary.
D11 taught the sampler distinctness so the two engines solved the *same* problem, and the
head-to-head (`compare.py`, notes.md) was unambiguous: ~50–80× slower on the distinct problem,
and its **solve-rate collapses** (3/10 at Zipf≥3.5) exactly where backtracking stays 10/10 and,
being complete, can additionally *prove* UNSAT. The strategy study (`samplers.py`) further showed
distinctness was never the sampler's bottleneck — reaching feasibility is — so even its own
refinement bought only a marginal edge over the naive gate.

So the hypothesis behind D3 — "a sampler may beat / complement simple backtracking here" — was
tested and **falsified**. The sampler earned its place in the *arc* (it produced the acceptance
test as a feedback signal, which is what corrected the objective), but it never earned an
operational place in the shipped system. The lingering cost was real: five benchmark drivers that
only exercised it (`compare`/`frontier`/`samplers`/`quality`/`bench`), one of which (`compare.py`)
hung past a 300 s timeout on its own default config and would trip the next developer; plus dead
kernel surface that existed solely for its quality move (`Lexicon.allowed_and_scores_at`) and
solely for its moves (`Rng.choice`).

Decision: **delete the artifact, keep the lesson.** Removed `core/engines/sampler.py`, the five
sampler-only drivers, the N=2 sampler ground-truth test (its subject is gone; `bruteforce` remains
the ground truth and `backtrack` has its own subset test), and the sampler-only kernel surface
(`allowed_and_scores_at`, `Rng.choice`). `scripts/demo.py` was rewired onto the surviving
backtracker (same N=2..4 correctness/diversity demo, now `backtrack ⊆ bruteforce`). The measured
numbers that justify the verdict stay in `docs/notes.md`, the README "arc" keeps the origin story
in past tense, and the open question "does the sampler earn its keep" is resolved *No* here.

Rationale: for a **failed spike**, a decision record plus git history is a stronger form of memory
than dead-but-runnable code. Code left in place rots silently, invites accidental use, taxes every
`grep`/exploration with false weight ("there are two engines"), and — as the hang showed — ships
foot-guns. This repo's doc discipline (this log, notes.md, open-questions.md, the README arc)
carries the *why* more durably than the module ever did. Nothing is lost: the sampler is one
`git show` away, and D3→D6→D7→D11→D19 is the full narrative of an idea that was worth trying and
worth removing.

Alternatives considered:
- **Quarantine it (gate behind an opt-in flag, heavy "not great" banner, leave the code):**
  rejected — pays the maintenance/attention tax *forever* in exchange for optionality we're
  unlikely to exercise; the worst-of-both "tombstone in place".
- **Keep a single minimal `sampler.py` as a runnable demo of the arc's step one** (delete only
  the benchmarks): rejected — the numbers in D19/notes.md tell the origin story better than a slow
  live run, and a live import is exactly the surface that rots.
- **Delete with no record:** rejected — a spike deleted silently gets *re-attempted*; the whole
  value of running it is the recorded verdict.

Reversal: restore `sampler.py` and its port/lexicon surface from git if a **big-and-soft** regime
returns — a large list with *genuine* soft preferences (themes, per-batch novelty; see
open-questions "Grid variety"), which is also the only condition under which D3/D7 said stochastic
or JAX parallel-chain sampling could retake primacy. That is a new spike with a new hypothesis, not
a resurrection of this one.

## D20. Difficulty is a layered decomposition; build only the complete, deterministic slices

Context: "how hard is a mini" had one knob — the clue `Difficulty` enum (D15, Mon..Sat)
— and no model behind it. The question we actually asked: for a *dense* mini, what
*is* difficulty, and which parts of it can this repo treat the way it treats
everything else (a complete, provable signal) versus which parts are irreducibly soft
(need human solve data we do not have)? Three literatures describe one phenomenon:
**Item Response Theory** gives a per-entry logistic gettability `P = σ(θ − b)`
(ability minus item difficulty); **flow theory** puts the fun at θ≈b; **queuing
theory** explains the *effort* blow-up (time-to-solve scales like `1/(1−ρ)` as the
puzzle's demand approaches the solver's capacity). The synthesis: IRT is the smooth
per-entry primitive; the queuing/effort blow-up is what *emerges* when you compose
per-entry gettability across an interlocked grid. The composition operator is the
crossings — so difficulty is "the marriage of the word and its crossing support",
and a mini solves as a **percolation/belief-propagation cascade**: get the gettable
entries, they donate letters, neighbours' effective difficulty collapses, the grid
unzips — unless a cluster of mutually-hard, weakly-supported entries stalls the
cascade (the queuing blow-up: the solver is *stuck*).

Decision: model difficulty as four layers, each landing on the layer of the hexagon
where its regime already lives, and **implement only the two that are complete and
deterministic** — filter-and-prove, the house style (D6/D7) — leaving the soft ones
recorded but unbuilt until there is data to calibrate them.

- **A. Word prior (complete, `core`, *built*).** A word's intrinsic gettability is
  (inverse) obscurity = its score. Today `Lexicon.filtered` is a one-sided *floor*;
  difficulty wants a two-sided **band** `[lo, hi]`, so "harder" means *drawing from
  the obscure band*, not merely lowering the floor. `filtered(min_score, max_score)`
  (and the `LexiconSource`/`MiniService`/`cli.mini` thread) makes an obscurity band a
  first-class generation parameter. Because backtracking is complete, a banded run
  still yields a **difficulty ceiling** as a theorem (a `None` = "no distinct mini
  exists drawn from this band"), exactly parallel to the quality ceiling of
  `ceiling.py`. This is a filter operation in the complete regime — *not* something to
  sample.
- **A′. Structural checkability (complete, `app`, *built*).** The mini-specific
  pathology is the **Natick**: two obscure entries crossing at a letter neither word
  pins, so the solver can only get it by *knowing* one word outright. That is a
  low-support percolation stall at one cell, and it is *computable from the lexicon
  with no solve data*: for each crossing cell, free that cell in the across word and
  count the distinct letters the rest of the across word still admits
  (`Lexicon.n_letters_at`), likewise for the down word; the cell is **forced** if
  either count is 1 (one direction determines the letter) and **open** otherwise.
  `app/difficulty.analyze` reports the open crossings of a `FilledGrid`. Two modelling
  choices are load-bearing and documented at the call site: (i) openness is scored
  against the solver's **full** vocabulary (the unfiltered list), not the
  generation-filtered list — a solver knows all words, not only the ones above the
  bar; (ii) it is the **final-state, maximal-support** reading (the rest of each word
  is assumed known), so an open crossing is *unavoidably* hard regardless of solve
  order — a sound, conservative signal, not a full solve-trajectory simulation. This
  is a `core`-computable structural difficulty signal that word-score alone cannot
  see (a grid of all-common words can still hide an open crossing; a grid of obscure
  words can unzip cleanly). `analyze` couples to nothing in `core`: it takes an
  `options(answer, pos) -> int` callable, so it is representation-agnostic (square or
  blocked) and trivially fakeable.
- **B. Clue transform (soft, `app`/adapter, *deferred — the knob exists, calibration
  does not*).** The same answer is Monday or Saturday depending on the clue; the clue
  *shifts* effective `b` for a fixed grid, which is why word- and clue-difficulty
  *decouple and compensate* (hard word ↔ gentle clue). This already has a home: the
  `Difficulty` enum behind `ClueProvider` (D15/D16), in the one regime with no
  completeness. It stays soft and sampled (n candidates, rank); what is missing is
  *calibration* — proving a clue is "Wednesday" needs human solve logs, which this
  environment does not have (cf. open-questions "solvability/fun needs playtesting").
- **C. Batch curation (scheduling, above the generator, *deferred*).** The "normal
  distribution of difficulty" is a property of a *batch/week* (mostly medium, few
  extreme), not of one grid — it is the open "Grid variety across a batch" problem,
  needing a per-puzzle difficulty number to schedule against. Recorded, not built.

Rationale: this is D6's move applied to a second axis. D6 turned *quality* into
feasibility on a filtered list; difficulty's word-and-structure layers are likewise
*complete* (filter, prove, measure) and belong in `core`/`app`, while its clue layer
is *soft* and stays quarantined behind the existing port exactly as clue *quality*
does. Splitting the axis this way keeps the epistemics honest: we ship the slices we
can prove and are explicit that the rest awaits data. It also retires a tempting
error — a single "difficulty sampler" spanning words and clues — which would cut
across the complete/soft seam the architecture already draws (D19 removed a sampler
for precisely the complete-regime half). Note the pleasing inversion: message-passing,
evicted from *generation* (D3→D19) because generation is hard-bar feasibility, is the
right lens for *solver difficulty* — the soft, probabilistic regime returns, on the
analysis side, and D15's interface already anticipated it (it rejected "answer as a
bare `str`" for foreclosing "difficulty-by-gettability cluing").

Alternatives considered:
- **One difficulty knob / one sampler for both words and clues:** rejected — conflates
  a complete filter (words, structure) with a soft sample (clues). They are different
  regimes on different layers; the seam is the point.
- **Model the full solve trajectory (order-dependent cascade / BP marginals) now:**
  rejected for the first cut — it needs a solver-ability model and buys little over the
  conservative maximal-support reading, which already flags the unavoidable Natick.
  The trajectory model is the natural next spike *if* solve logs arrive (it is where a
  real message-passing/marginal computation would earn its keep — see D19's reversal
  condition).
- **Put `analyze` in `core` over `DoubleSquare`:** rejected — it would serve only the
  square model and re-import the two-model split into a place that does not need it.
  `FilledGrid` (the D15 anti-corruption form) is exactly the representation-agnostic
  input, so the metric lives in `app` and reads both models for free.
- **Weight openness into a single "Natick score" inside `analyze`:** rejected for now —
  kept `analyze` purely structural (openness) and left the obscurity cross-reference
  (openness × low score = the *unfair* Natick) to the `scripts/difficulty.py` driver,
  where the per-list score scale (invariant 4) is in hand. A fused score can move into
  the metric once its scale is settled.

Reversal: none for the decomposition. The band is additive and default-off
(`max_score=None` == today's floor). If solve logs arrive, layers B and C get built and
A′ grows the trajectory reading; the `options` seam in `analyze` is where a marginal/BP
computation would slot in without touching the callers.

## D21. Solve order: the dynamic difficulty reading (grow A′ from snapshot to cascade)

Context: D20's `analyze` is the **maximal-support snapshot** — it asks "at full
support, is this crossing letter forced?" and deliberately *defers* the
order-dependent solve trajectory ("needs a solver-ability model, buys little over the
conservative reading"). But the snapshot conflates two very different entries: an
obscure word whose crossings *force* it by the time a solver reaches it (fine) and one
that stays genuinely open (a Natick). Only the *order* distinguishes them. A human
solves easiest-first — gimmes they know from the clue, then whatever the accumulated
crossing letters make inferable — so support **arrives over time**, a percolation
cascade. Modelling that order is the promised A′ follow-up, now taken because it is the
cheapest lens that separates "obscure-but-gettable" from "obscure-and-stuck".

Decision: add `app/difficulty.solve_order(grid, candidates, score, *, gimme) ->
Trajectory` — **not a solver** (we have a complete one), but a difficulty *model* that
replays the already-known fill in human order and measures where the order forces a
hard get. Each iteration solves one entry, classified by *how* it was gettable:

- **forced** — only one word fits its current pattern (`candidates == 1`): free, pure
  logic, no clue needed;
- **gimme** — common enough (`score >= gimme`) to just know from the clue;
- **hard** — neither: the solver is stuck and must work an obscure, still-open entry,
  disambiguating among its remaining fits.

Solving an entry reveals its cells, which can force or ease its crossings next
iteration (the cascade — a cell is "known" once any entry through it is solved, and
crossing entries share the cell, so no explicit propagation map is needed). When
stuck, the model attacks the **most-supported** entry (fewest fits), ties to the one
you are likelier to know (higher score) — so *support*, not raw obscurity, drives the
cascade, and only the ice-breaking first get on an all-obscure grid is truly cold.
`Trajectory.bottleneck` is the hardest hard-get (most fits to disambiguate) — what
makes a grid a Saturday.

What it revealed (measured, `scripts/difficulty.py`, folded into notes.md):
- **all-common (cw>=90):** `GGGG…FF` — a few gimmes ignite, the rest cascade to
  forced, **0 hard-gets**. A grid of common words is a Monday *however open its
  crossings* — the dynamic mechanism behind D20's "openness ≠ hard when words are
  common".
- **mixed (cw>=68):** still **0 hard-gets** despite 8–13 *open* crossings — the payoff:
  obscure-but-forced ≠ Natick, which `analyze` alone cannot see.
- **all-obscure (cw band [50,58]):** `HHHH…HF` — no gimmes, so one cold ice-breaker
  (~20k fits, the bottleneck) then support cascades but every entry stays hard: a true
  Saturday. Lowering `gimme` to inside the band (you *know* those words) drops
  hard-gets 9→7 and the bottleneck from ~20k fits to ~140 — **anchoring/ignition
  quantified**.

Assumptions and limits, held explicitly:
- **No backtracking.** It replays a *known* solution, so it never guesses wrong; it
  models the *order of discovery*, not search. A real solver's wrong turns are out of
  scope (and not needed for a difficulty estimate).
- **One greedy order, not a distribution.** Ties are broken deterministically
  (`grid.runs()` order). A distribution over plausible solve orders is a later
  refinement; the greedy path is the honest "does an easy route exist" bound.
- **`gimme` is the soft, uncalibrated knob (D20 layer B).** It is an *input*, not a
  claim: the model *brackets* a real solver (vary `gimme` to sweep solver skill) rather
  than pretending to be one. Calibrating it still wants human solve logs.

Kept clean: `solve_order` couples to nothing in `core` — like `analyze` it takes a
`candidates(answer, known) -> int` callable (wired to `Lexicon.matching` in the
driver), so it is representation-agnostic (square or blocked) and fakeable with a
dict. The layers contract is untouched (it sits in `app`).

Alternatives considered:
- **A pure-structural cascade (no `score`/`gimme`, fill only forced entries):**
  rejected — a fully-checked grid has *no* forced entry at the start (every cell blank),
  so a logic-only solver cannot even ignite. Ignition *requires* the obscurity/clue
  signal; that a grid needs clue-gettable anchors to start is itself the finding, so
  `score` is a first-class input, not an add-on.
- **Score-first hard-get order (`(score, -fits)`):** tried, rejected — it picked
  multiple cold ice-breakers in a row (an obscure word with zero support chosen over a
  supported one), understating the cascade. Support-first (`(-fits, score)`) makes the
  cascade flow through crossings, which is the whole point of modelling order.
- **A finer effort scale than three buckets:** deferred — "how few fits is easy
  enough" is a calibration (soft) question; three buckets plus the per-step fit count
  convey the gradient without inventing a scale.

Reversal: `solve_order` is additive (a new `app` function + a driver mode; no `core`
or service change). The next step, when solve logs exist, is to calibrate `gimme`/the
bucket thresholds against real times and to widen the single greedy order into a
distribution — at which point the `candidates` seam is where BP marginals would slot
in, the same seam D20 named for `analyze`.
