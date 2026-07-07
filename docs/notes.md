# Running notes

Miscellany that does not fit README or the other docs: benchmark numbers,
environment quirks, data provenance and exact regeneration commands, and gotchas
that cost time. Append freely.

## Benchmark results (as measured this spike)

Machine: the ephemeral dev container (see below). NumPy 2.4.x, single-threaded
Python. Numbers are order-of-magnitude, not tightly controlled.

Packing is easy while the list is large:
- 5x5 on the weak list at Zipf>=2.5 (~4550 words), NON-distinct: ~82 ms/run,
  40/40 solved, median 0 restarts. Interlock does not bite when the list is big.

Sampler vs backtracking, 5x5, weak list, filtered, distinctness OFF (the ORIGINAL
early comparison, before the sampler enforced distinctness), same acceptance bar:
- T(Zipf)=3.0 (3130 words): sampler 2090 ms vs backtrack 33 ms  (64x)
- T=3.5 (1972 words):        sampler 3003 ms vs backtrack 17 ms  (174x)
- T=4.0 (1113 words):        sampler 5808 ms vs backtrack 13 ms  (450x)
Speedup GROWS as the list shrinks: stochastic local search degrades exactly where
systematic search improves. This is the empirical basis for D7.

Sampler vs backtracking on the DISTINCT problem (5x5, weak list, distinct=True,
sampler = penalty strategy, 10 seeds; re-measured this container). Both solve the
same problem now, so the comparison is apples-to-apples:
- T(Zipf)=3.0 (3130 words): sampler ~9.0 s (10/10) vs backtrack 0.12 s (10/10)  (~77x)
- T=3.5 (1972 words):        sampler ~22 s (3/10)  vs backtrack 0.27 s (10/10)
At T=3.5 the sampler's SOLVE RATE collapses (3/10) while backtracking stays 10/10
and complete; a raw ms ratio there is misleading because most sampler runs burn
their whole restart budget without solving. This is D7 confirmed on the distinct
problem: backtracking is the right engine for small/hard/filtered lists.

Sampler strategy study (scripts/samplers.py, 5x5, distinct=True, 10 seeds):
- gate (restart on a degenerate valid grid) vs penalty (duplicate-pair penalty in
  the move). On these lists the two are COMPARABLE: penalty is never worse on
  solve rate (10/10 vs 10/10 at T=3.0; 3/10 vs 2/10 at T=3.5) but adds per-step
  overhead (it rebuilds N*26 column strings when near feasibility). Finding: at
  N=5 distinctness is NOT the sampler's bottleneck -- reaching feasibility is --
  so the guided penalty buys only a marginal robustness edge. penalty is the
  default (guided=True) as the principled "actively enforce" behaviour; gate is
  the honest baseline it is measured against. Neither rivals backtracking.

Distinctness cost (5x5, backtracking, this container): removing the symmetric
basin took ~13 ms -> ~380 ms at Zipf>=3.5 (weak list) and ~19 ms -> ~620 ms at
score>=90 (curated). The easy speed was partly degenerate grids.

Honest ceilings (distinct=True):
- Weak list (Zipf): 5x5 tops out ~Zipf>=3.5 (e.g. mates/irene/linda/asset/needs);
  Zipf>=4.0 is provably UNSAT (exhaustive search, ~1.3 s to prove). Fills are
  name-heavy because dwyl has lowercased proper nouns it cannot distinguish.
- Curated list (crossword 0..100 score): 5x5 packs distinct grids with EVERY word
  >= 90 (top tier). Approx per-bar (25 seeds):
    score>=60 (5372 w): 25/25, 25 distinct, ~104 ms; kneel/nolte/aloha/capes/knelt
    score>=70 (4981 w): 25/25, 25 distinct, ~186 ms; acres/rhino/cigar/elect/delts
    score>=80 (4624 w): 25/25, 24 distinct, ~206 ms; parer/acela/turin/crust/hanes
    score>=90 (2384 w): 25/25, 18 distinct, ~844 ms; sedan/credo/rotor/adept/perth

Reading the "solved X/25": backtracking is complete, so one run settles
existence. The 25 randomised runs measure DIVERSITY (distinct grids) and average
TIMING; for UNSAT the ms is time-to-prove-unsat (full tree). Do not read it as a
success rate.

Black-cell fill (blocked.py/fill.py, this container): a 5x5 with corner or edge
blocks fills from the curated list (bar>=50) in a few ms per seed; raising the bar
on a fixed pattern the length-3 bucket empties between bar 90 (SAT, ~200 ms real
search) and 92 (0 three-letter words -> UNSAT), the blocked echo of "the lexicon
is the ceiling". Tiny 2x3 blocked grid: 66,201 distinct fills brute-forced as
ground truth, solver output a strict subset over 60 seeds. Data covers lengths
2..5, so demos use slots <= 5; the curated list has no 2-letter entry above any
real bar (length-2 slots are UNSAT on it).

## Environment quirks (dev container)

- Fresh container, initially EMPTY repo (zero commits). Because the first pushed
  branch becomes the GitHub default, the working branch `claude/empty-repo-review-
  0vagwh` became default; `main` was added later (D10) but the default-branch
  SETTING may still point at the working branch.
- Nothing preinstalled: no NumPy, no JAX, no system word list. `pip install numpy
  wordfreq` works (installs NumPy 2.4.x, wordfreq). JAX not installed (deferred).
- Container is EPHEMERAL and restarts lose /tmp and background tasks. Anything
  worth keeping must be committed. During this spike a restart killed background
  benchmark jobs; re-run rather than resume.
- Do not chain `sleep` in one bash call to wait; the harness blocks it. Use
  background runs or an until-loop.

## Data provenance and regeneration

Two families, DIFFERENT SCORE SCALES (architecture.md invariant 4):

Weak baseline — `data/words_N.txt` and `data/scored_N.txt`:
- Source: dwyl english-words `words_alpha.txt` (~370k words). Public domain.
  URL: https://raw.githubusercontent.com/dwyl/english-words/master/words_alpha.txt
- GOTCHA: that file has CRLF line endings. `awk 'length($0)==n'` counts the
  trailing \r, so every length bucket is off by one unless you strip \r first.
  This bit us; strip with `tr -d '\r'` before filtering.
- Regenerate length lists:
    tr -d '\r' < words_alpha.txt > clean.txt
    for n in 2 3 4 5; do awk -v n=$n 'length($0)==n' clean.txt > data/words_$n.txt; done
- Scores: `scripts/gen_scored.py` (needs wordfreq) writes `scored_N.txt` as
  "word zipf" for words with Zipf >= 2.0 (drops zero-signal junk like 'aalii').

Curated real list — `data/cw_N.txt`:
- Source: Crossword-Nexus collaborative word list, MIT licensed.
  URL: https://raw.githubusercontent.com/Crossword-Nexus/collaborative-word-list/main/xwordlist.dict
  Format: `WORD;score`, score 0..100, ~567k entries incl. de-spaced phrases and
  proper nouns (uppercase, no spaces). Convention: 60+ solid, 50 acceptable,
  <=30 weak/roll-your-own.
- Regenerate length-N slice (lowercased, score>=25, sorted by score desc):
    awk -F';' -v n=$n '$1 ~ /^[A-Za-z]+$/ && length($1)==n && $2>=25 {print tolower($1)" "$2}' \
      xwordlist.dict | sort -t' ' -k2,2nr -k1,1 > data/cw_$n.txt
- Provenance/licenses also recorded in data/SOURCES.md.
- Only the DERIVED length lists are committed; the raw dumps are not.

## Gotchas that cost time

- CRLF in the dwyl list (above).
- Score scales differ per list; a threshold only means something against its own
  list. `ceiling.py` chooses default thresholds by list name for this reason.
- The sampler enforces distinctness only with `distinct=True` (default off, so the
  raw-packing scripts bench.py/quality.py are unchanged). With it off it can emit
  a degenerate square; validate output if you use that path.
- Empty-repo default-branch behaviour (above).
- Brute-force enumeration is only viable at N=2; at N=3+ on a permissive list the
  count is huge — do not enumerate the full list.

## Repo status at end of spike

- On `origin/main` at the spike HEAD (8 commits). Working tree clean.
- Engine: complete backtracking primary, sampler secondary. Distinctness enforced
  in backtrack + validate + sampler (distinct=True). Curated list wired via
  `from_scored_file`.
- Deliverable: `scripts/mini.py` generates distinct minis above a quality bar.
- Not started: clue generation, cross-batch variety, JAX, black-cell grids.
