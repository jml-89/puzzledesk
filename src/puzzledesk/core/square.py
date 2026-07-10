"""Double word square: representation and energy.

State is just the N across (row) words, held as indices into a row lexicon.
The down words are *induced* by reading the grid column-wise. The grid is valid
-- a genuine double word square -- exactly when every induced column is itself a
real word.

energy(state) = number of columns that are NOT valid words.  Zero == solved.
"""

from __future__ import annotations

import numpy as np

from puzzledesk.core.lexicon import Lexicon, decode


class DoubleSquare:
    def __init__(self, rows: Lexicon, cols: Lexicon | None = None) -> None:
        # Across and down may draw from different lexicons; default to the same.
        self.rows = rows
        self.cols = cols if cols is not None else rows
        if self.rows.n != self.cols.n:
            raise ValueError("row and column word lengths must match")
        self.n = rows.n

    def grid(self, state: np.ndarray) -> np.ndarray:
        """(N, N) letter-index grid for a state (array of N row-word indices)."""
        return self.rows.letters[state]

    def column_strings(self, state: np.ndarray) -> list[str]:
        g = self.grid(state)
        return [decode(g[:, j]) for j in range(self.n)]

    def invalid_columns(self, state: np.ndarray) -> list[int]:
        g = self.grid(state)
        return [j for j in range(self.n) if decode(g[:, j]) not in self.cols.wordset]

    def energy(self, state: np.ndarray) -> int:
        return len(self.invalid_columns(state))

    def render(self, state: np.ndarray) -> str:
        g = self.grid(state)
        return "\n".join(" ".join(chr(int(c) + 97) for c in g[i]) for i in range(self.n))
