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
baseline. Follow-up not done: GitHub's *default branch* setting may still point at
`claude/empty-repo-review-0vagwh`; flipping it to `main` is a one-click settings
change. Reversal: n/a.
