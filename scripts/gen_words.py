"""Generate the plain (uncurated) word lists: one lowercase word per line, for
every length in a range.

Slices the dwyl ``english-words`` list (``words_alpha.txt``) into per-length
buckets: lowercase, alphabetic-only, de-duplicated, sorted. These are the weak,
uncurated lists (``data/words_N.txt``) used to bring up the solver and pin the
packing ceiling; ``gen_scored.py`` scores them with wordfreq. The crossword-native
``cw_N.txt`` lists come from ``gen_cw.py`` instead.

Run once to (re)generate ``data/words_N.txt`` for the chosen lengths. The source is
a moving upstream, so re-slicing an already-committed length may drift slightly;
regenerate a whole contiguous range together if you care about consistency.

    uv run scripts/gen_words.py                 # lengths 2..15 from the canonical URL
    uv run scripts/gen_words.py --min-len 6     # only add the longer lengths
    uv run scripts/gen_words.py --source path   # slice a local words_alpha.txt
"""

import argparse
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
SOURCE_URL = "https://raw.githubusercontent.com/dwyl/english-words/master/words_alpha.txt"


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
    ap.add_argument("--source", default=SOURCE_URL, help="local path or URL of words_alpha.txt")
    args = ap.parse_args()

    buckets: dict[int, set[str]] = {n: set() for n in range(args.min_len, args.max_len + 1)}
    for line in read_source(args.source).splitlines():
        w = line.strip().lower()
        if w.isalpha() and len(w) in buckets:
            buckets[len(w)].add(w)

    for n in range(args.min_len, args.max_len + 1):
        words = sorted(buckets[n])
        (DATA / f"words_{n}.txt").write_text("".join(f"{w}\n" for w in words))
        print(f"words_{n}.txt: {len(words)} words")


if __name__ == "__main__":
    main()
