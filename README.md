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

**Where it landed:** the solver is no longer the bottleneck — the lexicon is. On
dwyl + wordfreq we pack every 5×5 the list admits in ~15 ms, up to a provable
ceiling of `zipf≥4.5` (e.g. `makes/above/korea/event/seats`). Above that it's
provably UNSAT *for this list* — a property of the words, not the search.

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
| `scripts/ceiling.py`           | how high can the bar go before UNSAT |
| `data/words_N.txt`             | length-N words from dwyl `words_alpha` |
| `data/scored_N.txt`            | the above with wordfreq Zipf scores (see `scripts/gen_scored.py`) |

## Run

```bash
pip install numpy wordfreq          # wordfreq only needed to regenerate scores
python3 scripts/demo.py             # correctness across N=2..4
python3 scripts/ceiling.py 5        # 5x5 quality ceiling with backtracking
```

## Status / next

- [x] Lexicon, energy model, sampler, brute-force ground truth
- [x] Validated N=2 (vs. ground truth), 3, 4, 5
- [x] Acceptance test as the feedback signal; quality → feasibility on a filtered list
- [x] Complete backtracking engine — 5×5 in ~15 ms, 64–450× over the sampler
- [x] Mapped the frontier and the ceiling (dwyl+wordfreq: 5×5 tops out at zipf≥4.5)
- [ ] **Better lexicon** — the solver is done; a curated scored crossword list
      (e.g. Broda / Spread the Wordlist) is what lifts the quality ceiling
- [ ] Clue generation (separate downstream stage)
- [ ] JAX parallel chains — only if we reintroduce genuinely soft preferences

The word list here is deliberately weak (dwyl `words_alpha` + wordfreq Zipf) —
it exercised the packing and pinned the ceiling, and it is now provably the
limiting factor.
