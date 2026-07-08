# puzzledesk

Dense crossword generation — the NYT-mini style, where a 5×5 grid has no black
cells and every letter is checked twice. That object is a **double word square**
of order 5: five across words and five down words, fully interlocked.

## Approach

Across the two engines here, **state = the N across (row) words**; the down words
are *induced* by reading the grid column-wise. A grid is a valid double word
square iff every induced column is itself a real word.

### The arc (how the design was found)

We started with **energy-based sampling** — the grid as a Markov random field on
a 2-D lattice, `energy = number of invalid columns`, drawn toward zero by an
annealed min-conflicts move (`sampler.py`). It packs 5×5 fast on a big list.

Then we built the **acceptance test** as a first-class feedback signal
(`validate.py`), and it corrected the objective. A grid is acceptable iff *every*
across and down word clears a quality bar — a **bottleneck (min) test**, not an
average; one obscure word fails the whole grid. Averaging word-frequency was the
wrong signal.

That reframe collapsed "quality" into **feasibility on a threshold-filtered
list**: filter to words above the bar, solve feasibility, and every result
passes by construction — no soft-weighting. But on the small, hard lists that
high bars produce, min-conflicts wanders. So the right engine became a
**complete propagation-backtracking search** (`backtrack.py`): it solves a
distinct 5×5 in ~0.1–0.3 s where the stochastic sampler needs seconds
(≈50–80× faster), and — on the small, hard lists high bars produce — the
sampler's solve-rate collapses (2–3/10) while backtracking stays 10/10 and,
being *complete*, can even prove when no acceptable grid exists at all.

**Distinctness.** A genuine double word square needs all 2N words distinct.
Otherwise a solver falls into the **symmetric basin** — a grid symmetric down
the diagonal has across ≡ down, the down constraints collapse onto the across
ones, and you get an easy, degenerate fill that's really only N words. All three
paths now enforce 10-distinct: the acceptance test, the backtracker (pruning +
leaf check), and the sampler (a duplicate-pair penalty in the move, see
`samplers.py`). Killing the basin drops backtracking's 5×5 from ~13 ms → ~380 ms
(the real problem is harder) and lowers the honest ceiling.

**Where it landed:** the solver is no longer the bottleneck — the lexicon is. On
dwyl + wordfreq the genuine (10-distinct) 5×5 ceiling is ~`zipf≥3.5`
(`mates/irene/linda/asset/needs`); `zipf≥4.0` is provably UNSAT *for this list*.
That diagnosis was confirmed by swapping in a **curated crossword list** (the
Crossword-Nexus collaborative list, MIT, scored 0–100 for solver-enjoyment): the
ceiling jumps from "UNSAT at zipf 4" to **every word scoring ≥90** — genuine
distinct minis like `sedan/credo/rotor/adept/perth` in ~0.8 s, or ≥70-quality
grids (`rotor/atone/strep/petal/srsly` × `rasps/otter/torts/oneal/reply`) in
~0.2 s. Same solver, unchanged — the words were the whole story.

Building small-first (2×2 → 3×3 → 4×4 → 5×5): at N=2 we enumerate every valid
square by brute force as ground truth; above that, validity is by construction.

**Black cells (the model generalization).** The induced-column trick above is
load-bearing but only works while every row and column is one full-length word.
Real crosswords have black cells, so a grid becomes a set of **slots** (maximal
white runs, across and down) of *varying length* that **cross** at shared cells —
there is no single column to read. `blocked.py` parses a black-cell pattern into
that slot/crossing graph; `fill.py` fills it as a CSP over slots with the same
complete backtracking (now with MRV ordering and per-slot *pattern* queries into
a length-bucketed `MultiLexicon`), still distinct, still every entry ≥ the bar by
construction. Same small-first discipline: a tiny blocked grid is enumerated as
ground truth.

The block pattern itself is now a **parameter, not a fixed template**: you give a
shape and a *number* of black cells and `patterns.py` searches the legal layouts
— fully checked (no unchecked cells, no sub-`min_len` runs), white cells connected
— with the same complete backtracking, then fills each until one solves. Because
the layout search and the fill are both complete, "no grid" is a proof, not a
timeout. Word lists longer than 5 (for full-size 15×15 grids) are the remaining
step — see `docs/open-questions.md`.

**Symmetry is optional.** By default the layout search is restricted to
180°-symmetric grids (the crossword convention), where a black cell is chosen as
a *rotation orbit* — so a symmetric grid can only carry an odd black count when a
centre cell absorbs it, and often not even then (a centre black on a 5×5 splits
the middle row/column into length-2 runs, so *no* symmetric 3-black 5×5 exists).
Pass `symmetric=False` (`--nonsymmetric` on `generate.py`) and each cell is its
own unit: any legal placement is allowed, which is the only way to get e.g. 3
black cells across a 5×5. The completeness guarantee is unchanged — the search
just enumerates a larger legal set.

## Layout

The package is a hexagon (ports & adapters) with a linear import stack enforced by
import-linter: `core < app < adapters < bootstrap < cli` (see
`docs/architecture.md`).

| Path | What |
|------|------|
| `src/puzzledesk/core/lexicon.py`    | word storage; `set` for column checks, `(M,N)` letter matrix for pattern queries, per-word scores, `filtered(bar)`, `matching(pattern)`, text parsers; `MultiLexicon` buckets words by length for blocked grids |
| `src/puzzledesk/core/square.py`     | double-word-square representation and energy (the fully-checked model) |
| `src/puzzledesk/core/blocked.py`    | **blocked grids** — parse a black-cell pattern into the across/down slot + crossing graph |
| `src/puzzledesk/core/validate.py`   | acceptance test — bottleneck (weakest-word) verdict |
| `src/puzzledesk/core/rng.py`        | the `Rng`/`RngFactory` ports — randomness is injected, not built in the kernel |
| `src/puzzledesk/core/engines/backtrack.py`  | **complete** prefix-pruned search — the primary engine for squares |
| `src/puzzledesk/core/engines/sampler.py`    | min-conflicts / annealed-Gibbs sampler; enforces distinctness (`distinct=True`) via a duplicate-pair penalty |
| `src/puzzledesk/core/engines/fill.py`       | **complete** MRV backtracking fill over slots — the blocked-grid engine (+ `enumerate_fills` ground truth) |
| `src/puzzledesk/core/engines/patterns.py`   | **block-pattern generation** — from a black-cell *count* to legal layouts; `fill_by_count` ties layout search to fill |
| `src/puzzledesk/core/engines/bruteforce.py` | exhaustive enumeration (ground truth, tiny orders) |
| `src/puzzledesk/app/`               | use-case services (`MiniService`, `BlockedGenerateService`), the ports they need (`LexiconSource`, `Writer`), and structured results |
| `src/puzzledesk/adapters/`          | infrastructure implementing the ports: `NumpyRngFactory` (the injected Prng), `FileLexicon` (disk reads), `StreamWriter` |
| `src/puzzledesk/bootstrap/`         | composition root — `build()` a service `Container` in stages (config → adapters → services) |
| `src/puzzledesk/cli/`               | thin entry points: argv → build → run → present |
| `tests/`                            | pytest suite — invariants, ground truth, DI (fakes for the ports) |
| `scripts/mini.py`, `scripts/generate.py` | tool shims (logic in `cli/`); also `uv run mini …` / `uv run generate …` |
| `scripts/demo.py`              | validation across N=2..4 (benchmark driver) |
| `scripts/frontier.py`          | sweep the acceptance bar; where does packing stay feasible |
| `scripts/compare.py`           | sampler vs backtracking head-to-head (same distinct problem) |
| `scripts/samplers.py`          | sampler strategy study — gate vs distinctness-penalty |
| `scripts/ceiling.py`           | how high can the bar go before UNSAT (`ceiling.py 5 cw`) |
| `scripts/blackcells.py`        | **blocked-grid fill** — ground-truth check, filled grids, quality ceiling |
| `data/words_N.txt`             | length-N words from dwyl `words_alpha` |
| `data/scored_N.txt`            | the above with wordfreq Zipf scores (weak baseline list) |
| `data/cw_N.txt`                | curated crossword list, scored 0–100 (the real list) |
| `data/SOURCES.md`              | provenance and licenses for the word lists |

## Run

The project uses [uv](https://docs.astral.sh/uv/). `uv run` provisions the
virtualenv (installing `puzzledesk` and its deps) on first use, so no manual
`pip install` step is needed.

```bash
uv run scripts/demo.py             # correctness across N=2..4
uv run scripts/mini.py 5 70 3      # three 5x5 minis, every word score >= 70
uv run scripts/ceiling.py 5 cw     # 5x5 quality ceiling on the curated list
uv run scripts/blackcells.py       # blocked-grid fill: ground truth + filled grids
uv run scripts/generate.py 5 5 4 60 3   # 5x5 minis with 4 black cells, layout found by search
uv run scripts/generate.py 5 5 3 60 3 --nonsymmetric  # 3 black cells, no 180° symmetry
```

`wordfreq` is only needed to regenerate the scored word lists; install it with
the `scoring` extra and run the generator:

```bash
uv run --extra scoring scripts/gen_scored.py   # rebuild data/scored_N.txt
```

## Development

```bash
uv sync                # create/refresh the dev environment
uv run ruff check      # lint
uv run ruff format     # format
uv run mypy            # type-check src/puzzledesk
uv run lint-imports    # enforce the hexagonal layers (import-linter)
uv run pytest          # invariants + ground truth + DI
```

Ruff (lint + format), mypy, import-linter and pytest are configured in
`pyproject.toml`. The package ships type information (`py.typed`); `mypy` runs with
`disallow_untyped_defs`, so new code in `src/puzzledesk` must be fully annotated.
`lint-imports` fails the build on a forbidden cross-layer import, so the
architecture is a checked fact, not a convention.

## Deeper docs (agent-facing, in `docs/`)

- `docs/architecture.md` — data model, invariants, the two engines, gotchas
- `docs/decisions.md` — decision log (why it is shaped this way)
- `docs/open-questions.md` — unresolved questions and next-spike considerations
- `docs/notes.md` — benchmarks, environment quirks, data provenance/regeneration

## Status / next

- [x] Lexicon, energy model, sampler, brute-force ground truth
- [x] Validated N=2 (vs. ground truth), 3, 4, 5
- [x] Acceptance test as the feedback signal; quality → feasibility on a filtered list
- [x] Complete backtracking engine — non-distinct 5×5 in ~15 ms; on the distinct
      problem ~50–80× over the sampler and complete where the sampler stalls
- [x] 10-distinct-words constraint (forbid the symmetric basin) in test, solver,
      and sampler; strategy study (`samplers.py`) settles how the sampler enforces it
- [x] Mapped the frontier and honest ceiling (distinct 5×5 tops out ~zipf≥3.5;
      ≥4.0 provably UNSAT on the weak list)
- [x] **Curated lexicon** — swapped in the Crossword-Nexus list; distinct 5×5
      minis with every word ≥90, publishable fills. `scripts/mini.py` generates.
- [x] **Black cells** — slot/crossing model + complete MRV backtracking fill;
      varying-length slots, distinct entries, every entry ≥ bar; tiny grid vs
      brute-force ground truth. `scripts/blackcells.py`. (Fill only.)
- [x] **Block-pattern generation** — black cells are a *count*, not a template;
      `patterns.py` searches legal symmetric/checked/connected layouts and fills
      them, complete both ways (`scripts/generate.py`)
- [x] **Non-symmetric black cells** — `symmetric=False` drops the 180° constraint
      so any legal placement is allowed (e.g. 3 blacks across a full 5×5, which no
      symmetric layout admits); `generate.py --nonsymmetric`
- [x] **Hexagonal architecture** — pure `core`, `app` services, `adapters` (the
      injected Prng lives here), a staged `bootstrap` container, thin `cli`; layering
      enforced by import-linter; pytest suite driven by injected fakes (D14)
- [ ] Word lists longer than 5 — needed for full-size (15×15) blocked grids
- [ ] Clue generation (separate downstream stage)
- [ ] Grid variety controls — seed words, themes, avoid overused entries
- [ ] JAX parallel chains — only if we reintroduce genuinely soft preferences
