"""puzzledesk.app -- the application layer: use-case services and the ports they
need from the outside world.

A *service* orchestrates the pure core (load a lexicon, run an engine, validate,
shape a result) to satisfy one user-facing use-case -- "generate N minis",
"generate N blocked minis from a black-cell count". Services depend only on the
core and on *ports* (:mod:`puzzledesk.app.ports`) -- interfaces the infrastructure
must satisfy -- never on a concrete adapter. That inversion is what lets a test
drive a service with an in-memory lexicon and a recording rng, and it is enforced
by import-linter (``app`` may import ``core`` but not ``adapters``/``bootstrap``/
``cli``).

Services return structured results (:mod:`puzzledesk.app.results`); turning those
into bytes on a stream is the job of ``cli`` + the ``Writer`` adapter, not of the
service. Benchmark/demo drivers (ceiling, compare, ground-truth checks, ...) are
NOT services -- they are measurement scaffolds that live in ``cli`` and drive the
core engines directly through the same injected adapters.
"""
