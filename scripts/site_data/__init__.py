"""What every page module under this package gets: the store, a way to cut a
query file's stdout into its blocks, the constants the pages share, and the one
function every private-fleet head count goes through on its way to a reader.

A page module is `scripts/site_data/<page>.py` with one function,
`build(ch) -> dict`. The dict is embedded in `site/<page>.html` (underscores in
the module name become dashes in the file name) as the page's
`<script type="application/json" id="data">`, and its optional `"n"` sub-dict
fills the page's `<span data-n="key">` spans. `scripts/build_site_data.py` is
the driver; its guards are the NET, not the rule — see `private_count`.

There is no ClickHouse client library here for the same reason there is none in
notes/plot.py: the store is `clickhouse local --path data/ch` and the only way
in is `scripts/ch.sh`, which also honours CH_PATH. Query files are run ONE AT A
TIME — the store lock is exclusive — and cached, because five page modules
asking sql/60 for a different block of the same stdout should pay for it once
(sql/60 is 32 s).
"""
import functools
import re
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MEDIA = ROOT / "site" / "media"
CONTEXT = ROOT / "data" / "context"

# ---------------------------------------------------------------- constants

# The privacy floor (CLAUDE.md, docs/SITE.md § Privacy on the site,
# docs/dataset-card.md § Privacy rule). Every published head count of private
# boats is 0 or at least this; `private_count` below is how that is enforced.
K_FLOOR = 5

# The digit-group separator every page prints. ONE character, because the
# driver's guard has to be able to read a published string back as a number and
# a second separator is a second thing to forget (it had two, and index.py's
# thin space was not one of them — a "3 boats" string sailed straight through).
THIN = " "

# The six years the store holds whole or nearly so. 2022 and 2023 are two
# storm months each, 59 days, and a head count over 59 days is not a year's.
YEARS = [2015, 2018, 2021, 2024, 2025, 2026]

# ITU-R M.1371: a Class A transponder sends at most one position report every
# 2 s, so this many in a day is a property of the radio, not of the ship.
# sql/60 block 6 counts the vessel-days above it.
REPORT_SECONDS = 2
CAP_A = 86_400 // REPORT_SECONDS

# S9's floor: the number of private boats that covered a mile on the REFERENCE
# day, median over the storm's own dates. Below it a sailing ratio is a few
# dozen boats in a winter week and says nothing. Measured per storm it runs
# 15.5 … 203, then 506, 2 056, 2 096; the literal sits in the widest gap,
# exactly as notes/plot_ch04.py picks it. NOT the privacy floor — this one is
# about signal, K_FLOOR is about a person.
LEISURE_FLOOR = 250

# sql/50's window: 72 hours on each side of the storm's own dates.
WINDOW_DAYS = 3

# The reader never sees "ship_group". Five fleets, in the order they stop.
FLEET_NAME = {"fishing": "fishing boats", "leisure": "sailing boats",
              "other": "work boats", "passenger": "ferries",
              "cargo": "cargo ships"}
FLEET_KEY = {"fishing": "fishing", "leisure": "sailing", "other": "work",
             "passenger": "ferries", "cargo": "cargo"}
STOP_ORDER = ["fishing", "leisure", "other", "passenger", "cargo"]

# Column names for the query files more than one page reads. They live here
# because `blocks` tells result sets apart by WIDTH, so a name list and a width
# are two halves of one fact and three copies of it drift apart quietly.
W = ("storm start_day hour offset_h mobile ship_group heard moving_msgs msgs "
     "ref_hour ref_heard ref_moving_msgs ratio_moving ferry_crossings "
     "ref_ferry_crossings").split()
W_INT = "offset_h heard moving_msgs msgs ferry_crossings".split()
D1 = ("storm mobile ship_group day offset_d heard moved share_moved ref_day "
      "ref_heard ref_moved ref_share_moved").split()
D1_INT = "offset_d heard moved".split()
A1 = ("year window coverage loaded_days class_b_vessels class_b_leisure_vessels "
      "class_a_vessels class_a_vessels_5d leisure_per_class_a "
      "leisure_per_class_a_5d class_b_5d class_b_1d class_a_1d").split()
A1_INT = ("year loaded_days class_b_vessels class_b_leisure_vessels "
          "class_a_vessels class_a_vessels_5d class_b_5d class_b_1d "
          "class_a_1d").split()
A4 = ("year vessel_days median_msgs_per_vessel_day vessel_hours msgs "
      "msgs_per_vessel_hour vessel_days_moving median_dist_nm_moving "
      "danish_share german_share").split()
B6 = ("mon loaded_days vessel_days median_msgs mean_msgs p90_msgs p99_msgs "
      "max_msgs vd_over_cap share_over_cap max_over_cap_x dup_month").split()
B6_INT = "loaded_days vessel_days max_msgs vd_over_cap dup_month".split()
H1 = "year fleet visible_days hidden_days hidden_share vessels_with_hidden".split()
H1_INT = "year fleet visible_days hidden_days vessels_with_hidden".split()
H3 = "vessel year line kind island hidden_days dominant_hidden_type".split()
H3_INT = "year hidden_days".split()


# ------------------------------------------------------------ the hard rule

def private_count(x, what):
    """A head count of PRIVATE boats, on its way to a reader. Returns it, or
    stops the build.

    Every private-fleet head count a page module publishes or charts goes
    through here, at the point it is read out of the query — not at the point
    it is filed under a key. The driver's name-based guard in
    scripts/build_site_data.py is the second net and it can only catch a number
    whose key still carries the word: these modules rename `leisure` to
    `sailing` for the reader, and a count filed as `sailing_boats` used to
    reach the page unchecked. So the rule lives at the source and the net stays
    behind it.

    0 is allowed: nothing was seen, and nobody is identified by an absence.
    Anything from 1 to K_FLOOR - 1 is a number small enough to be a person's
    boat, and CLAUDE.md does not permit it to leave this machine.

    A share of the private fleet needs no floor and must not be passed here —
    0.37 would look like three boats. What a share MUST NOT do is stand next to
    its own sub-five numerator or denominator, which is a judgement no function
    can make for the module.
    """
    if x is None:
        raise SystemExit(
            f"{what}: a private-fleet count is None. Either the query lost the "
            f"row or the module is withholding it; a withheld count is left "
            f"out of the page entirely, never published as nothing.")
    if 0 < x < K_FLOOR:
        raise SystemExit(
            f"{what}: {x} boats — a published private-fleet count is 0 or at "
            f"least {K_FLOOR} (CLAUDE.md, docs/SITE.md § Privacy on the site). "
            f"Aggregate it further, or leave it off the page.")
    return x


def sp(x):
    """12345.6 -> '12 346', with the one separator the whole site prints."""
    return f"{round(x):,}".replace(",", THIN)


# ------------------------------------------------------------------ the store

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


class _Blocks(dict):
    def __init__(self, src):
        super().__init__()
        self.src = src

    def __missing__(self, width):
        raise SystemExit(
            f"{self.src}: no result set with {width} columns. The file emitted "
            f"widths {sorted(self)} — a block that gained or lost a column has "
            f"moved into another bucket, and the caller's column names no "
            f"longer line up with it. Fix the width here, not downstream.")


def blocks(rows, src="a query file"):
    """{column count: [rows]} — how a multi-statement query file is split.

    Every sql/ file that emits more than one result set is read this way by
    notes/plot_ch04.py and notes/plot_honesty.py: the blocks arrive one after
    another on one stdout and their widths tell them apart. Same trick, same
    fragility — but asking for a width that is not there is now a stop with the
    file name and the widths in it, where a defaultdict used to hand back an
    empty list and let the page draw nothing.
    """
    out = _Blocks(src)
    for r in rows:
        out.setdefault(len(r), []).append(r)
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


# ---------------------------------------------------- the storm onset, once

def smooth5(series, lo, hi):
    """A centred 5-hour mean over a dense offset range, as a percentage.

    One fleet's messages against the same hour a fortnight away is noisy — the
    denominator is one hour of one afternoon. Five hours is what chapter 04
    uses everywhere (notes/plot_ch04.py's `smooth`), so the site and the
    chapter draw the same line. A hole in the window breaks the line rather
    than bridging it.
    """
    out = []
    for o in range(lo, hi + 1):
        w = [series.get(o + d) for d in range(-2, 3)]
        if all(v is not None for v in w):
            out.append([o, round(100 * sum(w) / 5, 1)])
    return out


def halves_at(series, ndays):
    """The hour a fleet stops: the first offset at which its 5-hour mean falls
    below HALF its own pre-window median (offsets -72 … -25), searched from -24
    onward. None if it never does.

    The normalisation is the point. A fleet that idles at 40 % of normal all
    week has not stopped, and a fixed threshold would say it stopped three days
    early. Same definition as notes/plot_ch04.py's `stops_at`, which is what
    finding 40 is built on.
    """
    base = [v for o, v in series.items() if -72 <= o <= -25 and v is not None]
    if not base or statistics.median(base) <= 0:
        return None
    half = 50 * statistics.median(base)
    for o, v in smooth5(series, -24, 24 * ndays - 1):
        if v < half:
            return o
    return None


def hourly_series(rows):
    """sql/50's rows -> {(storm, ship_group): {offset_h: ratio_moving}}.

    The private fleet is Class B and every public fleet is Class A. Keying on
    ship_group alone would fold the hundred-odd Class A yachts into the sailing
    line and overwrite it.
    """
    series = defaultdict(dict)
    for r in rows:
        if r["mobile"] == ("Class B" if r["ship_group"] == "leisure" else "Class A"):
            series[(r["storm"], r["ship_group"])][r["offset_h"]] = r["ratio_moving"]
    return series


def sailing_storms(day_rows, ndays):
    """The storms whose private fleet is big enough to say anything about:
    LEISURE_FLOOR boats covering a mile on the REFERENCE day, median over the
    storm's own dates. Read off sql/52 block 1, which is where S9 measured it.
    """
    ref_moved = defaultdict(list)
    for r in day_rows:
        if (r["mobile"] == "Class B" and r["ship_group"] == "leisure"
                and r["ref_moved"] is not None
                and 0 <= r["offset_d"] < ndays.get(r["storm"], 0)):
            ref_moved[r["storm"]].append(r["ref_moved"])
    return sorted(s for s, v in ref_moved.items()
                  if statistics.median(v) >= LEISURE_FLOOR)


def onset(series, ndays, sailing_ok):
    """{ship_group: [hour, …]} — the hour each fleet's movement halves, over
    every observed storm.

    ONE definition, used by site/index.html (I5) and site/storms.html alike.
    They used to compute it twice and disagree on screen: index filtered the
    sailing fleet to the storms that cleared LEISURE_FLOOR and said "three
    hours before", storms.html pooled all fourteen — winter gales included,
    which the same module excludes everywhere else — and said "about six hours
    in". The filter belongs to the measure, so it lives with it.
    """
    out = defaultdict(list)
    for storm, n in sorted(ndays.items()):
        if not n:
            continue
        for g in STOP_ORDER:
            if g == "leisure" and storm not in sailing_ok:
                continue
            h = halves_at(series[(storm, g)], n)
            if h is not None:
                out[g].append(h)
    return out


def media_key(storm):
    """'Dagmar·Egon' -> 'dagmaregon', the name scripts/render_storm.py files
    its clip under."""
    return re.sub(r"[^a-z]", "", storm.lower())


def clips(storms):
    """{clip key: storm name} for the animations that are on disk AND in the
    archive, in file-name order.

    ONE discovery, for both pages. The three clips used to be known in four
    places — the keys in scripts/render_storm.py, a glob in index.py, a CLIPS
    literal in storms.py and three hard-coded <script> tags in storms.html —
    and storms.py inverted the key with `k.capitalize()`, which turns
    'dagmaregon' into 'Dagmaregon' and finds no storm at all. The directory is
    the fact; everything else reads it.
    """
    keyed = {media_key(s): s for s in storms}
    have = {f.stem[len("storm-"):]: None
            for f in sorted(MEDIA.glob("storm-*.js"))}
    out = {k: keyed[k] for k in have if k in keyed}
    assert out, (f"no clip in {MEDIA} matches a storm in the archive: "
                 f"{sorted(have)} against {sorted(keyed)}")
    return out


def storms_named():
    """How many storms the weather service has named since 2013 — the row count
    of data/context/storms.csv, which is the list itself, rather than a literal
    on the page that nobody updates when a storm is added."""
    rows = CONTEXT.joinpath("storms.csv").read_text().strip().splitlines()
    assert rows[0].startswith("name,"), "storms.csv no longer starts with a header"
    return len(rows) - 1


def onset_words(hours):
    """A pooled onset -> (how many hours, the phrase that goes after it).

    The direction is DATA. It used to be a word typed into two sentences next
    to an abs() in the build, which is how one page came to say "before" and
    the other "in" about the same fleet.
    """
    h = round(statistics.median(hours))
    return (str(abs(h)),
            "before the storm's own first midnight" if h < 0
            else "into the storm's own date")
