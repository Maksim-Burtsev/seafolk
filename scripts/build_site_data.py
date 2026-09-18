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
(`day_clocks.py` -> `site/day-clocks.html`), which is the whole of the module
discovery — no registry, no config.

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

 (b) A PRIVATE-FLEET BOAT COUNT IS >= 5 OR THE BUILD STOPS. Any number under a
     key path containing `leisure` or `small_boat` must be 0 or >= 5. The rule
     is the hard one in CLAUDE.md and docs/SITE.md, and it is checked here
     rather than in a page module because a page module is exactly where it
     would be forgotten. It follows that a SHARE of the private fleet is never
     filed under such a key — 0.37 would trip the guard, correctly, because
     nothing here can tell a share from a head count by looking at it. Page
     modules name a private-fleet share after what the reader is told it is
     (`sailing`, `flags.german`), and only head counts carry the word.

 (c) A SPAN WITH NO NUMBER FAILS. A page that says `<span data-n="fleet_2026">`
     and gets nothing would render an empty gap in a sentence, and an empty gap
     is how a hand-typed number gets added back later.
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


def as_number(v):
    """The number in a leaf, whether it arrived as one or as a display string
    ("22 773", "1.9 %"). None when there is no number in it."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    m = re.fullmatch(r"([\d  ]+(?:\.\d+)?)\s*%?", str(v))
    return float(m.group(1).replace(" ", "").replace(" ", "")) if m else None


def guard(page, data):
    """Guards (a) and (b) over one page's dict. Raises SystemExit on a breach."""
    private = ("leisure", "small_boat")
    for path, v in walk(data):
        if v is None:
            continue
        num = as_number(v)
        if (num is not None and 0 < num < 5
                and any(w in path.lower() for w in private)):
            sys.exit(f"{page}: {path} = {v} — a private-fleet count under five "
                     f"boats may not be published (CLAUDE.md, docs/SITE.md). "
                     f"A share does not belong under this key name; see the "
                     f"guard note in this file.")
        if NINE.search(str(v)):
            sys.exit(f"{page}: {path} = {v!r} holds a nine-digit integer — that "
                     f"is the shape of an MMSI. Publish it in millions or not "
                     f"at all.")


def fill(page, data):
    """Rewrite the page's JSON block and its data-n spans. Returns the ledger."""
    src = page.read_text()
    if "<script type=\"application/json\" id=\"data\">" not in src:
        sys.exit(f"{page}: no <script type=\"application/json\" id=\"data\"> block")
    blob = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    out = BLOCK.sub(lambda m: m.group(1) + blob + m.group(2), src)

    n, used = data.get("n", {}), []

    def span(m):
        key = m.group(2)
        if key not in n:
            sys.exit(f"{page}: <span data-n=\"{key}\"> has no number. "
                     f"scripts/site_data/{page.stem.replace('-', '_')}.py "
                     f"produced: {', '.join(sorted(n)) or '(nothing)'}")
        used.append(key)
        return m.group(1) + str(n[key]) + m.group(4)

    out = SPAN.sub(span, out)
    page.write_text(out)
    return blob, used


def main(only):
    pages = sorted(p for p in (ROOT / "scripts" / "site_data").glob("*.py")
                   if not p.name.startswith("_"))
    if only:
        pages = [p for p in pages if p.stem in only]
        missing = set(only) - {p.stem for p in pages}
        if missing:
            sys.exit(f"no module for: {', '.join(sorted(missing))}")
    for mod in pages:
        page = ROOT / "site" / f"{mod.stem.replace('_', '-')}.html"
        if not page.exists():
            # Five sessions write page modules into this one package in
            # parallel, and a module lands before its page does. Asking for
            # that page by name is an error; sweeping the directory is not.
            if only:
                sys.exit(f"{mod.name} builds {page}, which does not exist")
            print(f"  (skipping {mod.name}: {page.name} does not exist yet)")
            continue
        data = importlib.import_module(f"site_data.{mod.stem}").build(ch)
        guard(page, data)
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
