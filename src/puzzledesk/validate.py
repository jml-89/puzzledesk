"""The acceptance test -- the feedback signal the rest of the system optimises
against.

A grid is acceptable iff EVERY across word and EVERY down word clears the bar.
That is a bottleneck test on the weakest word, not an average: one obscure entry
fails the whole grid, exactly as it would for a human solver.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .square import DoubleSquare


@dataclass
class Verdict:
    ok: bool
    min_score: float          # score of the weakest word (the bottleneck)
    weakest: tuple[str, float]
    words: list[tuple[str, float]]  # every across+down word with its score

    def __str__(self) -> str:
        tag = "ACCEPT" if self.ok else "REJECT"
        return f"{tag} min={self.min_score:.2f} weakest={self.weakest[0]!r}"


def score_of(lex, word: str) -> float:
    return lex.score_map.get(word, 0.0)


def validate(sq: DoubleSquare, state: np.ndarray, threshold: float) -> Verdict:
    across = [(sq.rows.words[i], float(sq.rows.scores[i])) for i in state]
    down = [(w, score_of(sq.cols, w)) for w in sq.column_strings(state)]
    words = across + down
    weakest = min(words, key=lambda ws: ws[1])
    return Verdict(
        ok=weakest[1] >= threshold,
        min_score=weakest[1],
        weakest=weakest,
        words=words,
    )
