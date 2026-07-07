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
**complete propagation-backtracking search** (`backtrack.py`): 64–450× faster
than the sampler at 5×5, and *complete*, so it can prove when no acceptable grid
exists at all.

**Distinctness.** A genuine double word square needs all 2N words distinct.
Otherwise the solver falls into the **symmetric basin** — a grid symmetric down
the diagonal has across ≡ down, the down constraints collapse onto the across
ones, and you get an easy, degenerate fill that's really only N words. Both the
acceptance test and the solver enforce 10-distinct; killing the basin drops 5×5
from 17 ms → ~420 ms (the real problem is harder) and lowers the honest ceiling.

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

## Layout

| Path | What |
|------|------|
| `src/puzzledesk/lexicon.py`    | word storage; `set` for column checks, `(M,N)` letter matrix for pattern queries, per-word scores, `filtered(bar)` |
| `src/puzzledesk/square.py`     | double-word-square representation and energy |
| `src/puzzledesk/backtrack.py`  | **complete** prefix-pruned search — the primary engine |
| `src/puzzledesk/sampler.py`    | min-conflicts / annealed-Gibbs sampler (soft-objective / diversity engine) |
| `src/puzzledesk/validate.py`   | acceptance test — bottleneck (weakest-word) verdict |
| `src/puzzledesk/bruteforce.py` | exhaustive enumeration (ground truth, tiny orders) |
| `scripts/demo.py`              | validation across N=2..4 |
| `scripts/frontier.py`          | sweep the acceptance bar; where does packing stay feasible |
| `scripts/compare.py`           | sampler vs backtracking head-to-head |
| `scripts/ceiling.py`           | how high can the bar go before UNSAT (`ceiling.py 5 cw`) |
| `scripts/mini.py`              | **the generator** — print distinct minis above a quality bar |
| `data/words_N.txt`             | length-N words from dwyl `words_alpha` |
| `data/scored_N.txt`            | the above with wordfreq Zipf scores (weak baseline list) |
| `data/cw_N.txt`                | curated crossword list, scored 0–100 (the real list) |
| `data/SOURCES.md`              | provenance and licenses for the word lists |

## Run

```bash
pip install numpy wordfreq          # wordfreq only needed to regenerate scores
python3 scripts/demo.py             # correctness across N=2..4
python3 scripts/mini.py 5 70 3      # three 5x5 minis, every word score >= 70
python3 scripts/ceiling.py 5 cw     # 5x5 quality ceiling on the curated list
```

## Status / next

- [x] Lexicon, energy model, sampler, brute-force ground truth
- [x] Validated N=2 (vs. ground truth), 3, 4, 5
- [x] Acceptance test as the feedback signal; quality → feasibility on a filtered list
- [x] Complete backtracking engine — 5×5 in ~15 ms, 64–450× over the sampler
- [x] 10-distinct-words constraint (forbid the symmetric basin) in test + solver
- [x] Mapped the frontier and honest ceiling (distinct 5×5 tops out ~zipf≥3.5;
      ≥4.0 provably UNSAT on the weak list)
- [x] **Curated lexicon** — swapped in the Crossword-Nexus list; distinct 5×5
      minis with every word ≥90, publishable fills. `scripts/mini.py` generates.
- [ ] Clue generation (separate downstream stage)
- [ ] Grid variety controls — seed words, themes, avoid overused entries
- [ ] JAX parallel chains — only if we reintroduce genuinely soft preferences
