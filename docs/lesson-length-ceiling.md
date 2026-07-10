# The length ceiling — a data accident mistaken for a design constraint

**Status: synthesis / forward guidance (extracted at D36).** Not a post-mortem — nothing
died. This is the durable lesson from closing the 2..5 word-length gap, and the index for
reading the older, assumption-laden decisions correctly. Read it before you reason about
grid size, word length, or "how big can a mini get."

The decision log is append-only (see `CONTRIBUTING`/`CLAUDE.md`): the entries below that
assume 2..5 were **right for their time** and are load-bearing memory. This doc does not
rewrite them — it tells you how to read them now.

---

## TL;DR

- The "words are length **2..5**" ceiling was **data, never design.** The kernel was always
  length-agnostic — `Lexicon` takes any single length, `MultiLexicon` buckets over whatever
  `range(min_len, max_len+1)` a service asks for, and a missing length is just an empty
  (unfillable) bucket. Nothing in `core`/`app` ever hard-coded 5. D36 shipped lists to
  length 15 and the engines did not change by a line.
- We reasoned about that data gap as if it were permanent in ~a dozen places (indexed
  below). None were wrong when written; several read as present-tense-false now.
- **Two axes get conflated — keep them apart:**
  1. **Maximum word length** is a *vocabulary/data* property. Raising it enables the
     **less-dense** end of the blocked/capped design space: a larger `max_len` allows longer
     runs, so a big grid holds entries legal with *fewer* black cells → sparser, more open
     textures. *This* is what longer words buy.
  2. **Double-word-square order** is a *constraint-density* property. A fully-checked N×N
     square forces every row **and** column to be a word at once; its frontier is set by how
     rare simultaneous solutions get (order 7+ is rare in English), **not** by vocabulary
     reach. Longer lists do **not** meaningfully push square order — a 6×6 square happening
     to fill is incidental.

## The distinction, stated once, load-bearing

> "How long a word can we hold" ≠ "what double-word grids can we build."

They are related (a longer entry needs a longer list) but not the same, and the temptation is
to collapse them. When someone says "support longer words for more interesting grids," the
correct reading is: *widen the less-dense large-grid space* (sparser black-cell layouts with
longer runs), **not** *push the square order up*. The square order is gated by density and
search cost, and shipping vocabulary does nothing for it.

Corollary: after D36 the only real ceilings on grid size are (a) **search cost** — the
uncapped layout search still does not finish past ~12×12 (open-questions: "scaling past
~12×12"), and (b) **square-order rarity** — order 8+ word squares get rare fast in English.
Both are search/combinatorics limits. Neither is a data limit any more.

## Where the assumption appears — the index

Three buckets. Only the third was ever a correctness problem, and it is fixed.

1. **Legitimate and permanent — leave forever.** `5x5` as the canonical NYT-mini object; the
   measured theorems ("top tier admits exactly 38 distinct 5×5 minis"; the weak list's
   56→8→0 collapse; per-bar openness on 5×5). These are the product and its measurements,
   not an assumption. (`architecture.md` §invariants/openness, `notes.md` throughout, and
   the D31 counting theorem / `postmortem-kernel-methods.md`.)

2. **Historical ADR context — append-only, read as "true when written."** These assumed
   2..5 as the live data and reasoned correctly from it. Do **not** edit them; D36 is their
   reversal note.
   - **D12** (`decisions.md` ~line 161): "word lists cover lengths 2..5, so demos use slots
     ≤ 5" — the blocked-grid spike's scope.
   - **D24** (`decisions.md` ~lines 904–967): the whole "cap the entry length, don't grow the
     lists" argument — "no length-6+ data needed," "nothing beyond length 5 is ever asked
     for," "fills from the length-2..5 data we already have." D24's *reasoning stands* (the
     cap is still the right lever for a **short-word** big grid); only its premise that
     length-6+ lists don't exist is superseded.

3. **Live / authoritative statements — corrected at D36.** These are the ones that would
   mislead if left present-tense:
   - `architecture.md` — the blocked-grid data-model note (now "lengths 2..15") and the D24
     cap rationale (now "no length-6+ lists *required*; those lists exist, D36").
   - `open-questions.md` — "Word lists longer than 5" now **DONE (D36)**.
   - `notes.md` — the large-capped-mini narrative and provenance/regeneration section
     (now 2..15, reproducible drivers, and the less-dense-payoff framing).

## How not to re-cook it

- When you meet "2..5" / "no length-6+" / "data we don't have" in `docs/`, **check the
  D-number/date.** Anything pre-D36 is describing the old data gap; the shipped data is
  **2..15** (all of `cw`/`scored`/`words`).
- `max_len` (on `CappedLayout`/`GibbsLayout`) and the grid order (on `FullSquare`) are honest
  configuration knobs now — gated by search cost and combinatorial rarity, not by a missing
  file. If a length ≤ 15 slot won't fill, that is a bar/feasibility result, not "we don't
  have the words."
- The data is **reproducible**: `scripts/gen_cw.py`, `gen_words.py`, `gen_scored.py`, each
  `--min-len/--max-len`. `gen_cw.py` re-derives the committed `cw_5.txt` byte-exact — that
  reproduction is the correctness gate for any regeneration. Extending past 15 is a one-flag
  change, not a project.
- Before proposing "grow the word lists to make bigger grids," ask which axis you mean. If
  it's *less-dense* large grids: the lists already reach; raise `max_len`. If it's *bigger
  word squares*: longer lists won't help — that's the search/density frontier, a different
  problem (and a real open one).
