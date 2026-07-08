"""Bootstrap configuration -- the knobs the composition root reads before it wires
anything. Kept tiny and explicit; there is no config file, just values with sane
defaults an entry point can override.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

# config.py -> bootstrap -> puzzledesk -> src -> <repo root>; data/ sits there.
_REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class Config:
    """Where to read word lists and where to write output.

    ``stream`` is left as ``None`` to mean "stdout, resolved at wiring time" so the
    default is not bound to whatever ``sys.stdout`` happened to be at import.
    """

    data_dir: Path
    stream: TextIO | None = None
    clue_model: str = "claude-opus-4-8"  # the Claude model the clue adapter calls

    @classmethod
    def default(cls) -> Config:
        return cls(data_dir=_REPO_ROOT / "data")
