# Word list sources

## data/words_N.txt, data/scored_N.txt
Derived from the dwyl `english-words` list (`words_alpha.txt`), scored with the
`wordfreq` Zipf frequency. Deliberately weak/uncurated — used to bring up the
solver and pin the packing ceiling. dwyl list: Unlicense/public domain.

## data/cw_N.txt  (curated, crossword-native)
Length-N slice of the Crossword-Nexus collaborative word list
(https://github.com/Crossword-Nexus/collaborative-word-list), MIT licensed
("free for everyone"). Format: `word score`, score 0-100 (60+ solid, 50
acceptable, <=30 weak). Includes proper nouns and de-spaced phrases, as a real
crossword fill wants. Score is crossword-enjoyment, not raw frequency.
