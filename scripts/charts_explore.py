"""The chart the explorer (site/explore/index.html) is drawn on.

    uv run --project notes scripts/charts_explore.py

Two images over the whole bathymetry box (lon 7-16, lat 53.5-58.5), both from
scripts/chartkit.py so they are the same chart as every other sheet:

  sea   the full base: paper, shallows, contours, soundings, land
  land  land and coast ONLY, on a transparent ground

deck.gl lays them as two BitmapLayers with the fleets' dots between them, so a
dot that falls inside a coastal cell is covered by the land, the way chartkit's
own stipple keeps to the sea. No data is read here.

Written as site/explore/data/sheet.js with the images inlined as data: URLs,
not as .webp files beside the page: WebGL refuses an image loaded from file://
(a cross-origin texture), and the page must open by double-click.
"""
import base64
import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chartkit as ck  # noqa: E402
from matplotlib.collections import PatchCollection  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402
from PIL import Image  # noqa: E402

BOX = (7.0, 16.0, 53.5, 58.5)      # exactly the EMODnet grid in data/context
WIDTH = 2600                       # ~3x the map at its widest; sharp one zoom step in
OUT = ck.ROOT / "site" / "explore" / "data" / "sheet.js"
NINE = re.compile(r"\b\d{9}\b")    # scripts/test_site.py's radio-ID shape


def render(sheet, transparent):
    buf = io.BytesIO()
    sheet.fig.savefig(buf, format="png", dpi=100, transparent=transparent,
                      facecolor="none" if transparent else ck.C["paper"])
    ck.plt.close(sheet.fig)
    img = Image.open(buf)
    return img if transparent else img.convert("RGB")


def data_url(img, quality):
    # base64 can spell nine digits in a row by chance; the site's guard cannot
    # tell that from a radio ID, so nudge the encoder until it does not.
    for q in range(quality, quality - 6, -1):
        buf = io.BytesIO()
        img.save(buf, "WEBP", quality=q, method=6)
        s = base64.b64encode(buf.getvalue()).decode()
        if not NINE.search(s):
            return "data:image/webp;base64," + s
    sys.exit("every encoding holds a nine-digit run")


def main():
    sea = ck.Sheet(BOX, WIDTH).base()
    sea._soundings_draw()                       # chartkit draws these in save()
    land = ck.Sheet(BOX, WIDTH)
    land.fig.patch.set_alpha(0)
    land.ax.set_facecolor("none")
    land.ax.add_collection(PatchCollection(
        [Polygon(r) for r in ck.land_rings()], facecolor=ck.C["land"],
        edgecolor=ck.C["coast"], lw=.55))
    body = {"box": list(BOX), "w": sea.w, "h": sea.h,
            "sea": data_url(render(sea, False), 86),
            "land": data_url(render(land, True), 90)}
    OUT.write_text("// Written by scripts/charts_explore.py. Do not edit.\n"
                   f"window.SEAFOLK_SHEET={json.dumps(body, separators=(',', ':'))};\n")
    print(f"{OUT.relative_to(ck.ROOT)}: {sea.w}x{sea.h}, {OUT.stat().st_size / 1e3:.0f} kB")


if __name__ == "__main__":
    main()
