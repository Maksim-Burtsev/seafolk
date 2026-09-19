#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""The guards in scripts/build_site_data.py, tested on their own.

    uv run scripts/test_build_guards.py

Milliseconds, no store, no pages: scripts/build_site_data.sh runs it before it
opens the store, so a broken guard is found before a thirty-second query is.

WHY THIS EXISTS. The guards are the last thing between the store and a public
page, and until now the only way to know they worked was to write a leaking
page and watch the build stop. Two of them did not: a private count filed as
`sailing_boats` built green, because the guard was keyed on the schema's word
for the fleet and the pages use the reader's; and a display string ("3 boats")
was not read as a number at all, so anything printed rather than returned
slipped past. Both are cases below.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_site_data import as_int, fill, guard  # noqa: E402
from site_data import private_count  # noqa: E402


def stops(data, because):
    """The guard must refuse this page dict."""
    try:
        guard("a-page.html", data)
    except SystemExit as e:
        assert because.lower() in str(e).lower(), \
            f"stopped for the wrong reason: {e}"
        return
    raise AssertionError(f"guard passed {data!r} — it must stop: {because}")


def passes(data):
    guard("a-page.html", data)


# --- guard (b): a private-fleet head count under five ----------------------
# Every word the pages use for the fleet, because the modules rename `leisure`
# to `sailing` for the reader and the guard used to know only the schema's word.
for key in ("leisure_boats", "small_boats", "sailing_boats", "private_boats",
            "marina_boats", "small_boats_min", "n.sailing"):
    stops({"block": {key: 3}}, "under five")
stops({"block": {"sailing_boats": "3 boats"}}, "under five")
stops({"block": {"leisure": "4"}}, "under five")
stops({"harbour": {"small_boats": [12, 7, 2]}}, "under five")
# 0 is nobody, and nobody is not a person: the rule is 0 or >= 5.
passes({"block": {"sailing_boats": 0}})
passes({"block": {"sailing_boats": 5}})
passes({"block": {"sailing_boats": "22 773"}})
# a SHARE of the private fleet is a float and carries no floor. 0.37 is not
# three boats, and a guard that reads it as three stops a correct build.
passes({"block": {"sailing_share": 0.37}})
passes({"block": {"sailing_pct": "1.9 %"}})
passes({"block": {"sailing_peak": "one in the afternoon"}})
# a count of something that is not boats, on the allow-list, with its reason
passes({"picture": {"rows": [[2, 9, 1, 4], [5, 12, 3]]}})
passes({"n": {"sailing_storms": "3", "sailing_hours": "3"}})
# …and a count of boats under a name nothing on the allow-list covers
stops({"n": {"sailing_fleet": "3"}}, "under five")

# --- guard (a): the shape of a radio ID ------------------------------------
stops({"block": {"total": 219_000_123}}, "nine-digit")
stops({"block": {"note": "the boat 219000123 sailed"}}, "nine-digit")
passes({"block": {"total": 21_900_012}})          # eight digits
passes({"block": {"total": 2_190_001_234}})       # ten digits are not an MMSI

# --- guard (c): "n" holds numbers, or the key is not there -----------------
stops({"n": {"winter_sailing_lo": None}}, "withholding")
stops({"n": {"winter_sailing_lo": "None"}}, "withholding")
stops({"n": {"trip_half": "nan"}}, "withholding")
passes({"n": {"trip_half": "0"}})

# a span whose key the module never produced: an empty gap in a sentence
with tempfile.TemporaryDirectory() as d:
    page = Path(d) / "a-page.html"
    page.write_text('<script type="application/json" id="data"></script>'
                    '<p>out: <span data-n="boats_out"></span></p>')
    try:
        fill(page, {"n": {"boats_in": "7"}})
    except SystemExit as e:
        assert "boats_out" in str(e), e
    else:
        raise AssertionError("fill accepted a span with no number behind it")
    # …and the same page, built
    fill(page, {"n": {"boats_out": "7"}})
    assert '<span data-n="boats_out">7</span>' in page.read_text()

# --- the number parser the guard reads leaves with -------------------------
assert as_int(3) == 3
assert as_int("3 boats") == 3
assert as_int("22 773") == 22773      # the separator site_data.sp prints
assert as_int("1 088") == 1088        # a stray nbsp from a hand edit
assert as_int("1 088 departures") == 1088
assert as_int(0.37) is None                # a share is never a head count
assert as_int("1.9 %") is None
assert as_int("three quarters") is None
assert as_int("4 October 2025") is None
assert as_int(True) is None

# --- the rule itself, where the modules call it ----------------------------
assert private_count(0, "nobody") == 0
assert private_count(5, "five") == 5
for bad, why in ((3, "at least"), (None, "None")):
    try:
        private_count(bad, "a harbour hour")
    except SystemExit as e:
        assert why in str(e), e
    else:
        raise AssertionError(f"private_count let {bad!r} through")

print("PASS  scripts/test_build_guards.py")
