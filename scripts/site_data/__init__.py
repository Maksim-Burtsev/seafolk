"""What every page module under this package gets: the store, and a way to cut
a query file's stdout into its blocks.

A page module is `scripts/site_data/<page>.py` with one function,
`build(ch) -> dict`. The dict is embedded in `site/<page>.html` (underscores in
the module name become dashes in the file name) as the page's
`<script type="application/json" id="data">`, and its optional `"n"` sub-dict
fills the page's `<span data-n="key">` spans. `scripts/build_site_data.py` is
the driver; it, not the module, enforces the privacy and nine-digit guards.

There is no ClickHouse client library here for the same reason there is none in
notes/plot.py: the store is `clickhouse local --path data/ch` and the only way
in is `scripts/ch.sh`, which also honours CH_PATH. Query files are run ONE AT A
TIME — the store lock is exclusive — and cached, because five page modules
asking sql/60 for a different block of the same stdout should pay for it once
(sql/60 is 32 s).
"""
import functools
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@functools.lru_cache(maxsize=None)
def ch(*args):
    """Run `scripts/ch.sh <args>` and return its stdout as a tuple of rows.

    `ch("50_storm_window.sql")` runs the file in sql/; `ch("-q", "SELECT 1")`
    runs one query. Every field is a string, exactly as the TSV carries it —
    `\\N` is a real NULL and stays a string here, so a parser has to decide.
    """
    cmd = [str(ROOT / "scripts" / "ch.sh")]
    cmd += list(args) if args[0].startswith("-") else \
        [str(ROOT / "sql" / args[0]), *args[1:]]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        sys.exit(f"{args[0]} failed (exit {p.returncode}):\n{p.stderr.strip()}\n"
                 "  'Cannot lock file .../status' means another reader holds the\n"
                 "  store: run against your own APFS clone (CH_PATH=data/ch_<name>).")
    out = tuple(tuple(line.split("\t")) for line in p.stdout.splitlines() if line)
    assert out, f"{args[0]} returned no rows"
    return out


def blocks(rows):
    """{column count: [rows]} — how a multi-statement query file is split.

    Every sql/ file that emits more than one result set is read this way by
    notes/plot_ch04.py and notes/plot_honesty.py: the blocks arrive one after
    another on one stdout and their widths tell them apart. Same trick, same
    fragility — a block that changes its column count moves, loudly, into
    another bucket and the caller's `dict(zip(NAMES, row))` stops lining up.
    """
    out = defaultdict(list)
    for r in rows:
        out[len(r)].append(r)
    return out


def typed(names, row, ints=()):
    """One TSV row -> a dict. `ints` are cast to int, `\\N` becomes None, and
    anything else that looks like a number becomes a float."""
    d = {}
    for k, v in zip(names, row):
        if v == "\\N":
            d[k] = None
        elif k in ints:
            d[k] = int(v)
        else:
            try:
                d[k] = float(v)
            except ValueError:
                d[k] = v
    return d
