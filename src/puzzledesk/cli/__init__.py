"""puzzledesk.cli -- the "front": thin entry points over the composition root.

Each module here is one program a user runs. The shape is always the same: parse
argv, :func:`~puzzledesk.bootstrap.build`, run a service (or, for the benchmark and
demo drivers, drive the core engines directly through the container's injected
adapters), and present via a ``Writer``. No generation logic lives here -- only
argument parsing and formatting.

Two kinds of program share this directory (the tool/benchmark split CLAUDE.md
calls for, honoured by intent):

  * **tools** -- ``mini``, ``generate``, ``blackcells``: produce crossword
    artifacts, every emitted grid distinct and above the bar.
  * **benchmarks/demos** -- ``bench``, ``ceiling``, ``frontier``, ``compare``,
    ``samplers``, ``quality``, ``demo``: measure or check; they may be slow and
    print numbers, not grids. ``gen_scored`` is a data-regeneration maintenance
    tool (needs the optional ``wordfreq`` extra).

``cli`` is the top of the import stack: it may import every lower layer; nothing
imports it.
"""
