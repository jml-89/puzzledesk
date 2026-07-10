"""Generate scored word lists: 'word<space>zipf' per line, for words above a
mild frequency floor (drops pure junk like 'aalii'=0.0, keeps everything with a
real usage signal). The Zipf score is what `filtered(bar)` thresholds on.

Reads the plain ``data/words_N.txt`` lists (from ``gen_words.py``) and scores them.
Run once to (re)generate ``data/scored_N.txt`` for the chosen lengths; the solvers
read only these files, not wordfreq itself.

    uv run --extra scoring scripts/gen_scored.py               # lengths 2..15
    uv run --extra scoring scripts/gen_scored.py --min-len 6   # only the longer lengths
"""

import argparse
from pathlib import Path

from wordfreq import zipf_frequency

DATA = Path(__file__).resolve().parent.parent / "data"
FLOOR = 2.0  # drop words with no meaningful usage signal


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-len", type=int, default=2)
    ap.add_argument("--max-len", type=int, default=15)
    args = ap.parse_args()

    for n in range(args.min_len, args.max_len + 1):
        src = DATA / f"words_{n}.txt"
        if not src.exists():
            print(f"words_{n}.txt: missing, skipped (run gen_words.py first)")
            continue
        words = [w.strip() for w in src.read_text().split()]
        scored = [(w, zipf_frequency(w, "en")) for w in words]
        scored = [(w, s) for w, s in scored if s >= FLOOR]
        scored.sort(key=lambda ws: (-ws[1], ws[0]))
        (DATA / f"scored_{n}.txt").write_text("".join(f"{w} {s:.2f}\n" for w, s in scored))
        print(f"scored_{n}.txt: {len(scored)} words (floor zipf>={FLOOR})")


if __name__ == "__main__":
    main()
