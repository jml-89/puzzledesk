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
  first that solves, complete both ways. Follow-ups left open: the layout search
  enumerates raw orbit subsets (no dedup by symmetry class, connectivity checked at
  the leaf not incrementally) — fine at 5x5, wants pruning before 15x15; and there
  is no control over WHICH legal layout beyond "first that fills" (word-count
  target, black-cell distribution, avoiding stacked/awkward shapes are unmodelled).
- **Word lists longer than 5.** Data is lengths 2..5, so demos use slots <= 5. A
  full 15x15 needs 6..15-length lists (same `cw`/`scored` pipeline, longer slice).
  Also: the curated list has no usable 2-letter entries, so any grid with a
  length-2 slot is UNSAT on it — fine for American grids (min length 3).
- **Theme placement.** Theme entries are chosen first and their lengths drive the
  layout; fill then works around fixed entries. `fill.solve` already supports this
  in principle (pre-place words / pre-fill cells before solving) but there is no
  API or theme-tagged word data yet. See "Grid variety" above — themes are where
  the soft objective (and a reason to sample) genuinely returns.
- Larger word SQUARES (the no-black case): order 8+ gets rare fast in English;
  feasibility/timing for 6x6, 7x7 on the curated list is still unmeasured.

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
