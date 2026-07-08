"""puzzledesk.core -- the pure kernel.

No I/O, no argv, no stdout, no wall-clock, no unseeded randomness. Everything
here is deterministic given its inputs (a ``(lists, seed)`` pair reproduces a
result exactly) and fully typed. The two grid models, the engines, the lexicon,
and the acceptance test live here, plus the driven port the engines need from the
outside world -- :class:`~puzzledesk.core.rng.Rng` (randomness is the one impure
dependency, so it is injected rather than constructed here).

Import rule (enforced by import-linter): ``core`` imports nothing from ``app``,
``adapters``, ``bootstrap`` or ``cli``. It is the bottom of the stack.
"""
