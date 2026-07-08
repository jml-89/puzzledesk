"""Blocked grid: the slot/intersection graph that replaces the induced-column
trick once black cells exist.

In the fully-checked square, state was the N across words and the down words were
*induced* by reading whole columns -- validity was "is this column a word". Black
cells break that: the grid is no longer N rows x N columns of one word each, but a
set of **slots** (maximal white runs, across and down) that **cross** at shared
cells. There is no longer a single "column" to read; a down entry may start
partway down the grid and stop at a block.

So we parse the block pattern into slots and record, for every white cell, which
across slot and which down slot pass through it. That crossing structure is the
whole constraint: two entries that cross must agree on their shared letter. Fill
(fill.py) is then a CSP over slots, not a scan of columns.

Template format: one string per row, ``.`` = white (fillable), ``#`` = black.
"""

from __future__ import annotations

from dataclasses import dataclass, field

BLOCK = "#"
WHITE = "."


@dataclass
class Slot:
    id: int
    direction: str  # "A" (across) or "D" (down)
    cells: list[tuple[int, int]]
    number: int = 0  # the clue number at the slot's start cell

    @property
    def length(self) -> int:
        return len(self.cells)


@dataclass
class BlockedGrid:
    rows: int
    cols: int
    block: list[list[bool]]  # block[r][c] == True if black
    slots: list[Slot] = field(default_factory=list)
    # (r, c) -> {"A": slot_id, "D": slot_id} for the slots through that cell.
    cell_slots: dict[tuple[int, int], dict[str, int]] = field(default_factory=dict)
    orphans: list[tuple[int, int]] = field(default_factory=list)

    @classmethod
    def parse(cls, template: str | list[str], min_len: int = 3) -> BlockedGrid:
        rowstrs = template.split() if isinstance(template, str) else list(template)
        rowstrs = [r.strip() for r in rowstrs if r.strip()]
        R = len(rowstrs)
        C = len(rowstrs[0])
        if any(len(r) != C for r in rowstrs):
            raise ValueError("all template rows must have equal width")
        block = [[ch == BLOCK for ch in row] for row in rowstrs]
        g = cls(rows=R, cols=C, block=block)
        g._build(min_len)
        return g

    def _runs(self, cells: list[tuple[int, int]], min_len: int) -> list[list[tuple[int, int]]]:
        """Split a line of cells into maximal white runs of length >= min_len."""
        runs: list[list[tuple[int, int]]] = []
        cur: list[tuple[int, int]] = []
        for r, c in cells:
            if self.block[r][c]:
                if len(cur) >= min_len:
                    runs.append(cur)
                cur = []
            else:
                cur.append((r, c))
        if len(cur) >= min_len:
            runs.append(cur)
        return runs

    def _build(self, min_len: int) -> None:
        sid = 0
        for r in range(self.rows):
            for run in self._runs([(r, c) for c in range(self.cols)], min_len):
                self.slots.append(Slot(sid, "A", run))
                sid += 1
        for c in range(self.cols):
            for run in self._runs([(r, c) for r in range(self.rows)], min_len):
                self.slots.append(Slot(sid, "D", run))
                sid += 1
        for s in self.slots:
            for r, c in s.cells:
                self.cell_slots.setdefault((r, c), {})[s.direction] = s.id
        # White cells touched by no slot (a run shorter than min_len): unchecked /
        # unfillable. A well-formed American grid has none.
        self.orphans = [
            (r, c)
            for r in range(self.rows)
            for c in range(self.cols)
            if not self.block[r][c] and (r, c) not in self.cell_slots
        ]
        self._number()

    def _number(self) -> None:
        """Assign the conventional clue numbers (left-to-right, top-to-bottom;
        a cell starts a number if it begins an across or a down slot)."""
        starts = {s.cells[0]: s for s in self.slots}
        num = 0
        seen: dict[tuple[int, int], int] = {}
        for r in range(self.rows):
            for c in range(self.cols):
                if (r, c) in starts:
                    if (r, c) not in seen:
                        num += 1
                        seen[(r, c)] = num
                    starts_here = [s for s in self.slots if s.cells[0] == (r, c)]
                    for s in starts_here:
                        s.number = seen[(r, c)]

    def lengths_needed(self) -> set[int]:
        return {s.length for s in self.slots}

    def crossings(self) -> list[tuple[int, int]]:
        """Unique (across_slot_id, down_slot_id) pairs that share a cell."""
        pairs = set()
        for ds in self.cell_slots.values():
            if "A" in ds and "D" in ds:
                pairs.add((ds["A"], ds["D"]))
        return sorted(pairs)

    def render(self, letters: dict[tuple[int, int], str] | None = None) -> str:
        letters = letters or {}
        out = []
        for r in range(self.rows):
            row = []
            for c in range(self.cols):
                if self.block[r][c]:
                    row.append("#")
                else:
                    row.append(letters.get((r, c), ".").upper())
            out.append(" ".join(row))
        return "\n".join(out)
