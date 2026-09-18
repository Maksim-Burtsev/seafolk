"""site/day-clocks.html — the S3 prototype, kept building.

This is the page the site's colour tokens and typography came from, and the
query that fed it used to live inside scripts/build_site_data.sh. It moved here
unchanged when S12a turned that script into a wrapper, so the prototype keeps
working while S12b rebuilds it properly as site/pulse.html (docs/SITE.md § P1).

Nothing else should copy this module: it has no `n` map, because the page holds
its prose in a JS translation table rather than in HTML with data-n spans,
which is exactly what docs/SITE.md § Build forbids for the real pages.
"""
import json
import re

from . import ROOT

# July 2025, the four fleets the page draws, as
#   {"weekday": {"sailing": [24 shares], …}, "sat": {…}, "sun": {…}}
QUERY = """
SELECT toJSONString(mapFromArrays(groupArray(daytype), groupArray(fleets)))
FROM (
    SELECT daytype, mapFromArrays(groupArray(fleet), groupArray(hours)) AS fleets
    FROM (
        SELECT daytype,
               multiIf(ship_group='leisure',   'sailing',
                       ship_group='passenger', 'ferries',
                       ship_group) AS fleet,
               arrayMap(x -> round(x * 100, 3), groupArray(share_of_day)) AS hours
        FROM (
            %s
        )
        WHERE month = 202507
          AND (  (ship_group = 'leisure'   AND mobile = 'Class B')
              OR (ship_group IN ('passenger','cargo','fishing') AND mobile = 'Class A'))
        GROUP BY daytype, fleet
    )
    GROUP BY daytype
)"""


def build(ch):
    # sql/12 is one WITH … SELECT, so its body nests as a subquery: drop the
    # leading comment block and the trailing semicolon and inline it. That is
    # what the shell script's two seds did, and it keeps one definition of the
    # day profile instead of two.
    body = (ROOT / "sql" / "12_day_profile.sql").read_text()
    body = re.sub(r"^--.*$", "", body[body.index("WITH"):], flags=re.M)
    return json.loads(ch("-q", QUERY % body.rstrip().rstrip(";"))[0][0])
