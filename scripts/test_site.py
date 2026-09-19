#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""The gate on everything under site/. Run it after scripts/build_site_data.sh.

    uv run scripts/test_site.py

It reads whatever pages exist, so a page added by a later session is covered
the moment it lands — there is no list of pages to keep up to date.

Seven checks, each of them something a reviewer would otherwise have to read for:

 (1) every page parses, and its data block is valid JSON
 (2) every <span data-n="…"> holds EXACTLY what the page's own data block says
     it should. Empty is a hole in a sentence; different is a page that was
     hand-edited, or built and then edited, and either way the sentence and the
     table under the chart no longer agree
 (3) no bare digit in prose. Prose is <p>, <h1>…<h6>, <figcaption> and the
     text elements a reader reads the same way — <li>, <td>, <th>, <summary>,
     <dt>, <dd>, <button>, <label> — minus what a data-n span or a <code>
     element holds. Years, day-month dates and ISO dates are allowed;
     everything else has to come from the build, which is docs/SITE.md § Voice
 (4) none of the banned words. The list is Voice's: the reader is told "big
     ships" and "small boats", never the words in the schema. how.html may
     name the real term once, in parentheses, for the engineers
 (5) no `mmsi` and no nine-digit integer anywhere under site/, in any file —
     the second is the shape of a radio ID and the first is the word for it
 (6) the explorer's data stays inside its 40 MB budget
 (7) the small-boat numbers in the WRITTEN explorer files clear the >= 5 floor.
     scripts/build_explore_data.py asserts it on what it read; this asserts it
     on what is committed, the way scripts/test_export.py tests the parquet
     files rather than the query that made them

WHAT THIS DOES NOT CHECK, so that nobody reads it as a full gate: whether a
chart says what its headline claims. That is the blind read in docs/SITE.md
§ Acceptance, and it needs eyes.
"""
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
PROSE = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "figcaption",
         "li", "td", "th", "summary", "dt", "dd", "button", "label"}
SKIP = {"code", "script", "style"}

# docs/SITE.md § Voice. The reader never meets the schema.
BANNED = ["class a", "class b", "mmsi", "h3", "k-anonymity", "quantile", "p90",
          "median", "cell-hour", "vessel-day", "uniqexact", "baseline", "proxy",
          "cohort", "retention", "aggregate", "resolution"]

MONTHS = ("January|February|March|April|May|June|July|August|September|"
          "October|November|December")
DATEY = re.compile(rf"\b(19|20)\d{{2}}\b"                              # a year
                   rf"|\b\d{{1,2}}(?:\s*[–-]\s*\d{{1,2}})?\s+(?:{MONTHS})\b"
                   rf"|\b(?:{MONTHS})\s+\d{{1,2}}\b"                   # August 26
                   rf"|\b\d{{4}}-\d{{2}}(?:-\d{{2}})?\b")              # 2023-12
TEXT_FILES = {".html", ".js", ".css", ".json", ".svg", ".md", ".txt"}
NINE = re.compile(r"\b\d{9}\b")


class Page(HTMLParser):
    """Collects the prose of a page, and the contents of its data-n spans."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.prose, self.spans, self.figures = [], {}, []
        self._in, self._skip, self._span = [], 0, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in SKIP:
            self._skip += 1
        if tag in PROSE:
            self._in.append([tag, ""])
        if tag == "figure" and a.get("id"):
            self.figures.append(a["id"])
        if tag == "span" and "data-n" in a:
            self._span = [a["data-n"], ""]
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in SKIP and self._skip:
            self._skip -= 1
        if tag in PROSE and self._in:
            name, text = self._in.pop()
            self.prose.append((name, " ".join(text.split())))
        if tag == "span" and self._span is not None:
            self.spans[self._span[0]] = self._span[1].strip()
            self._span, self._skip = None, self._skip - 1

    def handle_data(self, data):
        if self._span is not None:
            self._span[1] += data
        elif not self._skip and self._in:
            self._in[-1][1] += data


def check(page, fails):
    def bad(msg):
        fails.append(f"{page.relative_to(ROOT)}: {msg}")

    src = page.read_text()
    p = Page()
    p.feed(src)

    # A page with no number in its prose needs no data block; a page with one
    # cannot have got it from anywhere but the build.
    n = None
    m = re.search(r'<script type="application/json" id="data">(.*?)</script>', src, re.S)
    if not m:
        if p.spans:
            bad("has data-n spans but no <script type=\"application/json\" "
                "id=\"data\"> block for scripts/build_site_data.py to fill")
    else:
        try:
            n = json.loads(m.group(1)).get("n", {})
        except json.JSONDecodeError as e:
            bad(f"the data block is not valid JSON: {e}")

    # The sentence and the block under it are one fact written twice. A page
    # that was built and then hand-edited keeps both, disagreeing, and nothing
    # else on this site would ever say so.
    for key, value in p.spans.items():
        if not value:
            bad(f'<span data-n="{key}"> is empty — run scripts/build_site_data.sh')
        elif n is not None and key not in n:
            bad(f'<span data-n="{key}"> is filled with "{value}" but the data '
                f'block has no such number — run scripts/build_site_data.sh')
        elif n is not None and value != str(n[key]):
            bad(f'<span data-n="{key}"> reads "{value}" and the page\'s own '
                f'data block says "{n[key]}" — the page was edited by hand '
                f'after the build; run scripts/build_site_data.sh')

    for tag, text in p.prose:
        stripped = DATEY.sub("", text)
        for digits in re.findall(r"\d[\d  ]*", stripped):
            bad(f'<{tag}> holds the bare number "{digits.strip()}" — every number '
                f'in prose is a <span data-n="…">: …{text[:90]}…')
        low = text.lower()
        for word in BANNED:
            for hit in re.finditer(rf"\b{re.escape(word)}\b", low):
                # how.html is allowed to name the real term once, in brackets,
                # because its readers are the ones who will run the queries.
                inside = (low.rfind("(", 0, hit.start()) > low.rfind(")", 0, hit.start()))
                if page.name == "how.html" and inside:
                    continue
                bad(f'<{tag}> says "{word}" — docs/SITE.md § Voice: …{text[:90]}…')
    return p


MONTH_JS = re.compile(r'^window\.SEAFOLK_MONTH=window\.SEAFOLK_MONTH\|\|\{\};'
                      r'window\.SEAFOLK_MONTH\["\d{4}-\d{2}"\]=(.*);\s*$', re.S)


def explorer_floor(data, fails):
    """Check (7): every small-boat number in the committed explorer files
    counts at least five boats.

    scripts/build_explore_data.py asserts the floor on the rows it reads out of
    the parquet; this reads the files that were actually written, because those
    are what ships. A month file is
    `window.SEAFOLK_MONTH["YYYY-MM"] = {fleet: [[cell indices], [values]]}`.
    """
    months = sorted(f for f in data.glob("*.js") if f.stem[:4].isdigit())
    if not months:
        fails.append("site/explore/data holds no YYYY-MM.js month files")
        return
    low, seen = [], 0
    for f in months:
        m = MONTH_JS.match(f.read_text().strip())
        if not m:
            fails.append(f"{f.relative_to(ROOT)}: not the shape "
                         f"scripts/build_explore_data.py writes")
            continue
        try:
            payload = json.loads(m.group(1))
        except json.JSONDecodeError as e:
            fails.append(f"{f.relative_to(ROOT)}: not valid JSON: {e}")
            continue
        values = (payload.get("small_boats") or [[], []])[1]
        seen += len(values)
        low += [(f.stem, v) for v in values if v < 5]
    print(f"  site/explore/data: {seen} small-boat cell-months across "
          f"{len(months)} months, {len(low)} of them under five boats")
    for month, v in low[:5]:
        fails.append(f"site/explore/data/{month}.js: a small-boat cell counts "
                     f"{v} boats — the k >= 5 floor is broken (CLAUDE.md)")


def main():
    fails, pages = [], sorted(SITE.glob("*.html")) + sorted(SITE.glob("*/*.html"))
    if not pages:
        sys.exit("no pages under site/")
    for page in pages:
        p = check(page, fails)
        print(f"  {page.relative_to(ROOT)}: {len(p.prose)} prose elements, "
              f"{len(p.spans)} numbers, {len(p.figures)} figures")

    for f in sorted(SITE.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in TEXT_FILES:
            continue
        body = f.read_text(errors="replace")
        if re.search(r"\bmmsi\b", body, re.I):
            fails.append(f"{f.relative_to(ROOT)}: says 'mmsi' — the site calls it "
                         f"a radio ID, and never prints one")
        for hit in NINE.findall(body):
            fails.append(f"{f.relative_to(ROOT)}: holds the nine-digit integer "
                         f"{hit} — that is the shape of a radio ID")

    data = SITE / "explore" / "data"
    if data.exists():
        mb = sum(f.stat().st_size for f in data.rglob("*") if f.is_file()) / 1e6
        print(f"  site/explore/data: {mb:.1f} MB of 40")
        if mb > 40:
            fails.append(f"site/explore/data is {mb:.0f} MB, over the 40 MB budget")
        explorer_floor(data, fails)

    if fails:
        print("\nFAIL")
        for f in fails:
            print(f"  {f}")
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
