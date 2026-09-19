#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Fill every page under site/ with numbers computed from the store.

    scripts/build_site_data.py                    # read data/ch
    CH_PATH=data/ch_s12a scripts/build_site_data.py   # read an APFS clone
    scripts/build_site_data.py index season       # only these pages

One module per page: `scripts/site_data/<page>.py` exposing `build(ch) -> dict`.
The module name maps to `site/<page>.html` with underscores turned into dashes
(`site_flags.py` -> `site/site-flags.html`), which is the whole of the module
discovery — no registry, no config. A module with no page is an error, and so
is a page with data-n spans and no module: every page on this site is built.

What the driver does with the returned dict:
  * writes it, as JSON, into the page's <script type="application/json" id="data">
  * writes dict["n"][key] into every <span data-n="key"> in the page
  * fails if a page has a span whose key the module did not produce
  * runs the guards below over every value, wherever it sits in the dict
  * prints the ledger: every number that reached a reader, and where from

The pages carry their data inline because they must open by double-click from
file:// — a page that fetches a sibling .json only works when it is served.

THE GUARDS, and why each one exists rather than being left to review:

 (a) NO NINE-DIGIT INTEGER, anywhere in the JSON or the spans. An MMSI is
     exactly nine digits, and site/ is an export (CLAUDE.md: aggregates only
     for private vessels). This also catches a raw message total, which is the
     other thing that reaches nine digits in this store; those are published as
     millions or not at all, the way notes/plot_honesty.py does it.

 (b) A PRIVATE-FLEET BOAT COUNT IS >= 5 OR THE BUILD STOPS — as a NET, under
     a second guard. The rule itself is `site_data.private_count`, called by
     the page modules where each count is read, because this one can only see
     a key NAME and the modules rename the private fleet to `sailing` for the
     reader: `{"block": {"sailing_boats": 3}}` used to build green. So the
     names here are wide (leisure, small_boat, sailing, private, marina) and
     the check is on INTEGER-valued leaves only — an int, or a string that is
     an integer once its separators and its trailing unit word come off.
     Shares are floats and are skipped: 0.37 is not three boats, and a module
     that files a share under one of those names is not thereby publishing a
     head count. What still has to be read by a person is a share printed NEXT
     TO its own sub-five numerator; no guard can see that.

 (c) A SPAN WITH NO NUMBER FAILS, and so does a NUMBER THAT IS NOT ONE.
     `<span data-n="fleet_2026">` with nothing behind it renders an empty gap
     in a sentence, and an empty gap is how a hand-typed number gets added
     back later. None is worse: it renders the word "None" in the middle of a
     sentence, which is what happened to a withheld private count. A module
     that withholds a number leaves the key out of "n" and the span out of the
     page.
"""
import importlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from site_data import ROOT, ch  # noqa: E402

BLOCK = re.compile(r'(<script type="application/json" id="data">).*?(</script>)', re.S)
SPAN = re.compile(r'(<span data-n="([^"]+)"[^>]*>)(.*?)(</span>)', re.S)
NINE = re.compile(r"\b\d{9}\b")

# Guard (b)'s key names. Every word the pages use for the private fleet, not
# only the two the schema uses: the modules publish `sailing`, `small_boats`
# and `marina_boats`, and a guard keyed on `leisure` alone sees none of them.
PRIVATE = ("leisure", "small_boat", "sailing", "private", "marina")

# The allow-list, as key paths. Guard (b) can only read a key NAME, so it
# cannot tell a head count of boats from a count of storms that happens to sit
# under a key with the word "sailing" in it. Every exemption is written out
# here with what the number actually counts; nothing gets out of this guard by
# accident, and a new entry is a thing a reviewer reads.
EXEMPT = {
    # how.html H1 is a DRAWING of the >= 5 rule: seven hexagons holding
    # invented counts of 1 to 12 boats, so a reader can see which of them the
    # floor deletes. No fleet behind them; the figure's caption says so.
    r"picture\.rows\[\d+\]\[\d+\]": "invented boats in the drawing of the rule",
    # index.html I4's sailing line is [day offset, share of the fleet, null] —
    # the third slot is a head count and it is DELIBERATELY withheld for this
    # one fleet. What trips the guard is the day offset, which runs -3 … +3.
    r"storms\.panels\.[^.]+\.lines\.sailing\[\d+\]\[\d+\]":
        "a day offset and a share; the count in this line is withheld",
    # storms, not boats: how many of the fourteen had a private fleet big
    # enough to draw at all (site_data.sailing_storms).
    r"n\.sailing_storms": "a count of storms",
    # hours, not boats: where the pooled sailing onset falls (site_data.onset).
    r"n\.sailing_hours": "a count of hours",
    # per cent of the boats heard that covered a mile — a share, printed whole.
    r"n\.storm_sailing_before": "a percentage",
    r"n\.storm_sailing_day": "a percentage",
}
EXEMPT_RE = re.compile("|".join(f"(?:{p})" for p in EXEMPT)).fullmatch

# A published number's separators. ONE of them is site_data.THIN and the rest
# are here because a hand-edited page or a stray nbsp must not let a count slip
# past as "unparseable".
SEPARATORS = str.maketrans("", "", "    ,")
UNIT_WORD = re.compile(r"[A-Za-z%][A-Za-z %]*$")


def walk(value, path=""):
    """(key path, value) for every leaf in a nested dict/list."""
    if isinstance(value, dict):
        for k, v in value.items():
            yield from walk(v, f"{path}.{k}" if path else str(k))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from walk(v, f"{path}[{i}]")
    else:
        yield path, value


def as_int(v):
    """The INTEGER a leaf publishes, or None if it does not publish one.

    An int is one. A string is one if it is all digits once the group
    separators and a trailing unit word are removed ("3 boats", "22 773",
    "1 088 departures"). A float is never one: every float on this site is a
    share or a rate, and "0.37" must not be read as a head count of nothing.
    """
    if isinstance(v, bool) or isinstance(v, float):
        return None
    if isinstance(v, int):
        return v
    if not isinstance(v, str):
        return None
    s = UNIT_WORD.sub("", v.strip()).strip().translate(SEPARATORS)
    return int(s) if s.isdigit() else None


def guard(page, data):
    """Guards (a), (b) and the "n" half of (c) over one page's dict.
    Raises SystemExit on a breach."""
    for key, v in (data.get("n") or {}).items():
        if v is None or str(v).strip().lower() in ("none", "nan"):
            raise SystemExit(
                f"{page}: n[{key!r}] is {v!r}. That reaches the reader as the "
                f"word in the middle of a sentence. A number the module is "
                f"withholding is left out of \"n\" and its span off the page.")

    for path, v in walk(data):
        if v is None:
            continue
        num = as_int(v)
        if (num is not None and 0 < num < 5
                and any(w in path.lower() for w in PRIVATE)
                and not EXEMPT_RE(path)):
            raise SystemExit(
                f"{page}: {path} = {v} — a private-fleet count under five "
                f"boats may not be published (CLAUDE.md, docs/SITE.md). Call "
                f"site_data.private_count() where this number is read, so the "
                f"module stops rather than the net.")
        if NINE.search(str(v)):
            raise SystemExit(
                f"{page}: {path} = {v!r} holds a nine-digit integer — that is "
                f"the shape of an MMSI. Publish it in millions or not at all.")


def fill(page, data):
    """Rewrite the page's JSON block and its data-n spans. Returns the ledger."""
    src = page.read_text()
    if "<script type=\"application/json\" id=\"data\">" not in src:
        raise SystemExit(f"{page}: no <script type=\"application/json\" id=\"data\"> block")
    blob = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    out = BLOCK.sub(lambda m: m.group(1) + blob + m.group(2), src)

    n, used = data.get("n", {}), []

    def span(m):
        key = m.group(2)
        if key not in n:
            raise SystemExit(
                f"{page}: <span data-n=\"{key}\"> has no number. "
                f"scripts/site_data/{page.stem.replace('-', '_')}.py "
                f"produced: {', '.join(sorted(n)) or '(nothing)'}")
        used.append(key)
        return m.group(1) + str(n[key]) + m.group(4)

    out = SPAN.sub(span, out)
    page.write_text(out)
    return blob, used


def main(only):
    mods = sorted(p for p in (ROOT / "scripts" / "site_data").glob("*.py")
                  if not p.name.startswith("_"))
    if only:
        mods = [p for p in mods if p.stem in only]
        missing = set(only) - {p.stem for p in mods}
        if missing:
            sys.exit(f"no module for: {', '.join(sorted(missing))}")

    pages = {}
    for mod in mods:
        page = ROOT / "site" / f"{mod.stem.replace('_', '-')}.html"
        # Every module builds a page. The skip that used to sit here was
        # scaffolding for five sessions writing into this package in parallel,
        # and it outlived them: a module whose page had been renamed or deleted
        # printed one line and the build stayed green.
        if not page.exists():
            sys.exit(f"{mod.name} builds {page.relative_to(ROOT)}, which does "
                     f"not exist — rename one of the two, or delete the module")
        pages[page] = mod

    # …and every page that carries numbers has a module. A page nobody builds
    # keeps whatever was last written into it, by the build or by hand.
    if not only:
        for page in sorted(ROOT.glob("site/*.html")):
            if page not in pages and re.search(r'<span data-n="', page.read_text()):
                sys.exit(f"{page.relative_to(ROOT)} has data-n spans but no "
                         f"scripts/site_data/{page.stem.replace('-', '_')}.py "
                         f"— its numbers are whatever was last put there")

    for page, mod in pages.items():
        data = importlib.import_module(f"site_data.{mod.stem}").build(ch)
        guard(page.relative_to(ROOT), data)
        blob, used = fill(page, data)

        print(f"\n=== {page.relative_to(ROOT)} — {len(blob)} bytes inline, "
              f"{len(used)} spans ===")
        for key, v in data.items():
            if key != "n":
                print(f"  [{key}] {len(list(walk(v)))} values")
        for key, v in sorted(data.get("n", {}).items()):
            print(f"  {'* ' if key in used else '  '}{key:34s} {v}")
        unused = sorted(set(data.get("n", {})) - set(used))
        if unused:
            print(f"  (not on the page yet: {', '.join(unused)})")


if __name__ == "__main__":
    main(sys.argv[1:])
