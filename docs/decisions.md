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

## D20. The whole-puzzle path: a `PuzzleService` compose + a plain-text solving view

Context: a QA round exposed a seam. Every piece of "generate a complete, solvable puzzle"
existed — `BlockedGenerateService` fills a grid, `ClueService` clues one through the
`ClueProvider` port (D15/D16), `FilledGrid` (D15) is the model-agnostic aggregate the
cluing context speaks, and its `runs()`/`crossings()` derive the entry structure — but
*nothing composed them*, and no presenter emitted a **solver-facing** view. Producing a
playable puzzle meant hand-stitching three steps (generate, clue, hand-number a blank
grid). The existing presenters (`mini_batch`, `blocked_result`) render the *answer key*
(letters visible); there was no blank-grid-plus-clues surface at all.

Decision: close the seam with a thin compose and a plain-text presenter — no new
mechanism, just wiring the existing complete/soft halves together.

- **`app.puzzle_service.PuzzleService`** — pure orchestration over the two existing
  services: `fill_grid_once` -> `ClueService.clue` -> `CluedPuzzle`. It owns no I/O and
  no provider of its own. Crucially a `None` grid propagates as a `None` puzzle *before*
  any clue call, so the completeness epistemics (invariant "None is a proof") survive the
  compose — "no puzzle" still means "no acceptable fill exists at this bar", never "gave
  up". To feed it, `BlockedGenerateService` grew `fill_grid_once` (the same search as
  `fill_once`, projected into a `FilledGrid` instead of a scored `BlockedResult`); the
  shared search is factored into one private `_fill`, so the scored and geometry views
  never drift.
- **`cli.present.playable`** — the solver-facing view: a blank numbered grid + Across/Down
  clue lists (with answer lengths), pure ASCII (`+ - | #` and digits) so it renders
  identically in any terminal or text box. Answers are never shown; `present.solution` is
  the separate reveal (and `--reveal`'s implementation). Clue **numbering** is a new
  `FilledGrid.numbering()` derivation — reading-order over run-start cells, computed on
  demand, never stored (the D15 "derive views at the point of use" rule; it agrees with
  `BlockedGrid`'s own slot numbers by construction).
- **`cli.puzzle`** — the entry point, and the first tool to take **named flags, not
  positional args**. `mini`/`generate` are positional (`mini 5 70 3`) and that is already
  a legibility cost; `puzzle` has more knobs of *more distinct kinds* (a dimension, a
  black-cell count, a score bar, a difficulty, a symmetry toggle). Positional order works
  when arguments share a semantic (`add(a, b)`); here they do not, so `puzzle 5 5 4 75
  wednesday` reads as line noise. `--black` / `--min-score` / `--difficulty` say what they
  mean at the call site, and argparse yields `--help`, validation, and `--no-symmetric`
  for free. This is deliberately *not* retrofitted onto `mini`/`generate` here — their
  documented positional invocations and shims stay working; the named-flag convention
  starts with the tool that needs it and is the recommended shape for new tools.

This is the **quick, developer-facing** front end. The richer, solver-facing surface will
be a web server with its own entry point; keeping this one a thin plain-text path is
intentional, not a stopgap that wants growing into a UI.

Rationale: the compose is the smallest change that turns a manual QA ritual into `uv run
puzzle`, and it adds no new architectural surface — `PuzzleService` sits in `app` beside
the services it holds, the presenter in `cli` beside the ones it joins, and both stay
testable with the in-memory `LexiconSource` and `FakeClueProvider` (no model, no files):
the presenter's exact layout is pinned as a string contract, and the service's `None`
propagation is a test, not a hope. The import-linter layers contract is unchanged (all new
edges point downward).

QA finding, recorded alongside (see notes.md): the clean-grid **min-score floor for the cw
list is ~75, not 60**. At `--min-score 60` the fill admitted `LEDON` (a non-word scoring 60);
75 produced only real words across several seeds. 75 is now the `puzzle` default. This is a
data-quality property of `cw_5.txt`, not an engine bug — the solver faithfully placed a word
the *list* rated acceptable — so the fix is the recommended floor, not a code change.

Alternatives considered:
- **Compose in the CLI instead of a service:** rejected — it would inline generation +
  cluing into an entry point, exactly the orchestration the `app` layer exists to hold, and
  would not be testable without stdout capture. The CLI stays thin (argv -> build -> run ->
  present) like `mini`/`generate`.
- **Reuse `blocked_result` / render the answer key:** rejected — that is the *setter's*
  view (letters visible); a puzzle you can *solve* needs the blank grid, which is a genuinely
  different presenter. They share nothing but the `Writer`.
- **Add `numbering` as a stored field on a result object:** rejected — numbering is a pure
  function of the geometry (D15); storing it would be a second source of truth that can drift
  from the grid. Derive at the point of use.
- **Positional args for consistency with `mini`/`generate`:** rejected — consistency with a
  known legibility cost is not a virtue; the named-flag form is where new tools should head.

Reversal: the plain-text path is additive and self-contained. If the web front end
subsumes it, `cli.puzzle` + `present.playable` can be dropped without touching
`PuzzleService` (which the web entry point would reuse) or any lower layer. Raising the cw
list's own quality would retire the 75-floor note independently.

## D21. Difficulty is a layered decomposition; build only the complete, deterministic slices

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

## D22. Solve order: the dynamic difficulty reading (grow A′ from snapshot to cascade)

Context: D21's `analyze` is the **maximal-support snapshot** — it asks "at full
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
  crossings* — the dynamic mechanism behind D21's "openness ≠ hard when words are
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
- **`gimme` is the soft, uncalibrated knob (D21 layer B).** It is an *input*, not a
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
in, the same seam D21 named for `analyze`.

## D23. Generate to a difficulty: select on solve order in the service — and say it is not a proof

Context: D21/D22 built difficulty as *analysis* — you generate a grid, then measure how
hard it is. The natural product move is to invert it: ask the generator for a *target*
difficulty and have it hand back grids that hit it ("give me a Saturday"). The
machinery is all present (`solve_order` scores a grid; `MiniService` already loops
seeds); D23 is the wiring, plus the one thing that must stay explicit — this selection
is **not** the complete/provable kind of answer the rest of the system trades in.

Decision: `MiniService.generate` grows two optional knobs, `min_hard_gets` (default 0,
== today's behaviour) and `gimme` (default 80). When `min_hard_gets > 0` the service
loads the **full** vocabulary (for the difficulty read, D22), generates over the band as
before, and for each solved grid runs `solve_order` (wired to the new
`Lexicon.n_candidates` primitive and the full-list score); it keeps a grid only if it
needs at least `min_hard_gets` hard gets, dedupes by fill, and returns the survivors
**hardest-first** with a `SolveDifficulty` attached (`hard_gets`, `bottleneck_word`,
`bottleneck_fits`, `gimme`). `cli.mini` exposes it as `--hard K [--gimme G]`.

The load-bearing distinction, stated in the docstring and the presenter's empty-result
message: **a short return is budget exhaustion, not UNSAT.** A backtracker `None` is a
theorem — the tree is exhausted, no grid exists (invariant: "None is a proof"). Difficulty
selection is best-of-a-seed-budget over a *soft, uncalibrated* score (`gimme` is D21 layer
B); returning fewer than `count` means "not found in the seeds tried", never "impossible".
Conflating the two would be the exact epistemic error the whole design is careful to avoid,
so the code never calls a difficulty miss a proof, and the message says "not found in the
seed budget" and suggests loosening (`higher gimme`, obscurer band), not "impossible".

Why *threshold-first*, not *global-hardest*: the service stops at the first `count` grids
clearing the bar (then sorts those), rather than scanning the whole budget for the
absolute hardest. The target is "at least this hard" — a Saturday, not *the* hardest
possible grid — and first-past-the-bar is faster and matches the ask. The budget is
`count * 40` when targeting (vs `* 20`), since target-meeting grids are rarer; still a
budget, still honest about it.

Kept clean: `n_candidates` is the mirror of `n_letters_at` (a `core` primitive; the
solve-order analogue of the checkability one), so the service wires `solve_order` with
core primitives exactly as the driver does — no new coupling, the layers contract holds.
Backward compatible: `min_hard_gets=0` skips all of it (no full-vocab load, no
`solve_order`, `difficulty=None`), so `mini 5 70 3` is byte-identical.

Alternatives considered:
- **Scan the full budget, return the N hardest (best-of):** rejected as the default —
  always burns the whole budget and answers a different question ("the hardest you can
  find") than the target ("hard enough"). The hardest-first sort of the threshold
  survivors gives most of the benefit at a fraction of the cost.
- **A `Difficulty`/Mon–Sat preset enum mapping to `(gimme, min_hard_gets)`:** deferred —
  tempting, but the mapping *is* the calibration that D21/D22 say needs solve data. Baking
  presets now would dress an uncalibrated guess as a named label. Two honest knobs until
  there are real times to fit the presets to.
- **Compute difficulty for every grid always (drop the `min_hard_gets>0` gate):** rejected
  — `solve_order` over the full 20k-word vocabulary is real work; making the default
  `mini` pay it for a field it did not ask for is a silent tax. Opt-in via the target.

Reversal: additive and default-off. When solve logs arrive, the `Difficulty` preset enum
becomes buildable (calibrate `gimme`/`min_hard_gets` per weekday), and best-of-budget
could join as an explicit mode; neither changes the seam.

## D24. Large minis: cap the entry length, don't grow the word lists — a cap-driven layout search

Context: every grid so far is <= 5x5, and the word data is lengths 2..5. The next
product step is a bigger mini — a 10x10. The naive reading ("a 10x10 needs 6..15-length
word lists") is both a data problem we don't have and, more importantly, *not what a good
big mini is*. A 10x10 packed with ten-letter words would be a themeless monster of obscure
long entries — exactly the hard-to-fill, hard-to-solve fills the whole system avoids. The
real desideratum, stated by the user, is the opposite: **tactically placed black cells so
the maximum entry length is controlled** — a big grid built out of short, familiar words.
That reframing is also the data-feasibility win: cap every entry at `max_len <= 5` and the
grid fills from the lists we *already have*, no length-6+ data needed.

The count-driven layout generator (D13, `gen_patterns`) cannot express this. It chooses
black *orbits* and validates a whole layout at the leaf with a `min_len`-only fully-checked
test; there is no maximum-length notion, and — because it enumerates orbit subsets in an
arbitrary order — a run-length bound cannot prune until a layout is already complete.
Measured: `gen_patterns(10x10, 20 black)` takes ~2.7 s to yield its first layout, and that
layout has a **10-letter run**; a post-hoc `max_len` filter finds nothing in any reasonable
budget (the sparse-black layouts it reaches first are all giant-run).

Decision: add a **cap-driven sibling**, `patterns.gen_capped` (+ the `fill_capped`
composite), rather than warp `gen_patterns`. The governing parameter is the *maximum* run
length; the black-cell count is *derived* from it (pass `num_black` to also pin the count).
Legality is otherwise identical to D13 — 180°-symmetric (toggleable), fully checked, white
cells 4-connected — plus the new upper bound: every entry length in `[min_len, max_len]`.

- **Row-major search with incremental run pruning.** The search runs cell-by-cell in
  reading order and prunes each partial row/column the moment a run is too long or too
  short (`_cell_ok`): a white that would push its across/down run past `max_len`, or a
  black that would close a run of length `1..min_len-1`, can never become legal, so the
  branch dies immediately. This is what the orbit/leaf model structurally cannot do, and it
  is why a capped 10x10 is found in ~8 ms instead of never. Symmetry is handled by forcing
  each cell from its already-decided 180° partner; connectivity and the final bottom-edge
  column runs are checked at the leaf.
- **A strict generalization, cross-tested for completeness.** With `max_len=None` and a
  fixed `num_black`, `gen_capped` enumerates the *exact same set* `gen_patterns` does
  (asserted in `tests/test_patterns.py`), and where the cap bites it equals brute force
  over all black-cell subsets. So the completeness discipline is intact: an empty generator
  is a proof no legal capped layout exists (e.g. an odd `num_black` on a symmetric 10x10 has
  no centre cell to carry it — a theorem, the direct echo of D13's odd-count proof).
- **Invariant 0 preserved; fill unchanged.** `gen_capped` yields plain `BlockedGrid`s that
  `fill.solve` fills with no change (MRV backtracking, grid-wide distinctness). Only the
  layout *search* is new. Threaded up as `BlockedGenerateService.fill_capped_once` and a
  `generate --max-len K` flag; the service loads the multi-lexicon over `range(min_len,
  max_len+1)` only, so nothing beyond length 5 is ever asked for.

Findings (this container, `scripts/largemini.py`; numbers in notes.md): a `max_len=5` 10x10
fills **10/10 seeds** from the cw 2..5 lists at bars 50–75 (~180 ms, 38 entries); a 12x12
likewise (44 entries, ~250 ms). The cap is precisely what makes a big mini *data-feasible*.
The completeness epistemics survive for *existence* (the odd-count proof above), but a fill
miss under a pattern/`node_budget` bound is **budget exhaustion, not a UNSAT theorem** — the
capped layout space at 10x10 is astronomically large (unlike the 5x5 orbit space D13 can
exhaust), so `fill_capped`'s `None` under a bound is worded as exhaustion, the same honesty
D23 draws for difficulty selection.

Alternatives considered:
- **Warp `gen_patterns` to be run-aware (one generator):** rejected for the spike. Its
  orbit-subset/leaf-validated model cannot prune a run bound, so making it cap-capable means
  replacing its search order wholesale — and it carries a passing brute-force ground-truth
  contract (D13) worth not disturbing. This is the exact D12->D13 precedent: a genuinely new
  regime gets a new, coexisting search rather than a warp of the proven one. Unifying the two
  once the row-major search is shown to subsume the count-first path is recorded as a
  follow-up (open-questions), not done here.
- **Generate 6..15-length word lists and *not* cap:** rejected. It is the data problem we
  don't have *and* the wrong product — long entries are the obscure, hard-to-fill ones; the
  user explicitly does not want a grid full of ten-letter words. Capping is both the ask and
  the feasibility win, so it is strictly better than sourcing longer lists here.
- **A stochastic layout sampler for the larger space:** rejected for the same reason as
  D7/D13 — small/hard/constrained search wants completeness, and the row-major pruning makes
  the complete search fast enough at 10x10.
- **Keep the fixed black *count* as the primary knob (D13's interface):** rejected as the
  primary. At 10x10 the count needed to hold `max_len` is a *consequence* of the cap, not a
  natural input; making the cap primary and the count an optional target matches how the
  object is actually specified ("no entry longer than five").

Reversal / follow-ups (open-questions): (i) **unify** `gen_capped` and `gen_patterns` if the
row-major run-aware search is shown to fully subsume the count-first path; (ii) **density
control** — the free-count search over-blackens under uniform randomization (22–52% at 10x10;
a `num_black` target of ~18 gives clean ~18% grids), so a black-density objective is the next
knob; (iii) **scaling past ~12x12** — connectivity is checked only at the leaf, so the search
backtracks heavily at 13x13+ (a 15x15 does not finish), which is the pre-existing "pruning
before 15x15" open-question made concrete (incremental connectivity/symmetry pruning is the
fix). None of these change the model; `gen_capped` and `fill_capped` are additive and the
layers contract is untouched.

## D25. Density control for capped layouts: a white-biased search + a black-cell ceiling

Context: D24 shipped the cap-driven generator, but its free-count search chose black/white
uniformly (50/50) and returned the first legal layout it stumbled into. On a 10x10 that
over-blackened badly -- **22-52% black cells, clustered** (a touching-neighbour fraction of
~0.95): blobby, dense, nothing like a real crossword. For a first expansion the *density*
and *spread* of the black cells is the single biggest quality lever (a 10x10 wants ~16-22%
black, spread as short breaking-walls), so this is the follow-up D24 flagged, taken now.

Measured the design space (`scripts/`, folded into notes.md), 10x10 max_len=5, 20 seeds:
uniform-50/50 gave 22-50% (cluster 0.95); a plain white-first order dropped the *median* but
left a fat tail (some seeds still 48%); a hard black ceiling *at* the feasibility minimum
(20 blacks, min+4) held 16-20% but made the search **backtrack pathologically** (a 312 ms
spike at 10x10; a 12x12 at a tight cap did not finish at all); a ceiling with a little slack
(22 blacks) held **16-22% black, 20 distinct / 40, cluster ~0.85, ~5 ms** to find. So the
lever is a *ceiling with slack*, plus an order that prefers few blacks.

Decision: two **completeness-safe** additions to `gen_capped`, plus a good default and a
runaway guard.

- **White-biased choice order.** When ``randomize``, each free cell is tried white-first,
  black-first only ``_BLACK_FIRST_PCT`` (15%) of the time, so the search prefers *fewer,
  less-clustered* black cells. This only reorders which layout appears first per seed -- the
  reachable set (and completeness) is untouched, exactly as D24's uniform shuffle was. A
  white-first order alone is not enough (the 48% tail), which is why the ceiling below is the
  guarantee and the bias is the *preference*.
- **A `max_black` ceiling.** An upper bound on the count, pruned early. ``{layouts with <=
  max_black blacks}`` is a well-defined set, so the search stays complete over it: an empty
  generator is still a proof (a ceiling *below the minimum feasible count* -- e.g. < 16 on a
  10x10 -- is provably empty, the same epistemics as an infeasible exact count). ``num_black``
  (exact) still exists; ``max_black`` is the softer density knob.
- **Default density.** When the caller pins neither count, `fill_capped_once` sets ``max_black
  = round(DEFAULT_BLACK_FRACTION * cells)`` with ``DEFAULT_BLACK_FRACTION = 0.22`` -- the
  measured slack point. The result: `generate 10 10 0 60 3 --max-len 5` now yields clean,
  real-crossword-like grids by default instead of the D24 over-black mess. `--max-black K`
  overrides for a specific density.
- **A layout `node_budget` (runaway guard).** A ceiling near the feasibility minimum makes
  the search backtrack hard, and on a bigger grid (12x12) that runs away. So `gen_capped`
  gains a ``node_budget`` mirroring `fill.solve`'s: the *generation* path (`fill_capped_once`)
  passes one so a pathological seed bails and the per-seed loop moves on; the *proof* path
  (`capped_layout_exists`) runs unbudgeted, so "no layout exists" stays a theorem. A budgeted
  empty result is exhaustion, not UNSAT -- stated in the docstring and covered by a test.

Result (notes.md): 10x10 default density fell from **22-52% to 16-22%** black, 20 distinct /
40 seeds, fills 10/10 at bars 50-75 -- real grids (`GLASS/UNITY/BYLAW/IGLOO`,
`ICON/BROWN/CHASE/TESLA/LOCKE`). The four forces -- density, diversity, search cost, grid
size -- trade against each other: tightening the cap toward the minimum buys density at the
cost of search time. 10x10 sits comfortably in the slack; a 12x12 at the same *fraction* is
near its own minimum, so its yield is low (the node budget bails most seeds) -- the frontier,
consistent with D24's scaling follow-up (a smarter layout search with incremental
connectivity/symmetry pruning is what buys tight density at 12x12+).

Alternatives considered:
- **Exact-count default (pin `num_black` at ~18%):** rejected as the default. It gives precise
  density but markedly less diversity (measured 6/20 distinct at a fixed count vs 13-20/20 for
  the ceiling) and needs per-(size, cap) tuning to stay feasible; the ceiling is one knob that
  degrades gracefully. Exact count remains available for callers who want it.
- **White-bias alone, no ceiling:** rejected -- the 48% tail means no density *guarantee*; the
  ceiling is what makes "at most this black" true.
- **Ceiling at the true minimum (tightest density):** rejected -- pathological backtracking
  (the 312 ms spike / 12x12 hang). Slack is cheaper than the marginal density.
- **An anti-cluster / spread objective now:** deferred. Count control is the dominant lever and
  already lands the density in range; the residual clustering (~0.85, short black walls) is a
  normal crossword texture, and a spread metric is a further-refinement knob, not this spike.

Reversal: additive and tunable. ``DEFAULT_BLACK_FRACTION`` and ``_BLACK_FIRST_PCT`` are
one-line constants; drop ``max_black``/``node_budget`` and the bias to return to D24's search
exactly. When the D24-scaling layout search lands, the ceiling's slack requirement relaxes and
tighter default density at 12x12+ becomes cheap.

## D26. Put a real solver in the loop: an agent-solving spike as an empirical difficulty probe

Context: the difficulty work so far (D21/D22/D23) is *analytical* — `solve_order` replays
a **known** fill easiest-first and classifies each get (forced / gimme / hard), with
`gimme` an uncalibrated solver-skill knob. Its own docstring is careful: "it is not a
solver (we have a complete one); it is a difficulty model." And open-questions has said all
along that the one thing blocking real calibration (layers B and C, and growing A′ into a
trajectory *distribution*) is **a human solve-time signal** — playtesting or logged solves —
which this environment does not have. The spike this entry records: stand up an actual
*soft* solver (an LLM agent) in a **feedback loop** against a generated puzzle, and use its
run — did it finish, and *how did it reason* — as a cheap proxy for that missing signal.
Two independent product reads: (i) whether the agent completes the grid is a coarse
difficulty bit; (ii) inspecting the agent's turn-by-turn thinking is the rich read — and it
is the empirical counterpart to `solve_order`'s modelled bottleneck, so a solver that stalls
where the model predicts a Natick is the model *earning its keep*.

Decision: build it on the **same complete/soft seam** as everything else, and land the
deterministic half fully (as D15 landed cluing interface-first with a fake), the live LLM
half behind a port (as D16 put the model in the adapter). Four pieces:

- **`app/solve.py` — the deterministic session (the "environment").** `Board` holds the
  static truth *including the answer key*; `SolveState` = board + the solver's per-*entry*
  guesses; a cell's letter is **derived** from the entries through it (D15's "derive views"
  rule), which makes a **crossing conflict** — two crossing guesses disagreeing on a shared
  cell — a signal the solver sees with *no* answer key. `is_solved` is **cell-based, not
  per-entry**: a crossword is solved when the grid is right, and filling the acrosses
  correctly already fills their crossing downs (the interlock), so there is nothing extra to
  "submit". The load-bearing integrity invariant: `SolveView` (what the agent acts on) is an
  **answer-free projection** — it carries geometry, clues, the solver's own current letters,
  and the policy's feedback, and *never* an unguessed answer. A solver that could read the
  key measures nothing.
- **Feedback is a policy knob, and that knob is the solver-skill dial** (the empirical twin
  of `gimme`): `CELL` (per-cell right/wrong for the solver's own filled cells — the NYT
  "check" button; the default, gentle, autocheck-on), `WORD` (whole-entry), `CROSSING` (only
  the conflict cells — uses **no** key, pure internal consistency, the most authentic
  no-cheating signal), `NONE` (only the terminal solved bit — the purest probe, weakest
  loop). Default `CELL` was the user's call for this spike; it is the most generous, so it
  compresses the difficulty signal — the stricter policies are the sharper probes, and that
  is documented at the knob.
- **`app/solver.py` — the `SolverAgent` port.** `act(view) -> SolverMove`, deliberately
  **one-shot and stateless**: the view already carries the full observable state, so the
  agent is a function of observable state and the harness re-sends the whole view each turn
  rather than the agent hoarding private history. `SolverMove` carries the agent's
  **reasoning** as a first-class field — capturing *how it thought* is the whole point.
- **`app/solve_service.py` — the harness.** Pure orchestration (the shape of `ClueService`
  /`PuzzleService`): build view → `act` → validate+apply (malformed placements rejected, not
  stored) → check → record turn → repeat until solved, given-up, or out of turns.
  `SolveReport` is the difficulty artifact (completed? turns? flail? the reasoning
  transcript). **The one epistemic rule (D23's lesson on the solving side): a budget miss is
  not a proof.** The fill engines' `None` is a UNSAT theorem; running out of turns is only
  "not solved in N turns". The report says `solved`/`exhausted`/`gave_up` honestly and the
  presenter never dresses exhaustion as "impossible".
- **`adapters/claude_solver.py` — the live agent, behind the port.** This is the **second
  LLM consumer D16 anticipated** ("a second consumer would justify a minimal, our-own seam…
  and only then"). We hold D16's line: the LLM does *not* become an app-layer port; the app
  depends on `SolverAgent` (which speaks views and moves), and the SDK, the credential
  (same `Config.clue_api_key_env` wiring), and the reasoning capture all live in the adapter,
  one level down beside `ClaudeClueProvider`. `cli/solve.py` composes the live path end to end
  (generate a clued puzzle, then solve it, then `present.solve_report`); two live steps, the
  grid *fill* stays LLM-free.

**The measurement is reasoning *volume*, so the call is shaped to expose it (the load-bearing
refinement, verified live).** For a model that solves every mini, *whether* it finishes is a
saturated signal — the graded difficulty tell is **how much it had to think**. Two live facts
forced the shape (notes.md "Agent solve loop"): (i) Opus 4.8 uses **adaptive** thinking
(`thinking={"type":"adaptive"}` + `output_config.effort`; the old `{"type":"enabled",
"budget_tokens":…}` 400s on it); (ii) forcing a JSON **schema** *suppresses the thinking pass
and zeros `thinking_tokens`* — exactly the signal we want. So the solver deliberately runs
**free-form**: the model reasons in prose (readable) and ends with a JSON object we parse
leniently, and `SolverMove.reasoning_tokens` carries the thinking-token count from `usage`
(the thinking *block* is returned redacted/empty, so the prose is the readable trace and the
count is the scalar). `SolveReport.total_reasoning_tokens` sums it; the presenter surfaces it.
This is why the solver adapter is free-form while the clue adapter stays structured — cluing
does not need a thinking measurement, solving *is* one. `--model`/`--effort` (and
`Config.solve_model`) let a weaker/cheaper solver be pitted against the same grid, since a
harder-for-this-solver puzzle should cost more reasoning; `Config.solve_thinking` selects the
thinking mode per model family (Opus `adaptive`, Haiku `enabled`), since each 400s on the
other's.

**Live check + first findings.** The whole path runs against the real API in-container.
Confirmed: at mini scale Opus 4.8 **one-shots the grid even under `--policy none` (no
feedback)** — the *completion* bit is saturated, so **reasoning-token spend is the
discriminating signal**, and it is difficulty-responsive (a trivial prompt spends 0 thinking
tokens; a mini spends thousands). `scripts/solve_effort.py` is the experiment driver that
sweeps a difficulty lever (clue Monday..Saturday, model, policy) holding the grid fixed and
reports thinking-token spend; measured numbers live in notes.md. The graded signal sharpens
further with larger grids (the 6..15 word lists, still unbuilt) or a weaker solver model.

Scope held tight for a spike. Tests drive the whole loop with a deterministic
`FakeSolverAgent` (oracle + scripted modes) — no model, no network — so the session,
feedback policies, answer-key quarantine, budget honesty, and rejection paths are all pinned
without egress, exactly as `FakeClueProvider` pins cluing. What is deliberately *not* built:
a **judge** that reads the transcript and scores difficulty (another soft stage — human
inspection for now); calibrating the feedback policies / turn budget against real human
times (the same "needs solve logs" blocker); on-demand checking (the current `CELL` policy
is autocheck-always-on) and per-turn feedback *cost*; and a shared `LanguageModel` seam
between the two Claude adapters (two direct SDK callers is not yet enough duplication to
force it — D16's "and only then" bar is *approached* here, not cleared; recorded so the next
adapter tips it).

Alternatives considered:
- **A `LanguageModelProvider` app port shared by clue + solve now:** rejected — same reason
  as D16. It leaks infrastructure (messages, tokens) into the domain. Two adapters calling
  the SDK directly is the honest amount of structure; the seam gets introduced when a
  *third* consumer or an adapter-level test need forces it.
- **Feedback baked in (one "check" behaviour):** rejected — the feedback model *is* the
  solver-skill assumption (the empirical `gimme`), so it must be an explicit, sweepable knob,
  not a constant. Baking it would hide the very parameter the probe exists to vary.
- **A per-cell `SolveGrid` reusing `FilledGrid` with a new empty sentinel:** rejected — the
  per-entry guess model is what makes crossing conflicts a key-free signal and matches how a
  human actually pencils entries; cells are derived from it, not the store of record.
- **Letting the agent see the answer key / the fill result:** rejected outright — it would
  make the measurement meaningless. The `SolveView` anti-corruption projection is the
  integrity boundary, the solving-side mirror of `FilledGrid` for cluing.
- **Treating a turn-budget miss as "unsolvable":** rejected — it would commit the exact
  epistemic error the whole system is built to avoid (D23). Only the *complete* fill engines
  prove UNSAT; a soft solver proves nothing by running out of turns.

Reversal: additive and self-contained. The session/harness/port sit in `app` beside the
clue services; the adapter and `cli.solve` sit beside their clue analogues; the layers
contract is unchanged (all new edges point downward). If the empirical signal proves useful,
the natural follow-ons are a transcript-judge (a third soft stage → the `LanguageModel` seam
finally earns itself), calibrating the policies/budget against the agent runs, and feeding
the result back to validate/tune `solve_order` (D22) — closing the analytical/empirical loop
the difficulty work has been reaching for.

## D27. The black-cell layout is a soft field: a Gibbs sampler, measured and kept (scoped)

Context: for several decisions the docs *cheerled* one idea without building it. D25's density
knobs -- a white bias, a black-fraction target, an anti-cluster penalty -- were each a **local
kernel applied uniformly across the grid**, and open-questions.md ("Layout generation is a soft,
local field") read that tell out loud: the black-cell **layout** is a *translation-invariant grid
with local run-length legality and a soft statistical objective* (density, spread, no 2x2 block),
i.e. an Ising/Potts **field with local factors**, not something to hand-tune inside a systematic
search. It even *stiffens near a critical density* -- the D25 runaway backtracking as ``max_black``
neared the feasibility minimum (the reason a ``node_budget`` was needed; why a 12x12 yields ~2/15
and a 15x15 hangs) is textbook SAT/UNSAT phase-transition hardness, exactly where a complete solver
chokes. This is the **"big-and-soft" regime D19 reserved** for a sampler's return. The spike: stop
cheerleading and *build the Gibbs sampler*, then -- in this repo's measure-then-record style (D19,
D24, D25) -- benchmark it head-to-head against ``gen_capped`` and keep or retire it on the numbers.
The stated target was **aesthetics** (density/spread/texture at the sizes that already fill), not
the giant-size frontier.

Decision: add ``core/engines/gibbs_layout.py`` -- an **annealed-Gibbs sampler over the binary
black/white field** -- as a *coexisting* layout generator beside the complete ``gen_patterns``/
``gen_capped`` (the invariant-0 "two models coexist" move, one level up at the layout layer). It
samples ``exp(-E/T)`` where the energy is a sum of **local factors**:

- **run-length legality** (dominant weight) -- a white run of length 1..min_len-1 or > max_len is
  penalised, so the anneal settles into a legal basin;
- **density** -- a ``(n_black - target)^2`` spring toward a target count;
- **anti-cluster** -- a penalty per 4-adjacent black-black pair (spread);
- **no 2x2 black block** -- an explicit term forbidding the American-grid defect.

Two structural choices honour the boundary open-questions.md drew:

- **Symmetry is global but free** -- the sampler colours only the 180°-rotation *orbit
  representatives* (both cells at once), so **every draw is symmetric by construction**, no factor,
  no penalty.
- **Connectivity is global and topological** -- a local factor genuinely cannot express "all white
  cells are one region", so it is **not** in the energy; it is a global **reject** at the end
  (``patterns._connected`` BFS). A single-cell Gibbs step evaluates only the *affected rows/columns*
  plus the *cluster terms touching the flipped orbit* (everything else cancels in the conditional),
  so the sampler is cheap per step.

The **`Rng` port grew one method**, ``random()`` (a uniform float for the Metropolis/Gibbs accept
draw) -- the port extension D19's reversal note explicitly anticipated ("the `Rng` port is the seam
to swap the randomness adapter without touching the engines"). ``numpy.random.Generator`` already
satisfies it, so no adapter changed. ``fill_gibbs`` composes the sampler with ``fill.solve`` exactly
as ``fill_capped`` does; ``BlockedGenerateService.fill_capped_gibbs_once`` and ``generate --gibbs``
expose it. Tests pin the contracts: a Gibbs draw is a member of ``gen_capped``'s complete legal set
(the ``backtrack ⊆ bruteforce`` ground-truth pattern, at the layout layer), never has a 2x2 block
(though the legal set does), is symmetric, is reproducible from the seed, and -- load-bearing -- a
**miss is budget exhaustion, never a proof** (``capped_layout_exists`` stays the sole existence
theorem; the epistemics survive the new engine unchanged).

**The verdict (measured, `scripts/gibbs.py`, this container; numbers in notes.md): KEEP, scoped to
the aesthetics regime.** On its target axis at 10x10 it wins where it was meant to and honestly loses
where a sampler must:

- **spread -- win:** clustering **0.67 vs gen_capped's 0.85** (blacks visibly better spread);
- **no 2x2 block -- categorical win:** **0.00 vs 0.27 per grid (max 2)** -- ``gen_capped`` emits the
  American-grid defect ~1 grid in 4; the field forbids it by construction;
- **density -- roughly a wash:** 20-26% vs 16-22% (a touch denser/wider -- the count spring vs the
  ceiling);
- **diversity -- loss:** 9/30 distinct vs 15/30 (the anneal converges to fewer minima);
- **speed -- loss:** ~197 ms/layout vs ~5 ms (~40x; still sub-second, fine for a generation tool);
- **fill -- unchanged:** both 6/6 from cw 2..5 at bars 60/70, 38 entries.

The measurement also surfaced an **unbid bonus at the 12x12 frontier**: ``gen_capped`` (default cap,
node-budgeted) **misses 13/15 seeds** and returns 1 distinct layout -- the D25 phase-transition
collapse -- while the Gibbs field **misses 1/15, returns 8/14 distinct**, at comparable time. The
sampler keeps producing where the complete search's budget chokes near the threshold, which is
precisely the phase-transition prediction the docs made. So the field is *also* the more productive
engine at the size D25 flagged as the frontier -- not just prettier.

So it earns a place, but a **scoped** one: ``gen_capped`` stays the **fast default** and the **sole
completeness/existence-proof** engine; the Gibbs field is the **aesthetic-controlled (and
frontier-productive) alternative** behind ``--gibbs``. The clean seam the architecture already draws
-- *a soft field for the blacks, a complete CSP for the words* -- is now real (open-questions.md's
"the shape of the spike"), and it is the same complete-vs-soft split as D21 (difficulty) and D15
(the clue port), surfacing this time in the geometry. D3's original post-classical instinct was not
wrong; D19 was right that it did not belong to the *fill* -- it belongs to the *layout*.

Alternatives considered:
- **Retire it (a D19-style "measured and removed"):** rejected -- unlike the fill sampler, this one
  *wins on its target axis* (no-2x2 is a guarantee ``gen_capped`` structurally cannot make; spread is
  better) and is strictly more productive at 12x12. A losing spike gets a tombstone; a winning-but-
  narrow one gets a scoped keep.
- **Make it the default layout engine (retire ``gen_capped``):** rejected -- it is ~40x slower at
  10x10, less diverse there, and (the decisive reason) **not complete**: it cannot prove
  ``capped_layout_exists``, the existence theorem the whole design's epistemics rest on. Coexistence,
  not replacement.
- **Metropolis-Hastings / simulated annealing instead of Gibbs:** rejected as the first cut -- the
  binary-field Gibbs conditional is exact and cheap (local delta), and the annealing schedule already
  gives the temperature control MH would tune. A different move kernel is a refinement, not a
  redesign.
- **Connectivity as a soft energy term or a repair pass:** rejected for the spike -- it is genuinely
  non-local (open-questions.md's "the real obstacle"), so a local factor cannot express it and a
  repair risks reintroducing an illegal run; a global BFS **reject** is the honest, simple gate. A
  union-find repair (or an ASP formulation with native reachability) is the recorded follow-up.
- **Expose the field weights as user knobs now:** deferred -- ``FieldParams`` exists and the
  benchmark set sensible defaults; a calibrated "sparse vs dense vs spread" preset surface is a
  product follow-up, not this spike.

Reversal: additive and coexisting. ``gibbs_layout.py``, the ``--gibbs`` path, and the ``Rng.random``
method are self-contained; delete them and ``gen_capped`` is untouched. The natural follow-ups
(open-questions.md): union-find/ASP connectivity to lift the 12x12 reject rate further; a spread/
density preset surface; and -- the larger prize the frontier result now motivates -- whether the
field's productivity past 12x12 makes it, not a smarter backtracker, the right answer to the
"scaling past 15x15" question (D24 (iii)).

## D28. How the sampler fares as basin shape and count change -- a study, and a repair that fails

Context: D27 landed the Gibbs layout field and named follow-ups -- chiefly a **connectivity
repair** (whiten a "bridge" black to reconnect a split white region, instead of only rejecting)
and a **sweep** to see how the sampler behaves as we reshape the basin (grid size, energy weights)
and change the count (black density). This is that study, taken in the repo's measure-then-record
style. The instrument is a new ``reject_reason`` classifier over the *raw* anneal
(``anneal_field`` split out of ``sample_layout``): ``ok`` / ``short_run`` / ``over_cap`` /
``disconnected`` -- so we can see not just *whether* an anneal fails but *how*, and watch the
failure mode move.

Decision: build the connectivity repair (a bridge-whitening ``_repair_connectivity``), the
``reject_reason``/``anneal_field`` instruments, and a sweep driver (``scripts/gibbs.py`` D28
section); measure; **record the findings, and delete the repair because the measurement
retired it** (D19-style: the lesson here, the code one ``git show`` away). The findings
(numbers in notes.md; this container):

- **The count knob has a hard FLOOR, and it is the jamming boundary seen from the soft side.**
  A tight cap forces a *minimum* black density (a 10-wide row capped at 5 needs >= 2 blacks). Ask
  the field for fewer blacks than that floor and it cannot answer with a *sparser legal* grid --
  it answers with an *illegal* one: ``over_cap`` white runs it could not break. So ``ok`` rate is
  a tent peaked **at** the floor: 10x10 ``ok`` climbs 12%->16%->**28%**->16% across frac
  0.14/0.18/0.22/0.26, ``over_cap`` collapsing (12->2) as the target rises to the ~22% floor, then
  ``disconnected`` taking over above it (over-crowding). This is exactly D25's phase transition --
  the same wall the *complete* search hits as ``node_budget`` (D25) -- now visible as the
  *sampler's* reject profile. The complete search backtracks into the wall; the field leaves
  soft-constraint residue against it. Same frontier, two epistemics.
- **The failure mode SHIFTS with basin shape.** At a fixed frac=0.20, as the grid grows the target
  falls further below the (rising) floor, so the reject profile moves from balanced to pure
  legality: 10x10 ``{ok 6, short_run 4, over_cap 7, disconn 8}`` -> 12x12 ``{ok 4, 7, 14, 0}`` ->
  14x14 ``{ok 0, 6, 18, 1}``. Connectivity (the D27 concern) *vanishes* as a failure mode at size;
  fine-grained run-length legality is what defeats the field as the basin tightens. The honest
  reading: **the soft field owns the soft objective (density, spread, no-2x2) but the hard
  run-length legality is where the complete search still wins** -- the very soft/hard split the
  architecture draws (D15/D21), now re-derived inside the layout layer.
- **The connectivity repair is DEFEATED by the cap -- a clean negative result.** Bridge-whitening
  fixed **0 of 25 disconnected anneals at every density and size measured**. The mechanism is
  exact: under a tight cap the blacks separating two white components *are* the cap-load-bearing
  cells (each caps a maximal run at ``max_len``), so whitening a bridge re-creates an over-cap run
  -- and such a run cannot be single-black-split back into two >= min_len runs (a 6-run splits only
  into 5+0..3+2, one side always < 3). So connectivity, the one *globally*-repairable-looking
  constraint, is *not* locally repairable **once a length cap couples it to run-length**. Rejection
  (the D27 baseline) is therefore correct for capped minis, and the repair was **removed** -- it
  earned no product surface. (This is the D19 move in miniature: a follow-up built, measured, found
  wanting, deleted with its verdict recorded, rather than left as a 0-effect flag to rot and
  mislead. The ``reject_reason``/``anneal_field`` *instruments* stay -- those are used.)
- **The reliable lever is the soft weights (the basin reshape works).** Sweeping ``w_cluster``
  0.0->0.55->1.2 moves clustering **0.90->0.73->0.71** *and* tightens the density spread
  (22-32% -> 20-24%), 2x2 staying 0 throughout. Where the *hard* constraints jam, the *soft*
  objective is exactly as controllable as a field promises -- which is the whole reason to have a
  field here at all.

Rationale: the study answers the question D27 opened ("how does it fare across the basin?") with a
coherent picture -- the sampler is a good soft-objective shaper up to a hard-legality wall that
*is* the jamming density, and that wall, not connectivity, is its frontier. The repair follow-up
was worth building precisely to learn it cannot work under a cap; recording that stops the next
agent re-attempting it. Nothing about D27's verdict changes: the field stays the aesthetic path,
``gen_capped`` the fast/complete default.

Alternatives considered:
- **Keep the repair (on, or off-behind-a-flag as an instrument):** rejected -- it fixes ~0 under
  the cap, so on-by-default is cost with no benefit and a misleading "we handle connectivity" claim,
  and off-behind-a-flag is exactly the "tombstone in place" D19 warns against (a 0-effect knob on
  three public signatures, a foot-gun to rot). Deleted; the mechanism and its verdict live in this
  entry + git. The pure ``reject_reason``/``anneal_field`` instruments the sweep *does* use stay.
- **A general legality *polish* (min-conflicts descent to fix short-runs/over-cap too):** tried in
  a spike, rejected -- blackening a short-run white cascades new short runs in the crossing
  direction; exact legalization of a near-legal field near the jam is itself the hard CSP the
  *complete* search already does well. Chasing it would re-import a backtracker into the sampler.
  Recorded as the reason the honest boundary is "soft field + complete legalizer", not "field
  alone".
- **Raise ``w_legal`` / colder tail to force legality at 12x12:** measured to barely move the
  ``over_cap``/``short_run`` counts -- the residue is a jamming property, not an annealing-schedule
  artifact. Left at the D27 schedule.
- **A count *below* the floor as a "sparse" mode:** rejected -- it is infeasible, not sparse; the
  field correctly cannot produce it. The floor is physics (D25), and asking under it is the same
  category error as a ``max_black`` below ``gen_capped``'s feasibility minimum (a provable empty).

Reversal / still open (open-questions.md): connectivity that is *not* cap-coupled would want an
**ASP/union-find formulation with reachability native** (the survey's declarative route) rather
than local whitening; the **legality wall past 12x12** is where a smarter field (WFC min-entropy
propagation, or a move set that respects run-length by construction) or simply the template-library
route earns its keep. The instruments (``reject_reason``, ``anneal_field``, the sweep) are additive
and the layers contract is untouched.

## D29. Drift and dead-code cleanup after the concurrent-spike merges

Context: several spikes merged to `main` in close succession -- D24/D25 (large capped
minis), D26 (agent solver), D27/D28 (Gibbs layout field) -- alongside a mid-stream
decision *renumbering* (the solver spike D24->D26; the difficulty spike's D20/D21/D22
became D21/D22/D23 once D20 "the whole-puzzle path" was inserted). The automated gate
stayed green the whole time, which is exactly the problem: ruff/mypy/import-linter/pytest
catch layering, types, and broken invariants, but not *semantic* drift -- so prose,
code comments, and a little dead surface fell out of sync with the code. This entry
records the cleanup; it changes no design.

Decision: chase the three classes the spikes left behind and fix them, architecture untouched.

- **Dead code removed.** `Lexicon.is_word` (an unused predicate) and the `CapturingWriter`
  adapter (referenced only in docstrings; the one test that needs a recording sink rolls its
  own inline `Writer`). Both are one `git show` away, per the D19 discipline. Deliberately
  *kept* despite looking caller-light: the static-difficulty subsystem (`analyze`,
  `CrossingOpenness`/`StructuralDifficulty`, `Lexicon.n_letters_at`) is D21 layer A' and the
  Gibbs `reject_reason`/`anneal_field` are the D28 study instruments -- both are load-bearing
  benchmark surface the docs describe as built, exercised by `scripts/difficulty.py`/`gibbs.py`
  and the tests, so removing them would contradict D21/D28, not clean up after them.
- **A batch-distinctness gap closed.** `MiniService.generate` deduped emitted grids only on
  the difficulty-*targeting* path (`min_hard_gets > 0`); the plain path could emit the same
  fill twice, because a *complete* backtracker returns the same solution under different seeds
  when the band admits few (`mini 5 90 3` at a tight bar). Distinctness *within* a grid
  (invariant 3) was never at risk -- `backtrack`/`validate` still enforce 2N distinct words;
  this is invariant 3 applied *grid-wide across the batch*, which the tool's "distinct minis"
  wording promises. The `seen`-set dedup is hoisted to guard every emitted grid (a regression
  test in `test_services.py` pins it: a lexicon with two distinct squares now yields at most
  two grids for `count=5`, never a repeat). Single-grid reproducibility is unchanged
  (`mini 5 70 1` is byte-identical; only the first grid of a batch is a documented contract).
- **Docs re-synced to the code.** The decision-log range in CLAUDE.md (D1-D13 -> D1-D28); the
  stale "`scripts/generate.py` is the demo / property check" claim in architecture.md (it is a
  shim to the `generate` tool; the property check moved to `tests/test_patterns.py`, as the same
  file already said elsewhere); five section-header paths that predated the `core/`+`core/engines/`
  reorg; the D20/D21 -> D21/D22 difficulty references the renumbering left in `app/difficulty.py`,
  `app/ports.py`, and `scripts/difficulty.py`; the drivers missing from the enumerations
  (`solve_effort.py`, `largemini.py`, `difficulty.py`, `gibbs.py`); and README's status/layout/run,
  which still listed clue generation as "not started" despite the shipped clue (D15/D16/D20),
  difficulty (D21-D23), and agent-solve (D26) work. The stale `from_scored_file` present-tense
  claim in notes.md's initial-spike snapshot was framed as historical (the read moved to
  `FileLexicon` at D14).

Rationale: the repo's memory *is* its docs (this log, architecture.md, notes.md), and the
"documentation is part of the change" rule (CONTRIBUTING) had slipped under merge pressure.
Recording the cleanup rather than silently applying it keeps the *why* legible and tells the
next agent that `is_word`/`CapturingWriter` were removed on purpose (not lost). No engine,
invariant, or layer changed; the full gate stays green.

Reversal: n/a -- maintenance. If a second `Writer` sink is ever wanted, `CapturingWriter` is in
git; if the static-difficulty benchmark is retired, its cluster becomes removable at that point.

## D30. Unify the CLI on argparse: `mini`/`generate` keep positionals, drop the hand-rolled parse

Context: D20 gave `puzzle` argparse (and `solve` followed), but `mini` and `generate` kept
hand-rolled argv parsing -- `mini` a `_take(args, flag)` helper that spliced `--flag VALUE`
pairs out of the list before reading positionals, `generate` a manual `iter(args)` loop
splitting flags from positionals by hand. D20 said the argparse retrofit was "deliberately
*not* retrofitted onto `mini`/`generate` here". That was a scoping call at the time (start the
named-flag convention with the tool that needs it), not a claim the hand-rolled parse was
better -- and it left two of the four tools with a bespoke, untyped, help-less, no-validation
parse that silently accepted junk (`mini 5 xyz` read `xyz` where a float was wanted).

Decision: reverse the "not retrofitted" scoping call and parse **all four** entry points with
argparse. `mini` and `generate` now build an `ArgumentParser` in a `_parse_args(argv)` helper
(the same shape `puzzle`/`solve` already use), with the historical arguments declared as
**optional positionals** (`nargs="?"` + `default`). The result:

- **The documented invocations are byte-for-byte unchanged.** `mini 5 70 3`, `generate 5 5 4
  60 3`, `--max`/`--hard`/`--gimme`, `--nonsymmetric`/`--asym`, `--max-len`/`--max-black`/
  `--gibbs` all parse exactly as before; the shims and `[project.scripts]` console commands
  are untouched. This is *not* the positional->named migration D20 reserved for tools that
  need it -- `mini`/`generate` stay positional (D20 stands); only the *parser* changed.
- **`--help`, type coercion, and validation come for free.** `mini abc` now exits with a clear
  `invalid int value: 'abc'` instead of a bare `ValueError` traceback (or, worse, silent
  misread); every tool answers `--help` with its arguments and defaults.
- **The hand-rolled `_take` helper and the manual flag/positional split are gone** -- one
  parsing idiom across the four tools, less surface to get wrong when a knob is added.

Rationale: this is the smallest change that makes the four front-doors consistent and gives
two of them the validation and help the other two already had, at zero cost to the documented
positional interface. No service, engine, invariant, or layer edge changed (the parse still
lives only in `cli`, the top of the import stack); the full gate -- ruff, mypy, import-linter,
pytest -- stays green. architecture.md's entry-point descriptions were already accurate about
the positional shape, so they needed no edit; this log is the record of *why* the parse moved.

Reversal: n/a -- consolidation. The hand-rolled parsers are in git if a tool ever needs a
parse argparse cannot express (none does today).

## D31. The kernel-methods review spike: measured, tombstoned -- see the post-mortem

Context: a final review-of-methods spike over the pure kernel (the arc D1-D30 is well
recorded, which made the genuinely-unexplored *complete/deterministic* gaps easy to see).
Two were tried, in the house regime (filter, prove, measure): **solution counting** (how
*large* is the SAT space at a bar -- the open-questions "how many distinct minis exist at
score>=X" item) and an **early distinctness prune** (the "detect a partial column that can
only complete to an already-used word ... measure before optimising" perf item). Both were
built, measured, and -- following this repo's tombstone discipline (D19 sampler, D28
connectivity-repair, D29 dead code) -- **removed from the shipped kernel with the findings
recorded**, because neither earns a durable place in it: the counter's value was a *one-time
measurement* (now recorded), and the prune *failed outright*.

Decision: tombstone the spike. The kernel returns to its pre-spike state (`backtrack.py` has
`solve` only; no `count`/`SolutionCount`, no `scripts/count.py`, no `tests/test_count.py`),
and the review + the measured findings live as the canonical reference in
**`docs/postmortem-kernel-methods.md`**. The code is one `git show` away (commit on the
spike branch); the numbers are the memory, exactly as D19 kept the sampler's numbers after
deleting the sampler.

What was learned (full write-up in the post-mortem; headline numbers also in notes.md):

- **The solution space collapses to a countable set at the ceiling.** The weak (Zipf) list
  goes **56 -> 8 -> 0** exact distinct 5x5 minis across T=3.5/3.7/3.9, which also *refines*
  the earlier ceiling read (the true edge is **between 3.7 and 3.9**, not "tops out ~3.5 /
  UNSAT at 4.0"). The curated **top tier (score>=90) admits exactly 38 distinct 5x5 minis** --
  the *denominator* behind "25 seeds found 18 distinct", and the number batch-variety
  reasoning was missing (at the top the distinct pool is genuinely tiny, which is *why*
  top-tier fills repeat). This finding survives the tombstone; the code that produced it need
  not.
- **The early distinctness prune does not pay.** A sound forced-down prune (a column prefix
  admitting one word determines its down word; reject a duplicate before the `r==n` leaf) cut
  only **~2% of search nodes and was time-neutral** -- the condition rarely fires before the
  existing leaf check catches the duplicate anyway. "Measure before optimising" answered No.

Alternatives considered:
- **Keep `count` as a shipped capability (partial success, not failure):** rejected on the
  owner's call to tombstone the spike -- consistent with D19's line that an idea can *earn its
  place in the arc* (here: it answered the open question) *without earning an operational place
  in the shipped system*. The measurement is the deliverable; the recorded number outlives the
  code, and a future counting need restores `count` from git rather than carrying it idle.
- **Keep the prune as an off-by-default flag:** rejected -- a ~2%, time-neutral knob on public
  signatures is the "tombstone in place" D19/D28 warn against.
- **A single decision entry, no separate doc:** rejected -- the spike is both a *review* of the
  whole methods arc and two experiments; a dedicated post-mortem is the "easy reference"
  canonical form, with this entry the index into it.

Reversal: n/a for the design (nothing in the kernel changed). To resurrect the counter or the
prune, `git show` the spike commit; the post-mortem records what they found so the resurrection
starts from the verdict, not from scratch.

## D32. Generation input becomes a typed spec algebra; the four fill methods collapse to one

Context: the next front is a REST API (basic puzzle aggregate: create + get). Before wiring
it, the internal shape it will consume needed formalising. The blocked generator carried the
smell a serialized API would expose immediately: four near-duplicate methods
(`BlockedGenerateService.fill_once` / `fill_capped_once` / `fill_capped_gibbs_once` /
`fill_grid_once`), each a flat bag of overlapping-but-different keyword arguments (rows, cols,
min_score, max_score, seed, symmetric, min_len shared; num_black / max_len / max_black /
max_patterns / max_layouts varying), plus `MiniService.generate` and `PuzzleService.generate`
re-declaring the bag again. Two structural problems: (a) **strategy selection lived in the
caller as method-name dispatch** — `cli/generate.py` chose which of the four to call with
`if args.max_len is not None: ... if gibbs: ...`, and the knobs illegal for a given engine
(`max_black` on Gibbs, `max_layouts` on the count search) were merely absent-or-ignored
kwargs; (b) **the load-bearing epistemic distinction** — is a `None` a UNSAT *proof*
(complete search) or budget exhaustion (a sampler)? — was encoded only in the method name
and a docstring (`cli/puzzle.py::_explain_no_puzzle` reconstructed it by hand).

Decision: model generation input as a typed algebra (`app/spec.py`) and collapse the four
methods into one strategy-dispatched search (`app/generate.py`, `GenerateService`). This is
D15's own rule — *"introduce a modelled structure only where an external contract forces
it"* — applied to generation input. argparse never forced it (named flags are free; D20/D30
kept the tools positional on purpose), so the services got away with the flat bag. A
serialized API body *does* force it: the request must be one validatable, versionable
object. So we model it now, and the internal call sites get the clarity for free.

- **The algebra.** `GridSpec` (the shape + quality band + seed every strategy shares); a
  **closed, tagged `LayoutStrategy` union** — `FullSquare` / `CountLayout` / `CappedLayout`
  / `GibbsLayout`, each a frozen record carrying *only its own* knobs; `FillSpec` (the
  fill-selection knobs `min_hard_gets`/`gimme`, D23 — distinctness is not a knob, always on);
  and `PuzzleSpec` bundling all four plus a `ClueStyle`. The illegal knob combinations the
  flat kwargs allowed are now **unrepresentable** (a `GibbsLayout` has no `max_black`), and
  the proof-vs-budget epistemic tag is `layout_is_complete(layout)` — a property of the
  *type*, so a caller (the API's future "no puzzle" response) words it honestly from the tag.

- **One dispatched search.** `GenerateService._search(grid, layout)` is a single `match` over
  the union; `fill_grid` projects it into the model-agnostic `FilledGrid` (D15) for *every*
  strategy — square or blocked, one call — and `fill` shapes the scored `BlockedResult` for
  the blocked ones. `layout_exists` likewise dispatches (subsuming the old `layout_exists` +
  `capped_layout_exists`). Exhaustiveness is enforced by `assert_never`, so adding a fifth
  engine (the surveyed WFC / template-library routes) is a compile-time obligation at every
  call site, not an `if`-ladder to remember.

- **The square folds in as `FullSquare`.** A single fully-checked square now flows through
  `GenerateService.fill_grid(grid, FullSquare())` like any blocked grid — so a square can
  become a clued puzzle through `PuzzleService` too, uniformly. `MiniService` stays as the
  square's *batch + scoring* specialist (it keeps the `DoubleSquare`/state the model-agnostic
  `FilledGrid` cannot carry, to score every word and read `solve_order` difficulty), now
  spoken in the same `GridSpec`/`FillSpec` vocabulary.

- **`assert_never` on the 3.10 floor.** CLAUDE.md recommends `match` + `typing.assert_never`,
  but `typing.assert_never` is 3.11+ and the floor is a hard 3.10 ("Modern Python — with one
  hard boundary"). Resolved by a hand-rolled `spec.assert_never` with a `NoReturn` parameter —
  the pre-3.11 idiom that gives mypy the *identical* exhaustiveness check without the 3.11
  import. (A small internal contradiction in CLAUDE.md, resolved in favour of the hard floor.)

Rationale: the API is the forcing function, but the collapse is a strict improvement
independent of it — one search instead of four, the impossible combinations typed out, the
epistemics surfaced. Scope held: no engine, invariant (0–5), or user-visible artifact changed
(all four CLIs and their documented invocations still work byte-for-byte; the benchmark
drivers were mechanically ported); the full gate — ruff, mypy (the exhaustiveness check
lands), import-linter (all new edges point down, `app/spec.py` sits in `app`), pytest —
stays green. `BlockedGenerateService` was renamed `GenerateService` (module `app/blocked.py`
→ `app/generate.py`, container field `blocked` → `generator`) because it now generates the
square too; the old name was a misnomer.

Alternatives considered:
- **A single flat `GenerationConfig` dataclass** (every knob, optional): rejected — it keeps
  the illegal combinations representable (a `num_black` *and* a `max_len` *and* a
  `max_layouts` on one object) and pushes "which knobs apply" back into runtime validation.
  The tagged union makes the engine's legal knobs a type, which is the whole point.
- **Keep the four methods, add the specs as a thin wrapper**: rejected — it leaves the
  method-name dispatch and the duplicated search in place; the specs would decorate a mess
  rather than replace it.
- **Fold `MiniService` entirely into `GenerateService`**: rejected for now — the square's
  batch + per-word scoring + difficulty targeting genuinely differ from single-grid
  generation, and forcing them together would blur invariant 0 (two coexisting models). The
  square folds in at the *spec/geometry* level (`FullSquare`, `fill_grid`), which is enough.
- **Pydantic models as the app spec**: rejected — D16 deliberately declined a `pydantic`
  runtime dependency. The app specs stay plain frozen dataclasses; when the REST layer lands,
  its wire schema (Pydantic, behind a `web` extra) *parses into* these, never *is* them — the
  D15 rule that the port speaks the canonical form and serialization is a separate concern.

Reversal: the collapse is consolidation (the old methods are in git). The spec algebra is
additive and is the seam the REST API and a `PuzzleRepository` port build on (open-questions
"Generation specs — BUILT (D32)"); if a fifth layout engine or a genuinely different fill
regime arrives, it is a new union variant + a new `match` arm, caught by `assert_never`.

## D33. Raise the Python floor to 3.13; retire the `assert_never` shim

Context: the floor had been a hard `>=3.10` since D14 — a deliberate boundary policed by
CLAUDE.md ("Modern Python — with one hard boundary") and re-affirmed at D32, whose one visible
cost was a hand-rolled `spec.assert_never` (a `NoReturn`-parameter function) written *because*
`typing.assert_never` is 3.11+ and could not be used under a 3.10 floor. That floor no longer
buys anything: 3.10 entered security-only maintenance and is effectively out of service, and
nothing consumes this package below 3.10 that we owe support to. Keeping it only taxed the
codebase with a workaround for a version we do not run (the dev toolchain is 3.11/3.13, never
3.10).

Decision: raise the floor to **`>=3.13`** and modernise the one construct the old floor forced.

- **The bump.** `requires-python = ">=3.13"`, ruff `target-version = "py313"`, mypy
  `python_version = "3.13"`. 3.13 is in full upstream support (to ~2029), so the floor is a
  live, supported version rather than a dead one — and it is the newest interpreter this
  environment can actually run and verify (see "what 3.14 cost us" below).
- **Retire the shim.** The D32 `spec.assert_never` (`(NoReturn) -> NoReturn`) is deleted;
  every dispatch (`spec.layout_is_complete`, `GenerateService._search`/`layout_exists`) now
  imports `typing.assert_never` directly. The static exhaustiveness check is *identical* —
  adding a `LayoutStrategy` variant without a `match` arm is still a mypy error — but it is now
  the stdlib name CLAUDE.md always recommended, not a local reimplementation of it.
- **The 3.11–3.13 toolbox is now in bounds.** `StrEnum`, `tomllib`, PEP-695 `type X = …`
  aliases and `class Foo[T]` generics, `@typing.override` — all now usable where they earn it
  (not swept in here; this change is the floor + the one directly-forced workaround, kept
  reviewable). CLAUDE.md's boundary section is rewritten from "modern *within 3.10*" to "the
  floor is 3.13".

**Why 3.13 and not 3.14 (the target that was asked for).** The intent was 3.14 as the floor;
the *environment* blocked it, not the code. This container cannot provision a 3.14 interpreter:
uv's python-build-standalone index here only knows `3.14.0rc2` (not 3.14.0 final), and even the
RC 403s — the agent proxy allowlists pypi/files.pythonhosted (so package **wheels** resolve
fine) but not github.com release assets (where the **interpreter** tarballs live). So a
`>=3.14` floor would make `uv sync`/`uv run` refuse to build an env here at all, shipping an
*unverifiable* floor — the whole gate (ruff/mypy/pytest) would stop running in this container.
3.13 is on disk (`/usr/bin/python3.13`), the full gate runs green on it, and the jump 3.13→3.14
is a one-line follow-up (`requires-python`, ruff, mypy) once the environment can fetch and test
3.14. So the destination is unchanged; this is a way-station chosen for verifiability, recorded
so the 3.14 bump is a known, trivial next step, not a re-decision.

- **One downstream fix the bump forced.** Re-locking on 3.13 resolved numpy `1.26`→`2.5.1`,
  whose type stubs split `Generator.random` into dtype/out-keyed overloads; the `Rng.random`
  port's broad `size: int | None -> Any` signature no longer matched a single overload, so mypy
  rejected the structural fit. Fixed by *narrowing the port to how it is actually used* —
  `random(self) -> float`, a single accept draw (the only call, `gibbs_layout`, is always
  no-arg) — which matches numpy's no-`size` overload cleanly. A port tightened to its real usage,
  not a stub worked around. The reproducibility invariant survives the numpy major bump: the
  `default_rng(0)` seed-0 mini is byte-identical before and after (`SEDAN/CREDO/ROTOR/ADEPT/PERTH`).

Rationale: a floor should be a supported version we actually run, and a workaround should not
outlive the constraint that forced it. This does both, at the cost of ~a dozen lines, with the
gate green on 3.13 (the exhaustiveness check still lands). Scope held: no engine, invariant, or
user-visible behaviour changed; `from __future__ import annotations` stays on every module
(harmless, and still correct even as 3.14's PEP 649/749 would make it a no-op) rather than
churning ~40 files for a cosmetic removal.

Alternatives considered:
- **Floor `>=3.14` (the stated target):** deferred, not rejected — see "Why 3.13" above. The
  environment cannot verify it; a `>=3.14` floor here is untestable and breaks local tooling.
  The bump is queued as a one-liner for when 3.14 is installable/CI-backed.
- **Floor `>=3.11` (minimum to get `typing.assert_never`):** rejected — 3.11 clears the shim
  but is a smaller step off a dead version; 3.13 is supported far longer and the dev box already
  has it, so there is no cost to taking the larger, still-verifiable step.
- **Keep `>=3.10` and the shim:** rejected — it is the status quo whose only justification (a
  version we must support) no longer holds.
- **Sweep StrEnum / PEP-695 / @override in the same change:** rejected for scope — this change
  is the floor + the one workaround the floor forced; broader modernisation is now *unblocked*
  and can land incrementally where it pays, without bundling it into the floor bump.

Reversal: lowering the floor again would re-import the shim (D32's form is in git). Raising it
to 3.14 is the intended next step and needs only the three config lines + retesting on a 3.14
interpreter — no code change (the shim is already gone).


## D34. Direction: ship a playable product; close the human-solve loop

Context: with the generation arc essentially closed (square → blocked → capped → Gibbs,
D13/D24–D28) and the difficulty arc built to the edge of its data blocker (D21/D22/D26),
the project reached a genuine fork: (a) an engineering "revamp", (b) more of the
dynamic-programming / field exploration (WFC, ASP, 15×15, a template library), or (c)
something with *a product at the end that we can feedback-loop*. The user asked, explicitly,
for help choosing — and named the preference: a product, not another inward spike.

Decision: **build a playable product, and use it to close the one feedback loop the project
has never closed** — a real human solving a real puzzle, whose solve-time becomes the ground
truth the difficulty work is blocked on. The staged plan lives in `docs/roadmap.md` (the
first forward-looking doc in `docs/`); this entry records the call and its reasoning.

The load-bearing argument (why this is not merely "a product"): both cybernetic streams the
project built — generation and the LLM-agent difficulty probe — are **internal** feedback
loops. The **external** loop (a person plays) is missing, and the difficulty stream is
*explicitly blocked on exactly its output*: `open-questions.md` repeats "the one thing that
would unblock B and C … is a human solve-time signal", and D26's agent-solver was always a
**proxy** for it ("an LLM brackets *a* solver, not *the* distribution"). So shipping a
playable puzzle is the **instrument that produces the missing measurement**; one loop unifies
both streams (generate → clue → serve → human plays → solve-time → calibrate difficulty →
target better → generate). The architecture already aimed here: D32's typed spec algebra was
built as the forcing function for a REST body, `open-questions.md` names "*A REST API — the
next front*" plus a `PuzzleRepository` port, and `site/` already ships a black-cell-aware
player (static today).

Sequencing honours D15 ("model structure only where an external contract forces it"): the
`PuzzleRepository` port and the wire schema arrive **with** the web layer that forces them,
never speculatively ahead — which is *why* this branch records the direction rather than
pre-building an inert repository port. Three phases (roadmap.md): (1) the API seam — `web/`
FastAPI behind a `web` extra, a Pydantic wire schema parsing into `PuzzleSpec`, a
`PuzzleRepository` port + in-memory adapter, `POST`/`GET /puzzles`; (2) the playable loop —
fold `site/`'s player against the live API, add a solve-telemetry endpoint (the human
signal); (3) close the cybernetics — calibrate D21/D22 against human times, validate the D26
proxy against reality, feed the batch scheduler.

Rationale: it is the only option that ends in a product *and* advances the research (the human
signal is the difficulty work's blocker, not a detour from it); it exercises the last unbuilt
architectural seam (a second adapter) and cashes in D32's spec algebra; and it composes with —
does not foreclose — the generation stream, which resumes when the loop earns the attention.

Alternatives considered:
- **More generation/field methods** (WFC vs Gibbs bake-off, ASP for native connectivity,
  a curated template library, scaling past 12×12): deferred, not rejected — it is the natural
  continuation of stream 1 and stays open in `open-questions.md`, but it is inward-facing and
  produces no product or human signal. The D27 field/complete split means it composes later
  rather than conflicting now.
- **Deepen the difficulty cybernetics without shipping** (a transcript→difficulty judge,
  calibrating the LLM-solver against the deterministic vocabulary-floored solver): rejected as
  the *primary* direction — it sharpens the proxy but stays a proxy, still blocked on the human
  data that only shipping produces. It becomes Phase 3, *after* the loop exists.
- **An engineering revamp**: rejected as lowest-value — the codebase is already hexagonal,
  DI'd, strict-typed, and import-linted (D14/D18/D32/D33) with little real debt; a revamp would
  polish a clean floor while the product loop stayed unbuilt.

Reversal: this is a *scope/priority* call, not an engine or invariant (0–5) change, so it
reverses by deprioritisation, not by removing code — the API and persistence seams are
additive and live at the `cli`/adapter edge. If the human-signal loop proves too sparse or
noisy to calibrate against (Phase 3's premise), the project falls back to the LLM-proxy
difficulty work or the generation stream, while the served/playable/persisted puzzle (Phases
1–2) stands as the product regardless.

## D35. Phase 1: the HTTP API layer + a persistence port

Context: D34 chose to ship a playable product and `docs/roadmap.md` sequenced it. Phase 1
is the API seam -- the forcing contract the rest of the loop needs, and the move D32's
typed spec algebra was explicitly built to enable ("a serialized API body *does* force
it"). It is pure architecture: no new engine, no research, no invariant touched.

Decision: add a `web` layer beside `cli` and a `PuzzleRepository` port with an in-memory
adapter.

- **`app/repository.py` -- the persistence port.** A `PuzzleRepository` Protocol
  (`save(spec, puzzle) -> PuzzleId`, `get(id) -> StoredPuzzle | None`) plus `StoredPuzzle`
  (the `CluedPuzzle`, its originating `PuzzleSpec` for provenance, and the assigned id).
  Declared in `app` (the application states the capability); implemented in `adapters`.
  This is the "Second adapters" seam open-questions reserved, finally exercised. The port
  is **total** -- `get` returns `None`, never raises -- so the caller words "no such
  puzzle" (the 404 is the API's call), the same shape as `ClueProvider` returning empties.
  Determinism nuance (D34): the *fill* is reproducible from `(lists, spec, seed)` but the
  *clues* are soft (LLM), so the clued aggregate is stored as **data**, not regenerated.
- **`adapters/memory_repository.py` -- the first implementation.** A dict + a monotonic
  counter (ids `"1"`, `"2"`, ...). Wired in `bootstrap` as a plain stage-2 adapter (it
  takes no config, reaches nothing outside); `Container` gains a `repository` field. A DB
  adapter is a drop-in second implementation of the same port -- that the swap is drop-in,
  with nothing above this layer changing, is the whole point of the port.
- **`web/` -- the HTTP entry point.** FastAPI behind a `web` optional extra, isolated
  exactly like `anthropic` behind `clue` (the package and the whole gate run without it;
  only `puzzledesk.web.*` imports FastAPI/Pydantic). `web/schema.py` is a **Pydantic wire
  schema** -- a discriminated union of layout bodies mirroring `LayoutStrategy` -- that
  *parses into* `PuzzleSpec` via `to_spec()`, and a `PuzzleView` that *renders* a stored
  puzzle as player JSON via `puzzle_view()`. It is a **separate** object, never `PuzzleSpec`
  itself (D15: the port speaks the canonical form; serialization is an export concern).
  `web/app.py::create_app(container)` is a factory (so a test hands it a fake-clued
  container) exposing `POST /puzzles` (parse -> generate -> store -> view, 201) and
  `GET /puzzles/{id}` (read back, 404 if absent); `web/main.py` is the uvicorn instance.
- **The completeness epistemics cross the HTTP boundary intact.** A `None` from generation
  is worded from the spec's layout tag (`layout_is_complete`, D32): a complete strategy's
  empty result is a **422 `unsat`** ("a UNSAT proof, not a timeout"), a budgeted/sampled
  one's is **422 `budget`** -- never collapsed into a bland not-found. "None is a proof"
  survives the API, restated on the wire.

Enforcement/scope: `web` joins the import-linter `layers` contract at the top (a top entry
point like `cli`); the whole five-command gate stays green (ruff, ruff format, mypy --
FastAPI/Pydantic added to the optional-extra `ignore_missing_imports` override beside
`anthropic`, since the base gate runs without the extra --, import-linter, pytest). Two
test files: `tests/test_repository.py` (the port round-trip, sequential ids, total-`None`,
the runtime-checkable fit) runs in the base gate; `tests/test_web.py` (POST/GET round-trip
against the *real* engine with fake clues, the 404, the 422-`unsat` proof, the wire-schema
parse) is guarded by `importorskip("fastapi")` so the base gate skips it and
`--extra web` runs it. A byproduct fix: `site/` (committed presentation artifacts its own
README declares "outside the lint/type scope") is now actually `extend-exclude`d from ruff,
which had been silently red there -- a prerequisite for a green `ruff check`.

Rationale: this is the smallest vertical slice that makes generation *servable and
persistent*, and it is the seam Phase 2 (the playable loop + solve telemetry) and the DB
adapter build on. It cashes in D32 and exercises the last unbuilt architectural seam,
without touching an engine or an invariant.

Alternatives considered:
- **Build the repository port speculatively before the web layer** (on the planning
  branch): rejected -- D15 says structure arrives only when a contract forces it, and the
  web body is the forcing function, so the port ships *with* it, not ahead.
- **Make the app spec double as the wire schema** (Pydantic on `PuzzleSpec` itself):
  rejected, per D16/D32 -- the app specs stay plain frozen dataclasses; the wire schema is a
  separate object that parses into them.
- **A DB adapter now:** deferred -- in-memory first proves the port and the loop; the DB is
  a drop-in second adapter once Phase 2 needs durability across restarts.
- **`create_app` takes just the two services it uses** (not the whole `Container`):
  rejected -- entry points take the assembled container (the `cli` idiom); a test swaps
  fakes in with `dataclasses.replace` on the frozen container.

Reversal: additive and edge-local (a new top layer + one adapter + one port), so it reverses
by deletion without disturbing `core`/`app`/`cli`. The `web` extra keeps FastAPI out of
everyone who does not serve HTTP.

## D36. Word lists to length 15: close the 2..5 data gap, make regeneration reproducible

Context: every list shipped covered lengths 2..5 only, and the docs repeatedly flagged
"word lists longer than 5" as an open, un-built item (architecture.md, open-questions.md).
This was never an engine limit -- `Lexicon` is length-agnostic and `MultiLexicon` buckets
over whatever `range(min_len, max_len+1)` a service asks for; a missing length just becomes
an empty (unfillable) bucket. So the 5-letter ceiling was purely a *data* gap.

**What longer words are for -- and what they are *not*.** Keep two axes separate: the
**maximum word length** we stock (a vocabulary property) is not the same as **which
double-word grids we can support** (a constraint-density property). Longer lists buy us the
*less-dense* end of the blocked/capped design space: a larger `max_len` permits longer runs,
which lets a big grid hold entries legal with **fewer** black cells -- sparser, more open
textures than the short-word cap forced. That is the whole payoff. It is *not* a lever on
double-word-*square* order: a fully-checked N x N square forces every row and column to be a
word at once, and that frontier is governed by how rare simultaneous solutions get (order 7+
is rare in English), not by vocabulary reach. A 6x6 square happening to fill is incidental --
squares stay density-bound whatever the list length. The user's ask, read correctly: support
longer words as an ordinary configuration knob so the *less-dense large-grid* explorations
are possible -- "just a different max length" -- not to push the square order up.

Decision: generate and ship `cw`/`scored`/`words` for **lengths 2..15**, and make the whole
data pipeline **reproducible in-repo** (it previously was not -- only `scored_N` had a
generator, and it hardcoded `(2,3,4,5)`; `words_N`/`cw_N` were sliced externally). No engine
or invariant change -- this is data + drivers.

- **Three parameterized slice/score drivers**, each a thin `scripts/*.py` (ANN-exempt,
  I/O lives here, not the kernel -- D18): `gen_words.py` (dwyl `words_alpha.txt` -> plain
  per-length lists), `gen_cw.py` (Crossword-Nexus `xwordlist.dict`, `WORD;score` ->
  curated per-length lists, floor `score>=25`, dedupe keeping the highest score), and
  `gen_scored.py` (now `--min-len/--max-len`, scores `words_N` with wordfreq, floor
  `zipf>=2.0`). Each takes `--min-len/--max-len` and defaults to the canonical upstream URL
  (or a local `--source`), so any length range regenerates with one command.
- **The curated list reproduces byte-exact.** `gen_cw.py` re-derives the committed
  `cw_5.txt` (20,292 words) identically, which pins the filter/sort/dedupe rules as the
  ground truth for the new lengths. The `words`/`scored` families come from a *moving*
  upstream (dwyl master), so an already-committed length re-slices to the same *set* but
  can reorder; the committed 2..5 files were left untouched and only 6..15 were added.
- **Nothing beyond the data changed.** Same `FileLexicon` read (`<name>_<n>.txt`), same
  bar-filter, same distinctness/completeness invariants. `max_len` on `CappedLayout`/
  `GibbsLayout` and the grid order on `FullSquare` are now the only things gating length --
  a search-cost concern, not a data one.

Findings (this container). The intended payoff -- a *less-dense* large grid -- lands: a 12x12
capped at `max_len=7`, bar 60, fills with real 7-letter entries (SEVENPM, IBETCHA, TVEXECS,
TRUSTEE, LENDOUT, ...) in ~3.9 s, an aesthetic the `max_len<=5` cap could not reach (it forced
denser black). As a *data-reach* sanity check only, a 6x6 fully-checked double square also
fills at bar 40 -- but that is not the point of the change (see the two-axes note above):
order-7 double squares stay hard/rare (a 7x7 `mini` did not finish in 180 s), a density/
search-scaling limit (architecture.md "order 8+ gets rare fast"), *not* something longer lists
were ever going to fix. Data footprint: ~7.7 MB added (cw 6..15), 9.7 MB raw / ~3-4 MB packed.

Alternatives considered:
- **Cap the length forever and never ship longer lists (the D24 stance, taken further):**
  rejected as the *general* answer. D24's point stands -- capping is the right lever for a
  *short-word* big grid -- but "we can only ever build short-word grids" is a data accident,
  not a design choice, and word squares / long-entry themed grids are exactly the interesting
  space the ceiling was hiding. Shipping the data makes `max_len` an honest knob; the cap
  remains available for those who want short words.
- **Only ship up to the working search regime (~12):** rejected. Lengths 13..15 sit unused
  until the uncapped >12x12 layout search is pruned (still open), but shipping the full
  American-crossword range makes `max_len` gated by *search performance alone*, never by
  missing data -- the cleaner contract. The cost is ~2 MB of currently-cold lists.

Reversal: additive (30 data files + 3 drivers, no `src` change), so it reverses by deleting
the 6..15 files. The generators stay useful regardless -- they make the 2..5 lists
reproducible where before they were not.
