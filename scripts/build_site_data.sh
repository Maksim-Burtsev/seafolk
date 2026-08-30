#!/usr/bin/env bash
# Refresh the data embedded in the pages under site/.
#
# The pages are self-contained: each carries its numbers in a
# <script type="application/json" id="data"> block, which this script rewrites
# in place. That keeps one file that works from file://, from GitHub Pages and
# as a published artifact — a page that fetches a sibling .json works in only
# the middle case.
#
#   scripts/build_site_data.sh                 # read data/ch
#   CH_PATH=/tmp/ch_copy scripts/build_site_data.sh   # read a copy, e.g. while a load runs
set -euo pipefail
cd "$(dirname "$0")/.."

page=site/day-clocks.html

# July 2025, the four fleets the page draws, as
#   {"weekday": {"leisure": [24 shares], …}, "sat": {…}, "sun": {…}}
json=$(scripts/ch.sh -q "
SELECT toJSONString(mapFromArrays(groupArray(daytype), groupArray(fleets)))
FROM (
    SELECT daytype, mapFromArrays(groupArray(fleet), groupArray(hours)) AS fleets
    FROM (
        SELECT daytype,
               multiIf(ship_group='leisure',   'leisure',
                       ship_group='passenger', 'ferries',
                       ship_group) AS fleet,
               arrayMap(x -> round(x * 100, 3), groupArray(share_of_day)) AS hours
        FROM (
            $(sed -e 's/^--.*$//' -e '/^WITH/,$!d' sql/12_day_profile.sql | sed 's/;$//')
        )
        WHERE month = 202507
          AND (  (ship_group = 'leisure'   AND mobile = 'Class B')
              OR (ship_group IN ('passenger','cargo','fishing') AND mobile = 'Class A'))
        GROUP BY daytype, fleet
    )
    GROUP BY daytype
)")

python3 - "$page" "$json" <<'PY'
import re, sys, pathlib
page, data = pathlib.Path(sys.argv[1]), sys.argv[2]
s = page.read_text()
new = re.sub(r'(<script type="application/json" id="data">).*?(</script>)',
             lambda m: m.group(1) + data + m.group(2), s, flags=re.S)
if new == s and '<script type="application/json" id="data">' not in s:
    sys.exit(f"{page}: no <script type=\"application/json\" id=\"data\"> block to fill")
page.write_text(new)
print(f"{page}: embedded {len(data)} bytes")
PY
