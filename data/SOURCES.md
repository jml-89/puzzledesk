# Word list sources

All three families ship one file per length, **lengths 2..15** (D36). The derived
lists are committed; the raw upstream dumps are not. Everything is reproducible with
the `scripts/gen_*.py` drivers (each `--min-len/--max-len`, defaulting to the URLs
below or a local `--source`).

Storage: kept as plain files in git deliberately (~9.7 MB raw / ~3-4 MB packed, rarely
changes, and the solvers just `read_text` them). Not worth Git LFS at this size; revisit
LFS -- or drop the committed lists and regenerate from the drivers -- only if the corpus
grows structurally (more languages, much larger curated lists, or binary artifacts).

## data/words_N.txt, data/scored_N.txt
Derived from the dwyl `english-words` list (`words_alpha.txt`), scored with the
`wordfreq` Zipf frequency. Deliberately weak/uncurated — used to bring up the
solver and pin the packing ceiling. dwyl list: Unlicense/public domain.
Regenerate: `scripts/gen_words.py` then `scripts/gen_scored.py` (needs `wordfreq`).

## data/cw_N.txt  (curated, crossword-native)
Length-N slice of the Crossword-Nexus collaborative word list
(https://github.com/Crossword-Nexus/collaborative-word-list), MIT licensed
("free for everyone"). Format: `word score`, score 0-100 (60+ solid, 50
acceptable, <=30 weak). Includes proper nouns and de-spaced phrases, as a real
crossword fill wants. Score is crossword-enjoyment, not raw frequency.
Regenerate: `scripts/gen_cw.py` (re-derives the committed `cw_5.txt` byte-exact).
