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
    solve_model: str = "claude-opus-4-8"  # the Claude model the solver adapter calls (D24)
    # How the solver model exposes thinking. Model families differ (verified live): Opus 4.8
    # uses "adaptive" (+ effort); Haiku 4.5 uses "enabled" (+ a token budget); each 400s on
    # the other. "off" disables thinking. This is what lets a weaker model be pitted on the
    # same grid so reasoning-spend grades difficulty (D24).
    solve_thinking: str = "adaptive"  # "adaptive" | "enabled" | "off"
    solve_effort: str = "high"  # adaptive-thinking effort (output_config.effort)
    solve_thinking_budget: int = 4096  # token budget for "enabled" thinking
    # Total output budget per solver turn. MUST comfortably exceed the thinking spend or the
    # thinking pass starves the answer: on a hard mini, adaptive thinking alone can consume an
    # 8k budget and the model never emits its move -- the harness then loops/fails on nothing
    # (a measurement artifact, not a solver wall; caught by reading the transcripts). 32k gives
    # ample headroom over any single-mini thinking spend seen so far.
    solve_max_tokens: int = 32000
    solve_max_turns: int = 12  # the solver harness's default turn budget (a budget, not a proof)
    # Which env var the composition root reads the clue API key from before injecting
    # the resolved value into the adapter. We deliberately name an *off-normal* var:
    # the standard ``ANTHROPIC_API_KEY`` is auto-detected by other tooling in our
    # environments and that has bitten us, so the key lives under a name nothing else
    # claims. ``None`` (or a var set to nothing) = inject no key, so the adapter defers
    # to the SDK's own resolution (its own ``ANTHROPIC_API_KEY`` / ``ant auth login``
    # profile) -- normal setups still work.
    clue_api_key_env: str | None = "ANTHROPIC_API_KEY_TWO"

    @classmethod
    def default(cls) -> Config:
        return cls(data_dir=_REPO_ROOT / "data")
