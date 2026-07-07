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

## Does the sampler earn its keep?

`sampler.py` is the secondary engine and is ~50-80x slower than backtracking on
distinct filtered lists (its solve-rate collapses on the small/hard ones). It NOW
enforces distinctness (D11, `distinct=True`), so the "fix it" option is done; the
strategy study (samplers.py) also showed distinctness is not its bottleneck, so
the guided penalty barely beats the naive gate. It is retained for (a) genuinely
soft preferences and (b) sample-distribution behaviour. Question narrows to: keep
or delete? Resolution depends on whether soft preferences return (see variety,
above). If they do, the sampler (or a JAX parallel-chain version) may retake
primacy; the distinctness penalty is already in place, but would want vectorising
harder (it currently rebuilds N*26 column strings per near-feasible step).

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
