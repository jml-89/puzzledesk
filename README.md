# puzzledesk

Dense crossword generation — the NYT-mini style, where a 5×5 grid has no black
cells and every letter is checked twice. That object is a **double word square**
of order 5: five across words and five down words, fully interlocked.

## Approach

We treat filling as **sampling from an energy-based model** rather than
backtracking search. The grid is a Markov random field on a 2-D lattice; each
cell couples only to its row word and column word. We define an energy over
complete configurations and draw low-energy samples.

The current representation keeps state small: **state = the N across (row)
words**; the down words are *induced* by reading the grid column-wise.

```
energy(state) = number of induced columns that are not valid words
```

Zero energy ⇔ a valid double word square. The local update, for one row, uses
the per-column "allowed letters" marginal (which letters keep each column a real
word) — the message-passing flavour, done locally and cheaply.

Building small-first (2×2 → 3×3 → 4×4 → 5×5): at N=2 we enumerate every valid
square by brute force as ground truth; above that, `energy()==0` guarantees
validity by construction.

## Layout

| Path | What |
|------|------|
| `src/puzzledesk/lexicon.py`    | word storage; `set` for column checks + `(M,N)` letter matrix for pattern queries |
| `src/puzzledesk/square.py`     | double-word-square representation and energy |
| `src/puzzledesk/sampler.py`    | min-conflicts / annealed-Gibbs sampler with restarts |
| `src/puzzledesk/bruteforce.py` | exhaustive enumeration (ground truth, tiny orders) |
| `scripts/demo.py`              | validation across N=2..4 |
| `data/words_N.txt`             | length-N words filtered from the dwyl `words_alpha` list |

## Run

```bash
pip install numpy
python3 scripts/demo.py
```

## Status / next

- [x] Lexicon, energy model, sampler, brute-force ground truth
- [x] Validated N=2 (vs. ground truth), 3, 4 — 100% solve, sub-5 ms/run
- [ ] N=5, the main event
- [ ] Word **quality** scoring (fold into the energy as a soft term) — the weak
      dwyl list packs fine but produces junky fills
- [ ] Vectorise the hot loop onto JAX for parallel-chain / annealed exploration

The word list here is deliberately weak (dwyl `words_alpha`, ~370k entries incl.
much obscure junk) — enough to exercise packing before investing in a scored
lexicon.
