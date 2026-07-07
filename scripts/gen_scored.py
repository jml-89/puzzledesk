"""Generate scored word lists: 'word<space>zipf' per line, for words above a
mild frequency floor (drops pure junk like 'aalii'=0.0, keeps everything with a
real usage signal). Quality is then a soft term in the energy, not a hard filter.

Run once to (re)generate data/scored_N.txt; the sampler needs only these files,
not wordfreq itself.
"""

from pathlib import Path

from wordfreq import zipf_frequency

DATA = Path(__file__).resolve().parent.parent / "data"
FLOOR = 2.0  # drop words with no meaningful usage signal

for n in (2, 3, 4, 5):
    words = [w.strip() for w in (DATA / f"words_{n}.txt").read_text().split()]
    scored = [(w, zipf_frequency(w, "en")) for w in words]
    scored = [(w, s) for w, s in scored if s >= FLOOR]
    scored.sort(key=lambda ws: (-ws[1], ws[0]))
    (DATA / f"scored_{n}.txt").write_text("".join(f"{w} {s:.2f}\n" for w, s in scored))
    print(f"scored_{n}.txt: {len(scored)} words (floor zipf>={FLOOR})")
