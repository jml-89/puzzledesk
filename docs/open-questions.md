# Open questions

Unresolved design questions and next-spike considerations, with enough context to
act on. Not a prioritised backlog; each entry states what is unknown and what
would resolve it. Grouped roughly by area.

## Product: clue generation (not started)

The grid problem is solved; a mini is not a puzzle without clues. Planned as a
SEPARATE downstream stage (grid -> 10 clues, written and ranked), decoupled from
fill. Open:
- Provider/model choice. Per repo policy, default to the latest Claude models.
  This pulls in the provider question that was intentionally deferred.
- Ranking: generate multiple candidate clues per word and rank them (by an LLM
  judge? by difficulty target Monday..Saturday?).
- Cross-clue constraints: avoid leaking answers, avoid two clues of the same form,
  match a target difficulty for the whole puzzle.
- Interface: how clues attach to a generated grid (data model, export format —
  .puz / .ipuz / JSON?).

## Grid variety and curation across a batch

Within a grid we guarantee 10 distinct words. Across MANY grids in a session we do
NOT stop the same beloved crossword-ese (the `oreo`/`erie`/`srsly` class) from
recurring, nor do we bias toward fresh/interesting fills. Open:
- How to penalise overused entries without breaking backtracking completeness.
  Options: a forbidden/penalised set fed into the filter (keeps completeness, just
  changes the list); soft re-scoring + best-of-N; a seen-set across a batch.
- Seed words / themes: place one or more chosen entries, fill around them. The
  backtracker can be seeded by fixing a row (or by pre-constraining columns);
  needs an API. Themed minis (all words share a category) need theme-tagged word
  data we do not have.
- "Interesting" vs "merely acceptable" is not measured. The crossword score is
  enjoyment-ish but static; it does not know what you already used this batch.

## Does the sampler earn its keep? — RESOLVED: No (D19)

Resolved by **deletion** (D19). The sampler was ~50-80x slower than backtracking on
distinct filtered lists and its solve-rate collapsed on the small/hard ones; the
strategy study (the former `samplers.py`) showed distinctness was never its
bottleneck, so even the guided penalty barely beat the naive gate. Its stated
reasons to exist — (a) genuinely soft preferences, (b) sample-distribution
behaviour — are both *hypothetical future needs*, not current ones, so keeping the
code was a standing maintenance/attention tax (one of its benchmark drivers even
hung on its own defaults). We removed `sampler.py`, its five benchmark drivers, its
N=2 ground-truth test, and the kernel surface that existed only for it
(`allowed_and_scores_at`, `Rng.choice`); the measured verdict lives in D19 +
notes.md.

Re-opens only if a **big-and-soft** regime returns — a large list with genuine soft
preferences (themes, per-batch novelty; see "Grid variety" above). That is the one
condition under which D3/D7 said stochastic (or a JAX parallel-chain) sampling could
retake primacy, and it would be a fresh spike with a new hypothesis, restoring the
old code from git as a starting point rather than a resurrection.

The strongest candidate for that regime has since come into view: **black-cell layout
generation**, a soft, local, translation-invariant field problem — see "Layout
generation is a soft, local field" below. That is where a sampler would earn its keep,
not the fill.

**Update (D27): it did.** The layout Gibbs sampler was built and measured — and unlike the
fill sampler (retired), it *earns a scoped keep*: it guarantees aesthetic properties
(no 2x2 block) the complete search cannot, spreads blacks better, and stays productive at
the 12x12 frontier where the complete search's budget collapses. So the D3→D19 arc's final
shape is precise: **stochastic sampling lost the *fill* and won the *layout*** — the right
tool for each regime, exactly the split D19's reversal clause anticipated.

## Difficulty — partially modelled (D21)

Difficulty is decomposed into four layers (D21); the two *complete/deterministic*
ones are built, the two *soft* ones are recorded and blocked on data:

- **A. Word prior — BUILT.** Obscurity band `[lo, hi]` via `Lexicon.filtered(min,
  max)`, threaded to `cli.mini` (`mini N min count --max HI`). A banded run still proves a
  difficulty ceiling (complete search). Open follow-up: a *difficulty*-labelled sweep
  driver analogous to `ceiling.py` (where does a band go UNSAT), and whether obscurity
  band is the right proxy for "word difficulty" or whether a separate difficulty score
  (distinct from crowd-enjoyment score) is worth sourcing.
- **A′. Structural checkability — BUILT (static + dynamic).** `app/difficulty.analyze`
  flags *open* crossings (Natick risk) at maximal support, no solve data.
  `app/difficulty.solve_order` (D22) adds the **order-dependent cascade**: replay the
  fill easiest-first (forced → gimme → hard get) so an obscure entry its crossings
  *force* by the time you reach it is not a Natick — the distinction the static reading
  cannot make. Open follow-ups: (i) it is one greedy order with a deterministic
  tie-break, not a **distribution** over plausible solve paths, and `gimme` (the
  clue-gettability knob) is uncalibrated — both want human solve logs; this is exactly
  where a real belief-propagation/marginal computation would live (the `candidates`
  seam; cf. D19 reversal); (ii) openness is still structural only — fusing it with
  per-word obscurity into a single calibrated "Natick score" needs the score scale
  settled (invariant 4).
- **B. Clue difficulty — knob exists, calibration deferred.** The Mon..Sat
  `Difficulty` enum behind `ClueProvider` (D15/D16) is the soft, sampled layer.
  Proving a clue hits a target difficulty needs human solve logs this environment does
  not have — same blocker as "solvability/fun" below.
- **C. Batch difficulty distribution — deferred.** A bell curve of difficulty is a
  *batch* property (schedule mostly-medium, few extreme), needing a per-puzzle
  difficulty number to schedule against. This is the difficulty face of "Grid variety
  and curation across a batch" (below). D23 gives the per-puzzle number (`hard_gets`);
  what is missing is the scheduler that shapes a batch to a target distribution.

**Generate-to-a-difficulty — BUILT (D23), with a caveat.** `MiniService.generate(...,
min_hard_gets=K, gimme=G)` selects grids by `solve_order` and returns them
hardest-first (`mini --hard K --gimme G`). Two open edges: (i) selection is
best-of-a-seed-budget over a *soft* score — a short return is budget exhaustion, never a
proof, and there is no completeness here (unlike the fill); (ii) the target is two raw
knobs (`min_hard_gets`, `gimme`), not a calibrated Mon–Sat preset — building the preset
is the same "needs solve logs" blocker as layer B.

The one thing that would unblock B and C, and grow A′ into the trajectory model, is a
**human solve-time signal** (playtesting or logged solves) to calibrate IRT `θ`/`b`
against. Until then difficulty is what we can compute and prove, and no more.

**Empirical probe — SPIKED (D26).** `app/solve_service.SolveService` puts a *soft* solver (a
Claude agent, `adapters/claude_solver.py`) in a feedback loop against a generated puzzle
(`uv run solve`) and records whether it finished and, the richer read, its reasoning — with
**reasoning-token spend** the graded difficulty tell (completion saturates: a strong model
one-shots every mini). What it found (full write-up in notes.md, "Agent solve loop"):

- **Clue obliqueness is the fair, graded difficulty axis** (Mon→Sat ≈ 2× reasoning); the
  Mon..Sat enum now drives it in the clue prompt.
- **Word obscurity is not a slope but a cliff.** Within the known-word regime it is inert (for
  Opus *and* Haiku); it only bites at an **unknown × unknown crossing** — a Natick — which the
  vocabulary-floor probe reproduced *empirically* (the solver failed at exactly the cell
  `analyze` flags). So D21 layer A is really the fairness floor + Natick-avoidance, not a dial.
- Method caution earned twice (reading transcripts, not the table): a `max_tokens` truncation
  once faked a difficulty spike; and a score-floor is a leaky proxy for an LLM's vocabulary
  (it knows famous low-score names). A budget miss is "not solved in N turns", never a proof.

Still open: (i) a **judge** turning a transcript into a difficulty number (another soft stage;
human inspection for now); (ii) calibrating the policy/budget knobs against *human* solve
times (an LLM brackets *a* solver, not *the* distribution); (iii) the faithful bounded-human
solver is the deterministic `solve_order` run against a **vocabulary-floored** lexicon (an LLM
cannot truly forget words), which would give the bounded-difficulty curve directly.

## Puzzle quality beyond word-score

The acceptance test scores fillability + per-word crowd score. It does NOT capture:
- solvability / fun (needs clues, then playtesting signal),
- letter-pattern aesthetics, avoidance of awkward crossings,
- proper-noun density limits (curated list has many; a real mini rations them),
- whether the SET of 10 words is thematically coherent or at least not weird.
Open: what additional cheap signals are worth adding to the acceptance test vs
left to a human/LLM editor pass.

## Model generality

Black-cell FILL is now done (D12, blocked.py/fill.py/blackcells.py): slot +
crossing graph, MultiLexicon, complete MRV backtracking, distinct entries, tiny
grid vs brute-force ground truth. What that spike deliberately left open:
- **Block-pattern generation — DONE (D13, patterns.py).** Black cells are now a
  *count*, not a template: `gen_patterns` enumerates legal layouts (180° symmetry,
  full white connectivity, fully checked at min_len) and `fill_by_count` fills the
  first that solves, complete both ways.
- **Large minis via an entry-length cap — DONE (D24, `gen_capped`/`fill_capped`).**
  A grid bigger than 5x5 is generated by capping the *maximum* entry length (not by
  a fixed count): `gen_capped` places black cells so every entry is length `<=
  max_len`, which also keeps a 10x10 fillable from the length-2..5 data. Row-major
  search with incremental run pruning; complete (an odd count on a symmetric 10x10
  is a provable no-layout). Measured: 10x10 and 12x12 fill 10/10 from cw 2..5 (see
  notes.md). Open follow-ups from D24:
  - **Unify with `gen_patterns`.** `gen_capped(max_len=None, num_black=K)` enumerates
    the same set as `gen_patterns(K)` (cross-tested), so the row-major run-aware search
    likely *subsumes* the count-driven orbit search. Merging them (one generator, cap
    and/or count) is a cleanup once that equivalence is trusted in anger.
  - **Black-cell density control — DONE (D25).** A `max_black` ceiling (complete over
    "<= K blacks") plus a white-biased search order, defaulting to ~22% of the cells,
    replaced D24's over-black uniform search: a 10x10 now defaults to **16–22% black**,
    spread as short breaking-walls, filling 10/10 (was 22–52%, blobby). A layout
    `node_budget` keeps a tight cap from running away. Left open: an explicit
    *spread/anti-cluster* objective (residual clustering ~0.85 is acceptable but not
    tuned), and tight density at 12x12+ (near its feasibility minimum → low yield, wants
    the scaling search below). **Both are addressed by the D27 Gibbs field** (an explicit
    anti-cluster energy term → cluster 0.67, and it stays productive at 12x12 where this
    complete search collapses), which coexists with `gen_capped` — see "Layout generation
    is a soft, local field — BUILT (D27)".
  - **Scaling past ~12x12.** Connectivity checked only at the leaf makes the search
    backtrack heavily at 13x13+ (a 15x15 does not finish) — the "pruning before 15x15"
    item below, now concrete. Incremental connectivity/symmetry pruning is the fix.
- **Word lists longer than 5.** Data is lengths 2..5. With the D24 cap (`max_len <=
  5`) a big grid needs *nothing longer* — that is the point. Longer lists are only
  needed for the *un*capped regime (a real 15x15 with 6..15-letter entries), same
  `cw`/`scored` pipeline, longer slice. Also: the curated list has no usable
  2-letter entries, so any grid with a length-2 slot is UNSAT on it — fine for
  American grids (min length 3).
- **Layout search pruning before 15x15 (was under D13).** `gen_patterns` enumerates
  raw orbit subsets and `gen_capped` checks connectivity at the leaf — both fine to
  ~12x12, both wanting incremental connectivity/symmetry-class pruning past it.
- **Theme placement.** Theme entries are chosen first and their lengths drive the
  layout; fill then works around fixed entries. `fill.solve` already supports this
  in principle (pre-place words / pre-fill cells before solving) but there is no
  API or theme-tagged word data yet. See "Grid variety" above — themes are where
  the soft objective (and a reason to sample) genuinely returns.
- Larger word SQUARES (the no-black case): order 8+ gets rare fast in English;
  feasibility/timing for 6x6, 7x7 on the curated list is still unmeasured.

## Layout generation is a soft, local field — the sampler's real home (not the fill) — BUILT (D27)

**Resolved for the core hypothesis (D27): the sampler was built, measured, and KEPT
(scoped).** `core/engines/gibbs_layout.py` is an annealed-Gibbs sampler over the
black-cell field — local factors for run-length legality, density, anti-cluster, and
no-2x2-block; symmetry by construction (orbit colouring); connectivity as a global BFS
**reject** (the one non-local constraint, exactly as flagged below). Head-to-head vs
`gen_capped` (notes.md): at 10x10 it wins on spread (cluster 0.67 vs 0.85) and
*guarantees* no 2x2 block (vs ~0.27/grid), and at the 12x12 frontier it stays productive
(1/15 miss, 8/14 distinct) where the complete search's node budget collapses (13/15
miss) — the phase-transition prediction below, confirmed. It loses on speed (~40x) and
10x10 diversity and is not complete, so it *coexists* with `gen_capped` (the fast default
+ existence-proof engine) rather than replacing it (`generate --gibbs`). The thesis that
follows is what motivated the spike; it is preserved because the **follow-ups it names
(WFC, ASP, connectivity, template libraries) are still open** — see "Still open after
D27" at the end.

A thesis worth recording before anyone reflexively reaches for a bigger backtracker
at 15x15. **The black-cell LAYOUT problem and the word FILL problem are opposite
regimes**, and we have (so far) attacked both with the same tool.

- **Fill** (assign words to slots) is a discrete, hard-bar CSP on a small filtered
  list. That is the regime where complete propagation-backtracking beat the
  stochastic sampler decisively (D7) and the sampler was retired (D19). Backtracking
  is *right* there; keep it.
- **Layout** (place the black cells) is the reverse: a **translation-invariant grid**
  with **local run-length legality** and a **soft, statistical objective** (density,
  spread, no 2x2 blocks, eventually theme-shaped architecture). And it *stiffens near
  a critical density* — the runaway backtracking we hit as `max_black` approached the
  feasibility minimum (D25, the reason a `node_budget` was needed) is textbook
  SAT/UNSAT **phase-transition** hardness: complete solvers choke near the threshold,
  and "few blacks, tightly packed" is literally the *jamming* end of that transition.

**The tell.** Every density knob D25 added — a per-cell white bias, a neighbour-count
anti-cluster penalty, a black-fraction target, "no 2x2 black block" — is a *local
kernel applied uniformly across the grid*. When your patches are all convolution-
shaped, the object is a **field with local factors** (a Markov random field / an
energy model), not something to hand-tune inside a systematic search. This is exactly
the **"big-and-soft" regime D19 explicitly reserved** as the one condition under which
sampling / message-passing / convolutional methods retake primacy. D3's original
post-classical instinct was not wrong; it was aimed at the wrong layer. It belongs to
the *geometry*, not the *packing* — and note the pleasing symmetry with D21, where
message-passing, evicted from generation, returned for solver *difficulty*: soft
problems keep wanting the soft tool.

**The honest boundary — where it stops being local.** Two constraints are global:
- **180° symmetry** — global, but *free*: generate one half and reflect. Not a problem.
- **Connectivity** (all white cells form one region) — global and *topological*. A
  convolution / local factor genuinely cannot express it, and it is precisely the
  leaf check that made our backtracker blow up. This is the real obstacle, and it is
  the same for everyone.

So the shape is **local-soft-legality (field-shaped) + one global topological
constraint (not)**. Knowing which is which is the actual payoff: a field/energy model
buys run-length + density + spread + aesthetics almost for free; connectivity you bolt
on as a separate global check or bake into the sampler's moves.

### What the field actually does (surveyed, to guide a future spike)

- **Wave Function Collapse** (Gumin, 2016; huge in procedural content generation). A
  grid of cells, each a *superposition* of allowed states; repeatedly collapse the
  **minimum-entropy** cell and propagate local adjacency constraints to neighbours.
  This is our layout problem's exact discrete-constraint-propagation shape — and its
  min-entropy rule *is* MRV, the very heuristic `fill.py` already uses. Caveat: vanilla
  WFC has no notion of global connectivity (same boundary as above).
- **Answer Set Programming for PCG** (Smith & Mateas, "design space" approach). A
  declarative constraint language whose solvers encode **reachability/connectivity in
  cyclic graphs in linear space** — the thing SAT/local models struggle with. This is
  the natural home for the *global* half (connectivity, min word-count, symmetry) while
  a field handles the local/soft half. A strong candidate if we want declarative,
  provable layout generation with connectivity first-class.
- **MRF / Ising–Potts / Gibbs sampling / energy-based models / diffusion.** A binary
  (black/white) or categorical grid with local factors *is* an Ising/Potts field;
  Gibbs "layout sampling" and, lately, diffusion models are how you draw from it. The
  energy is just `local legality + soft aesthetic penalties (density, anti-cluster,
  symmetry-by-construction)` — sample it, reject on the connectivity check. This is the
  D3 sampler's actual conceptual home, correctly placed at the *layout* layer this
  time. (Its return would be a fresh spike with a new hypothesis, per D19's reversal
  clause — not a resurrection of the fill sampler.)
- **CSP phase transitions** (random k-SAT satisfiability threshold; jamming
  universality). Grounds the D25 runaway: hardness for *complete* methods peaks at the
  SAT/UNSAT boundary, i.e. exactly where we push `max_black` toward the minimum. Our
  `node_budget` is a symptom-management patch on that; local/probabilistic methods are
  built for that landscape.
- **Real-world practice — the pragmatic shortcut.** Professional constructors mostly do
  *not* generate grids from scratch. They either start blank and add blocks by hand
  (NYT / Mark Berry) or, more often, **pick from a curated grid-template library** (500+
  American-style patterns, all 180°-symmetric, no 1–2-letter words, fully interlocked),
  chosen by theme-entry lengths; the automated hard part is the *fill* (NP-complete),
  which is the half we already do well. So a near-term, low-risk option that sidesteps
  the whole generation question: ship a small **curated template library per (size,
  cap)** and reserve field-based generation for when we want *novel / parameterised /
  themed* black architectures a fixed library can't cover.

### The shape of the spike — TAKEN (D27)

An energy/Gibbs (or WFC-style) sampler over the black-cell field — local factors for
run-length legality, density, and anti-cluster; symmetry by construction (fold the
grid) — with connectivity enforced as a global reject/repair (BFS or union-find), or
the whole thing expressed in ASP with reachability native. Keep `fill.py`'s complete
backtracker for the words untouched. The system then has a clean, honest seam:
**a soft field for the blacks, a complete CSP for the words** — the same complete-vs-
soft split the architecture already draws at D21 (difficulty) and D15 (the clue port),
now surfacing in the geometry. Until then, 10x10 backtracking (D24/D25) is a fine
stopgap and the template-library route is the cheap way to more sizes.

**This is what D27 built** — the energy/Gibbs sampler with a global connectivity
**reject** — and the seam it predicted is now real. **D28 then ran the basin-shape × count
study and the connectivity-repair follow-up** (notes.md). Its findings reshape this list:

- **Connectivity by repair — TRIED, DEFEATED by the cap, REMOVED (D28).** The obvious upgrade
  (whiten a "bridge" black to reconnect components) fixes **~0** disconnected capped
  layouts at every density/size: under a tight cap the separating blacks *are* the
  cap-load-bearing cells, so whitening a bridge re-creates an over-cap run (and a 6-run
  can't split into two ≥3 runs). It was deleted (D19-style; verdict in D28, code in git).
  Still open: connectivity that is *not* cap-coupled — an **ASP formulation with native
  reachability** (the survey's declarative route), which is a different object than local
  whitening, or a move set that respects run-length by construction so the two constraints
  never fight.
- **The real frontier is the LEGALITY wall, not connectivity (D28).** The study showed
  the sampler's failure mode shifts from connectivity to run-length legality as the grid
  grows (14x14: 0% legal at frac 0.20, all `over_cap`/`short_run`) — the cap-forced
  jamming density. Getting the field past ~12x12 wants a move set or schedule that reaches
  *exactly*-legal grids near the jam (WFC min-entropy propagation, run-length-aware moves,
  or a soft-field + complete-legalizer hybrid — the last risks re-importing a backtracker,
  see D28). The count knob's **floor** is physics (D25): asking below it is infeasible, not
  sparse.
- **WFC min-entropy as an alternative move.** The survey's Wave Function Collapse
  (min-entropy collapse + local propagation — which *is* MRV) was not built; it is the
  natural candidate for the legality-wall above, worth a bake-off vs Gibbs.
- **A curated template library.** The "pragmatic shortcut" (a small per-(size, cap)
  library of hand-vetted symmetric patterns) is still unbuilt — the cheapest route to
  *more sizes* with guaranteed-clean architecture, complementary to the sampler (which is
  for *novel/parameterised/themed* layouts a fixed library can't cover).
- **Field weights as a product surface.** `FieldParams` exists and D28 measured `w_cluster`
  as a clean spread lever (cluster 0.90→0.71); a calibrated "sparse / dense / spread" preset
  surface is the remaining product step.

References (surveyed 2026-07): Gumin, *WaveFunctionCollapse* (2016,
github.com/mxgmn/WaveFunctionCollapse); Smith & Mateas, "Answer Set Programming for
Procedural Content Generation: A Design Space Approach" (IEEE TCIAIG 2011,
adamsmith.as/papers/tciaig-asp4pcg.pdf); random-CSP satisfiability/phase-transition and
jamming-threshold literature (e.g. arXiv:1702.06919); MRF/Gibbs and energy-based/diffusion
layout sampling; crossword-construction practice and grid-template libraries
(communicrossings.com, Crossword Compiler grid libraries).

## Performance / completeness follow-ups

- Distinctness leaf-rejection is the known inefficiency (~13ms->380ms at 5x5). The
  down words are only complete at the last row, so duplicates are caught late.
  Could we prune earlier — e.g. detect when a partial column can only complete to
  an already-used word? Unimplemented; measure before optimising.
- We only measure time-to-FIRST grid, not enumerate-all or solution COUNT at a
  bar. "How many distinct minis exist at score>=X" is unknown and is a different,
  larger computation.
- UNSAT proofs are per-list theorems. If the curated list updates upstream, the
  ceilings must be re-measured (they are properties of the data).

## Data / scale hygiene

- Two score scales coexist (Zipf 0..8 vs crossword 0..100). This is a live
  foot-gun; see architecture.md invariant 4. A future cleanup could normalise both
  to a common 0..100 at ingestion, but that loses the "these are different signals"
  clarity. Undecided.
- Curated `cw_N.txt` is committed (a length-N slice, score>=25). Regenerating from
  a fresh upstream dump is a manual awk step (see notes.md); not scripted.
- Container is ephemeral; wordfreq / the raw dumps are NOT committed, only the
  derived lists are. Regeneration requires network + wordfreq for the weak list,
  and the upstream .dict for the curated list.

## Architecture follow-ups (post-D14)

The hexagonal layering + DI is in (D14). Left open:
- **Tool vs benchmark directory split.** `cli/` holds the typed tools; the
  benchmark/demo drivers still live in `scripts/` (loose, ANN-exempt). A
  `scripts/tools` vs `scripts/bench` layout, or promoting each benchmark to a
  `cli` module + `[project.scripts]` console command (only `mini`/`generate` have
  one today), is unresolved. Question: are benchmarks worth typing, or is "loose
  and throwaway" (CLAUDE) the right call permanently?
- **`gen_scored.py`** stays a bare `scripts/` maintenance tool (optional `wordfreq`
  dep, writes data files). It doesn't fit the DI model (it *produces* the lists the
  adapter reads). Fold it behind a `cli` + an output adapter, or leave it? Undecided.
- **Second adapters.** The ports (`LexiconSource`, `Writer`, `RngFactory`) have one
  implementation each. A second — an in-DB/remote word source, a JSON/`.ipuz`
  writer for export (see clue-generation), a JAX `Rng` for parallel chains (D3/D7)
  — is where the seams earn their keep; none built yet.
- **Wiring config.** `bootstrap` has a single `build()` with defaults and no config
  file. If tools grow options (list choice, data dir, output format) a small typed
  config surface (env/flags → `Config`) is the natural next step.
