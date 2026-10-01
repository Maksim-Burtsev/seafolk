"""Two A3 posters in the nautical-chart style of the site (docs/SITE.md § Round 3).

    CH_PATH=data/ch_<clone> uv run --project notes scripts/render_posters.py

Writes into site/posters/ a PDF to print and a 300-dpi PNG of each:

  danish-waters   one July of traffic on one chart: cargo in pencil hatching,
                  ferries as red ink tracks, fishing as green stipple, small
                  boats as sail-orange stipple, over depths, contours and
                  soundings; neatline, compass rose, scale bar, cartouche.
  year-of-boats   the twelve months of 2025, one small sheet each, small boats
                  only: the Danish summer as it fills the water and drains away.

The maps are scripts/chartkit.py sheets; the data comes from the same helpers
as the essay's sheets (scripts/charts_index.py), so a poster and the page it
belongs to cannot disagree.

PRIVACY. Small boats come only from dist/dataset/leisure_daily.parquet, and
charts_index.small_boats() asserts every row it reads counts at least five
boats. They are drawn as stipple scattered at random inside their ~9 km cell:
no dot is a boat. Ferry tracks come from the store's public_track, and
charts_index.ferry_tracks() checks every radio ID in them against vessel_day
(Class A, never leisure) before anything is drawn; the IDs never reach a file.
The store is read, so run it on a clone (`cp -Rc data/ch data/ch_x`,
CH_PATH=data/ch_x): the clickhouse-local lock is exclusive.

FONTS. The site's Source Serif 4 and IBM Plex Mono, fetched once into
data/context/fonts (not committed) from the Adobe and Google font repositories.
"""
import io
import math
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import charts_index as ci  # noqa: E402
import chartkit as ck      # noqa: E402

import numpy as np                                                  # noqa: E402
import matplotlib                                                   # noqa: E402
import matplotlib.patheffects as pe                                 # noqa: E402
import matplotlib.pyplot as plt                                     # noqa: E402
from matplotlib import font_manager as fm                           # noqa: E402
from matplotlib.patches import Rectangle, Circle, Polygon           # noqa: E402
from PIL import Image                                               # noqa: E402

ROOT = ck.ROOT
OUT = ROOT / "site" / "posters"
C = ck.C
LABEL, SEA_INK = "#5a5446", "#3b5b6b"     # site/css/site.css --label, --sea-ink
W_MM, H_MM = 297.0, 420.0          # A3 portrait
DPI = 300
SOURCE = ("Danish Maritime Authority AIS archive · depths EMODnet Bathymetry · "
          "coast Natural Earth · github.com/Maksim-Burtsev/seafolk")

# ---------------------------------------------------------------- fonts ----
FONT_DIR = ROOT / "data" / "context" / "fonts"
FONTS = {
    "serif": "https://github.com/adobe-fonts/source-serif/raw/release/TTF/SourceSerif4-Regular.ttf",
    "it": "https://github.com/adobe-fonts/source-serif/raw/release/TTF/SourceSerif4-It.ttf",
    "semi": "https://github.com/adobe-fonts/source-serif/raw/release/TTF/SourceSerif4Display-Semibold.ttf",
    "semi_it": "https://github.com/adobe-fonts/source-serif/raw/release/TTF/SourceSerif4Display-SemiboldIt.ttf",
    "mono": "https://github.com/google/fonts/raw/main/ofl/ibmplexmono/IBMPlexMono-Regular.ttf",
    "mono_med": "https://github.com/google/fonts/raw/main/ofl/ibmplexmono/IBMPlexMono-Medium.ttf",
}


def fonts():
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    fp = {}
    for key, url in FONTS.items():
        f = FONT_DIR / url.rsplit("/", 1)[1]
        if not f.exists():
            print(f"  fetching {f.name}")
            urllib.request.urlretrieve(url, f)
        fm.fontManager.addfont(str(f))
        fp[key] = fm.FontProperties(fname=str(f))
    # chartkit letters its soundings in the generic "serif": make that the site's.
    matplotlib.rcParams["font.serif"] = ["Source Serif 4"]
    return fp


F = fonts()


def names():
    """site/js/chart.js's NAMES: the one list of names every sheet letters."""
    js = (ROOT / "site" / "js" / "chart.js").read_text()
    out = {}
    for m in re.finditer(r'"([^"]+)":\s*\{([^}]*)\}', js):
        d = dict(re.findall(r'(\w+):\s*("?[^,"]+"?)', m.group(2)))
        out[m.group(1)] = {k: v.strip('"') if v.startswith('"') else float(v) for k, v in d.items()}
    assert "Kattegat" in out and "København" in out, "chart.js NAMES did not parse"
    return out


NAMES = names()


# ---------------------------------------------------------------- page -----
class Page:
    """An A3 figure with a full-page axes in millimetres (y down) for the furniture."""

    def __init__(self, fig=None):
        self.fig = fig or plt.figure()
        self.fig.set_size_inches(W_MM / 25.4, H_MM / 25.4)
        self.fig.patch.set_facecolor(C["paper"])
        self.p = self.fig.add_axes([0, 0, 1, 1], zorder=10)
        self.p.set_xlim(0, W_MM)
        self.p.set_ylim(H_MM, 0)
        self.p.axis("off")
        self.p.patch.set_alpha(0)

    def rect(self, x, y, w, h):
        return [x / W_MM, 1 - (y + h) / H_MM, w / W_MM, h / H_MM]

    def text(self, x, y, s, font, size, color=None, **kw):
        kw.setdefault("va", "baseline")
        kw.setdefault("zorder", 8)
        return self.p.text(x, y, s, fontproperties=font, fontsize=size,
                           color=color or C["ink"], **kw)

    def line(self, xs, ys, lw=.6, color=None, **kw):
        self.p.plot(xs, ys, lw=lw, color=color or C["ink"], solid_capstyle="butt", **kw)

    def box(self, x, y, w, h, lw=.6, fill="none", color=None, z=1):
        self.p.add_patch(Rectangle((x, y), w, h, fill=fill != "none", facecolor=fill,
                                   edgecolor=color or C["ink"], lw=lw, zorder=z))

    def neatline(self, x, y, w, h, box, bar=1.6, gap=2.6, labels=True):
        """The chart border: an inner rule, a bar alternating ink and paper
        every ten minutes of arc, an outer rule, degrees lettered outside."""
        lon0, lon1, lat0, lat1 = box
        self.box(x, y, w, h, lw=.5)
        self.box(x - bar, y - bar, w + 2 * bar, h + 2 * bar, lw=.5)
        self.box(x - bar - gap, y - bar - gap, w + 2 * (bar + gap), h + 2 * (bar + gap), lw=1.3)
        step = 1 / 6
        X = lambda lon: x + (lon - lon0) / (lon1 - lon0) * w          # noqa: E731
        Y = lambda lat: y + (lat1 - lat) / (lat1 - lat0) * h          # noqa: E731
        k0 = math.floor(lon0 / step)
        for k in range(k0, math.ceil(lon1 / step)):
            if k % 2:
                continue
            a, b = X(max(k * step, lon0)), X(min((k + 1) * step, lon1))
            for yy in (y - bar, y + h):
                self.p.add_patch(Rectangle((a, yy), b - a, bar, color=C["ink"], lw=0))
        for k in range(math.floor(lat0 / step), math.ceil(lat1 / step)):
            if k % 2:
                continue
            a, b = Y(min((k + 1) * step, lat1)), Y(max(k * step, lat0))
            for xx in (x - bar, x + w):
                self.p.add_patch(Rectangle((xx, a), bar, b - a, color=C["ink"], lw=0))
        if not labels:
            return
        for lon in range(math.ceil(lon0), math.floor(lon1) + 1):
            self.text(X(lon), y + h + bar + gap + 4.2, f"{lon}°E", F["mono"], 7.5, ha="center")
        for lat in range(math.ceil(lat0), math.floor(lat1) + 1):
            self.text(x - bar - gap - 1.4, Y(lat), f"{lat}°N", F["mono"], 7.5, ha="right", va="center")
            self.text(x + w + bar + gap + 1.4, Y(lat), f"{lat}°N", F["mono"], 7.5, ha="left", va="center")

    def lettering(self, x, y, w, h, box, which, scale=1.0, moved=None):
        """Names from chart.js; `moved` shifts one for this sheet, {name: (lon, lat)}."""
        lon0, lon1, lat0, lat1 = box
        for n in which:
            d = dict(NAMES[n])
            if moved and n in moved:
                d["lon"], d["lat"] = moved[n]
            if not (lon0 < d["lon"] < lon1 and lat0 < d["lat"] < lat1):
                continue
            px = x + (d["lon"] - lon0) / (lon1 - lon0) * w
            py = y + (lat1 - d["lat"]) / (lat1 - lat0) * h
            halo = [pe.withStroke(linewidth=2.2 * scale, foreground=C["paper"])]
            if d.get("kind") == "water":
                s = " ".join(n.upper()) if d.get("big") else n
                self.text(px, py, s, F["it"], (12 if d.get("big") else 9) * scale, SEA_INK,
                          ha="center", va="center", rotation=-d.get("rot", 0), path_effects=halo)
            else:
                left = bool(d.get("left"))
                self.p.add_patch(Circle((px, py), .75 * scale, color=C["ink"], zorder=3))
                self.text(px + (-1.8 if left else 1.8) * scale, py, n.upper(), F["mono_med"], 6.6 * scale,
                          ha="right" if left else "left", va="center", path_effects=halo)

    def scalebar(self, x, y, mm_per_nm, nm=40, parts=4):
        seg = nm / parts * mm_per_nm
        for i in range(parts):
            self.p.add_patch(Rectangle((x + i * seg, y), seg, 1.4, facecolor=C["ink"] if i % 2 == 0 else C["paper"],
                                       edgecolor=C["ink"], lw=.5))
        for i in range(parts + 1):
            self.text(x + i * seg, y - 1.2, f"{round(i * nm / parts)}", F["mono"], 6.5, ha="center")
        self.text(x + nm * mm_per_nm / 2, y + 5.2, "nautical miles", F["it"], 8, ha="center")

    def rose(self, cx, cy, r, color):
        """A compass rose as charts print it: a degree ring, the true north star."""
        p = self.p
        for rr, lw in ((r, .6), (r * .86, .4), (r * .5, .35)):
            p.add_patch(Circle((cx, cy), rr, fill=False, edgecolor=color, lw=lw, zorder=5))
        for deg in range(0, 360, 5):
            a = math.radians(deg)
            ln = .14 if deg % 30 == 0 else .08 if deg % 10 == 0 else .045
            s, c = math.sin(a), -math.cos(a)
            p.plot([cx + s * r, cx + s * r * (1 - ln)], [cy + c * r, cy + c * r * (1 - ln)],
                   color=color, lw=.45, zorder=5)
            if deg % 30 == 0 and deg:
                self.text(cx + s * r * .74, cy + c * r * .74, f"{deg:03d}", F["mono"], 4.6, color,
                          ha="center", va="center", rotation=-deg, zorder=6)
        for k in range(8):                                # the star
            a = math.radians(45 * k)
            ln = r * (.84 if k % 2 == 0 else .42)
            w = r * .09
            tip = (cx + math.sin(a) * ln, cy - math.cos(a) * ln)
            l = (cx + math.sin(a - math.pi / 2) * w, cy - math.cos(a - math.pi / 2) * w)
            rt = (cx + math.sin(a + math.pi / 2) * w, cy - math.cos(a + math.pi / 2) * w)
            p.add_patch(Polygon([(cx, cy), l, tip], closed=True, facecolor=color, edgecolor=color, lw=.3, zorder=6))
            p.add_patch(Polygon([(cx, cy), rt, tip], closed=True, facecolor=C["paper"], edgecolor=color, lw=.3, zorder=6))
        self.text(cx, cy - r - 2.2, "N", F["semi"], 9, color, ha="center")

    def save(self, name):
        OUT.mkdir(parents=True, exist_ok=True)
        for ext in ("pdf", "png"):
            path = OUT / f"{name}.{ext}"
            self.fig.savefig(path, facecolor=C["paper"], dpi=DPI)
            print(f"  {path.relative_to(ROOT)}  {path.stat().st_size / 1e6:.1f} MB")
        plt.close(self.fig)


def key_swatch(pg, x, y, kind, color):
    if kind == "wash":
        pg.p.add_patch(Rectangle((x, y - 2.2), 9, 3, color=color, alpha=.55, lw=0, zorder=8))
    elif kind == "line":
        for dy in (-1.4, -.6, .2):
            pg.line([x, x + 9], [y + dy - .3, y + dy - .3 + .4 * dy], lw=.5, color=color, zorder=8)
    else:
        rng = np.random.default_rng(sum(map(ord, color)))
        pg.p.scatter(x + rng.random(14) * 9, y - 2.3 + rng.random(14) * 3, s=1.6, color=color, lw=0, zorder=8)


# ---------------------------------------------------- poster 1: one July ----
def danish_waters():
    box = (7.5, 14.0, 53.5, 58.5)            # the whole EMODnet grid north to south
    mx, my, mw = 20.0, 24.0, 257.0
    mh = mw * (box[3] - box[2]) * ck.ASPECT / (box[1] - box[0])

    s = ck.Sheet(box, width=round(mw / 25.4 * 100)).base()
    s.flow(*ci.public(2025, ["cargo"], 7), "graphite", strokes=60000)
    lon, lat, v = ci.public(2025, ["fishing"], 7)
    fish = s.stipple(lon, lat, [min(round(x / 8), 14) for x in v], 1.3, "fishing", size=.9, alpha=.75)
    lon, lat, v = zip(*ci.small_boats("2025-07"))
    small = s.stipple(lon, lat, [round(x / ci.BOATS_PER_DOT) for x in v], 9, "small", size=1.5, alpha=.85)
    segs = ci.segments(ci.ferry_tracks("2025-07-01", "2025-07-31", 2), 600)
    s.tracks(segs, "redpen", lw=.3, alpha=.12, hand=True)
    s.ax.collections[-1].set_rasterized(True)
    s._soundings_draw()
    print(f"danish-waters: {fish} fishing dots, {small} small-boat dots, {len(segs)} ferry segments")

    pg = Page(s.fig)
    s.ax.set_position(pg.rect(mx, my, mw, mh))
    pg.neatline(mx, my, mw, mh, box)
    pg.lettering(mx, my, mw, mh, box, [
        "Skagerrak", "Kattegat", "Nordsøen", "Østersøen", "Storebælt", "Lillebælt", "Øresund",
        "Femern Bælt", "Limfjorden", "Skagen", "Hirtshals", "Hanstholm", "Thyborøn", "Hvide Sande",
        "Esbjerg", "Frederikshavn", "Aarhus", "Odense", "København", "Helsingør", "Kiel", "Rødby",
        "Anholt", "Læsø", "Samsø", "Ærø", "Göteborg"], moved={"Østersøen": (13.2, 54.62)})

    X = lambda lon: mx + (lon - box[0]) / (box[1] - box[0]) * mw     # noqa: E731
    Y = lambda lat: my + (box[3] - lat) / (box[3] - box[2]) * mh     # noqa: E731
    pg.rose(X(7.98), Y(54.42), 14, C["ink"])

    # the cartouche, on the Swedish shore where a chart letters its title
    cx, cy = X(12.5), Y(58.42)
    cw, ch = X(13.93) - cx, 118
    pg.box(cx, cy, cw, ch, lw=1.1, fill="#f8f3e6", z=4)
    pg.box(cx + 1.8, cy + 1.8, cw - 3.6, ch - 3.6, lw=.45, z=5)
    t, r = cx + 6.5, cx + cw - 6.5
    pg.text(t, cy + 11, "SEAFOLK · CHART 1", F["mono_med"], 6.8, LABEL)
    pg.text(t, cy + 22.5, "Danish", F["semi"], 25)
    pg.text(t, cy + 32.5, "Waters", F["semi"], 25)
    pg.text(t, cy + 40.5, "One July of traffic,", F["it"], 10, LABEL)
    pg.text(t, cy + 45.2, "as the ships' own radios", F["it"], 10, LABEL)
    pg.text(t, cy + 49.9, "told it", F["it"], 10, LABEL)
    pg.line([t, r], [cy + 54.5] * 2, lw=.5)
    rows = [("wash", C["cargo"], "Cargo ships", "pencil, densest in the lanes"),
            ("line", C["ferry"], "Ferries", "and other passenger ships"),
            ("dots", C["fishing"], "Fishing boats", "a dot for 8 hours out"),
            ("dots", C["small"], "Small boats", f"a dot for {ci.BOATS_PER_DOT} boat-days")]
    for i, (kind, col, a, b) in enumerate(rows):
        yy = cy + 62.5 + i * 9.6
        key_swatch(pg, t, yy, kind, col)
        pg.text(t + 11.5, yy - .7, a, F["serif"], 9)
        pg.text(t + 11.5, yy + 3.3, b, F["it"], 7.4, LABEL)
    pg.text(t, cy + 101, "No dot is a boat: small-boat", F["it"], 7, LABEL)
    pg.text(t, cy + 104.4, "dots fall at random in their patch.", F["it"], 7, LABEL)
    pg.line([t, r], [cy + 108] * 2, lw=.5)
    km_per_mm = (box[1] - box[0]) * ck.KM_PER_DEG_LAT / ck.ASPECT / mw
    scale = round(km_per_mm * 1e6 / 1e4) * 1e4
    pg.text(t, cy + 113, f"JULY 2025 · 1 : {scale:,.0f}".replace(",", " "), F["mono_med"], 6.3)
    pg.scalebar(mx + 30, my + mh - 14, 1.852 / km_per_mm, nm=40)

    pg.text(mx - 4.2, 12.5, "SEAFOLK", F["mono_med"], 7.5, ha="left")
    pg.text(mx + mw + 4.2, 12.5, "DEPTHS IN METRES · WATER UNDER 5, 10 AND 20 M TINTED",
            F["mono"], 7, ha="right")
    pg.text(W_MM / 2, H_MM - 20, SOURCE, F["mono"], 6.8, LABEL, ha="center")
    pg.save("danish-waters")


# ------------------------------------------------ poster 2: twelve months ----
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def year_of_boats(year=2025):
    box = ck.BOXES["denmark"]
    pg = Page()
    gx, gut = 20.0, 6.0
    pw = (W_MM - 2 * gx - 2 * gut) / 3
    ph = pw * (box[3] - box[2]) * ck.ASPECT / (box[1] - box[0])
    top, pitch = 64.0, ph + 12.0

    pg.text(gx, 17, "SEAFOLK  ·  CHART  2", F["mono_med"], 7.5, LABEL)
    pg.text(gx, 33, "A year of small boats", F["semi"], 34)
    pg.text(gx, 43, f"Every small boat heard in Danish waters in {year}, month by month.",
            F["it"], 12.5, LABEL)
    pg.text(gx, 49.5, f"One dot for {ci.BOATS_PER_DOT} boat-days, placed at random inside its patch; "
            "no dot is a boat.", F["it"], 12.5, LABEL)
    pg.line([gx, W_MM - gx], [55, 55], lw=.5)

    totals = []
    for i, name in enumerate(MONTHS):
        rows = ci.small_boats(f"{year}-{i + 1:02d}")
        total = sum(r[2] for r in rows)
        totals.append(total)
        s = ck.Sheet(box, width=round(pw / 25.4 * 100)).base()
        lon, lat, v = zip(*rows)
        s.stipple(lon, lat, [round(x / ci.BOATS_PER_DOT) for x in v], 9, "small", size=1.0, alpha=.9)
        s._soundings_draw()
        buf = io.BytesIO()
        s.fig.savefig(buf, format="png", dpi=DPI, facecolor=C["paper"])
        plt.close(s.fig)
        img = np.asarray(Image.open(buf).convert("RGB"))

        x = gx + (i % 3) * (pw + gut)
        y = top + (i // 3) * pitch
        ax = pg.fig.add_axes(pg.rect(x, y, pw, ph), zorder=1)
        ax.imshow(img, interpolation="lanczos")
        ax.axis("off")
        pg.neatline(x, y, pw, ph, box, bar=.7, gap=1.2, labels=False)
        pg.text(x + 3.5, y + 7.5, name.upper(), F["mono_med"], 8.5,
                path_effects=[pe.withStroke(linewidth=2.5, foreground=C["paper"])])
        pg.text(x + pw, y + ph + 6.8, f"{round(total, -2):,.0f} boat-days".replace(",", " "),
                F["it"], 8.5, LABEL, ha="right")
        print(f"  {name}: {total} boat-days, {len(rows)} patches")

    peak = max(range(12), key=lambda k: totals[k])
    x = gx + (peak % 3) * (pw + gut)
    y = top + (peak // 3) * pitch
    pg.text(x, y + ph + 6.8, "the busiest month", F["semi_it"], 8.5, C["small"])
    pg.text(W_MM / 2, H_MM - 6, SOURCE, F["mono"], 6.8,
            LABEL, ha="center")
    pg.save("year-of-boats")


def main():
    for old in ("season-hills", "four-clocks"):
        for ext in ("pdf", "svg", "png"):
            (OUT / f"{old}.{ext}").unlink(missing_ok=True)
    which = sys.argv[1:] or ["danish-waters", "year-of-boats"]
    if "danish-waters" in which:
        danish_waters()
    if "year-of-boats" in which:
        year_of_boats()


if __name__ == "__main__":
    main()
