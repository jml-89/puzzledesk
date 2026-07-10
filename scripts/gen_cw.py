"""Generate the curated, crossword-native word lists: 'word<space>score' per line
(score 0-100), for every length in a range.

Slices the Crossword-Nexus collaborative word list (``xwordlist.dict``, ``WORD;score``
lines) into per-length buckets: lowercase, alphabetic-only (proper nouns and de-spaced
phrases survive as single tokens, as a real fill wants), score at or above a floor,
de-duplicated keeping the highest score, sorted by descending score then word. This is
the default list the generator draws from (``data/cw_N.txt``); score is
crossword-enjoyment, not raw frequency.

Run once to (re)generate ``data/cw_N.txt`` for the chosen lengths.

    uv run scripts/gen_cw.py                  # lengths 2..15 from the canonical URL
    uv run scripts/gen_cw.py --min-len 6      # only add the longer lengths
    uv run scripts/gen_cw.py --source path    # slice a local xwordlist.dict
"""

import argparse
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
SOURCE_URL = (
    "https://raw.githubusercontent.com/Crossword-Nexus/collaborative-word-list/main/xwordlist.dict"
)
FLOOR = 25  # score 0-100; <=30 is weak, drop the dregs (matches the shipped 2..5 lists)


def read_source(src: str) -> str:
    """Read the source list from a local path or an http(s) URL."""
    if src.startswith(("http://", "https://")):
        with urllib.request.urlopen(src) as resp:
            return resp.read().decode("utf-8", "replace")
    return Path(src).read_text()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-len", type=int, default=2)
    ap.add_argument("--max-len", type=int, default=15)
    ap.add_argument("--floor", type=int, default=FLOOR, help="drop scores below this (0-100)")
    ap.add_argument("--source", default=SOURCE_URL, help="local path or URL of xwordlist.dict")
    args = ap.parse_args()

    # length -> {word: best score seen}
    buckets: dict[int, dict[str, int]] = {n: {} for n in range(args.min_len, args.max_len + 1)}
    for line in read_source(args.source).splitlines():
        parts = line.split(";")
        if len(parts) != 2:
            continue
        w = parts[0].strip().lower()
        try:
            score = int(parts[1])
        except ValueError:
            continue
        if not w.isalpha() or score < args.floor or len(w) not in buckets:
            continue
        best = buckets[len(w)]
        if w not in best or score > best[w]:
            best[w] = score

    for n in range(args.min_len, args.max_len + 1):
        rows = sorted(buckets[n].items(), key=lambda ws: (-ws[1], ws[0]))
        (DATA / f"cw_{n}.txt").write_text("".join(f"{w} {s}\n" for w, s in rows))
        print(f"cw_{n}.txt: {len(rows)} words (floor>={args.floor})")


if __name__ == "__main__":
    main()
