"""The chart sheet every map on the site is drawn on: a Danish nautical chart.

Paper sea, buff land with an inked coast, pale blue shallows under 5 / 10 /
20 m, depth contours and small italic soundings from EMODnet Bathymetry
(scripts/fetch_bathymetry.py), and the fleets drawn the way a chart draws
things: cargo as a magenta wash (the colour charts give traffic routes),
ferries as red ink, fishing and small boats as stipple.

The image is the map and nothing else. The neatline, degree ticks, water names,
place names and the title cartouche are drawn over it in the browser by
site/js/chart.js, so text stays sharp and in the site's own fonts. That only
works because the projection is trivially linear: x is proportional to
longitude and y to latitude inside the sheet's box, with the aspect fixed at
cos(56 deg) — `project()` here and `chart.project` in site/js/chart.js, with each
image's box and size recorded in its page's manifest, site/media/charts/<page>.js.

    sheet = Sheet("denmark", width=1600)
    sheet.base()
    sheet.wash(lon, lat, weight, "cargo")
    sheet.save("i3-cargo")

Imported by the scripts/charts_*.py builders; run through
`uv run --project notes`, whose numpy + matplotlib + pillow are already here.
"""
import json
import math
import random
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt                                    # noqa: E402
from matplotlib.collections import LineCollection, PatchCollection  # noqa: E402
from matplotlib.patches import Polygon                               # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "media" / "charts"
CONTEXT = ROOT / "data" / "context"

# One palette, shared with site/css/site.css (--paper, --land, …). Change both.
C = {
    "paper": "#f4eddb", "land": "#eadcb2", "coast": "#4a3c26",
    "shoal": ("#bcd6dc", "#cfe2e4", "#e0ece9"),        # 0-5, 5-10, 10-20 m
    "contour": "#6f93a3", "sounding": "#5d7f90",
    "cargo": "#3b3934", "ferry": "#b02e1c", "fishing": "#1d6553",
    "small": "#24418f", "other": "#6b6f78", "ink": "#1d2a37",
    # the navigator's hand (round 4): what a person adds to a printed chart
    "pen": "#24418f", "redpen": "#b02e1c", "graphite": "#3b3934", "greenpen": "#1d6553",
}

# Named boxes: lon0, lon1, lat0, lat1.
BOXES = {
    "denmark": (7.6, 15.6, 53.9, 58.0),
    "inner":   (9.4, 13.2, 54.3, 56.9),     # the Belts, the Sound, the islands
}
ASPECT = 1 / math.cos(math.radians(56))
KM_PER_DEG_LAT = 111.2


def project(box, w, h, lon, lat):
    """Pixel (x, y) of a lon/lat on a w x h sheet of `box`, y down. The same two
    lines are chart.project in site/js/chart.js; scripts/test_charts.py holds
    both to known places so a flip in either language goes red."""
    x0, x1, y0, y1 = box
    return (lon - x0) / (x1 - x0) * w, (y1 - lat) / (y1 - y0) * h


def _gauss(a, sigma):
    if sigma <= 0:
        return a
    r = int(3 * sigma)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    a = np.apply_along_axis(lambda c: np.convolve(c, k, "same"), 0, a)
    return np.apply_along_axis(lambda c: np.convolve(c, k, "same"), 1, a)


_bathy = None


def bathy():
    """(depth grid in metres, positive down, NaN on land; lons; lats)."""
    global _bathy
    if _bathy is None:
        f = CONTEXT / "bathy_emodnet_0005.npz"
        if not f.exists():
            raise SystemExit(f"{f} is missing: run  uv run scripts/fetch_bathymetry.py")
        b = np.load(f)
        z, w, n, s = b["z"], float(b["west"]), float(b["north"]), float(b["step"])
        lons = w + s * (np.arange(z.shape[1]) + 0.5)
        lats = n - s * (np.arange(z.shape[0]) + 0.5)
        _bathy = (np.where(z < 0, -z, np.nan), lons, lats, (w, n, s))
    return _bathy


_land = None


def land_rings():
    global _land
    if _land is None:
        g = json.load(open(CONTEXT / "ne_10m_land.geojson"))
        rings = []
        for f in g["features"]:
            geom = f["geometry"]
            for p in geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]:
                ring = p[0]
                xs = [c[0] for c in ring]
                ys = [c[1] for c in ring]
                if max(xs) >= 2 and min(xs) <= 18 and max(ys) >= 52 and min(ys) <= 60:
                    rings.append(ring)
        _land = rings
    return _land


def is_sea(lon, lat):
    """True where EMODnet has water deeper than half a metre."""
    d, _, _, (w, n, s) = bathy()
    j = ((np.asarray(lon) - w) / s).astype(int)
    i = ((n - np.asarray(lat)) / s).astype(int)
    ok = (i >= 0) & (i < d.shape[0]) & (j >= 0) & (j < d.shape[1])
    out = np.zeros(np.shape(lon), bool)
    out[ok] = d[i[ok], j[ok]] > 0.5
    return out


class Sheet:
    def __init__(self, box="denmark", width=1600):
        self.box = BOXES[box] if isinstance(box, str) else tuple(box)
        x0, x1, y0, y1 = self.box
        self.w = width
        self.h = round(width * (y1 - y0) * ASPECT / (x1 - x0))
        self.fig = plt.figure(figsize=(self.w / 100, self.h / 100), dpi=100)
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(x0, x1)
        self.ax.set_ylim(y0, y1)
        self.ax.set_aspect(ASPECT)
        self.ax.axis("off")
        self.fig.patch.set_facecolor(C["paper"])
        self.ax.set_facecolor(C["paper"])
        self.km_per_px = (x1 - x0) * KM_PER_DEG_LAT / ASPECT / self.w
        self._wash = np.zeros((self.h, self.w))   # for keeping soundings off the lanes

    # ---- the chart itself -------------------------------------------------
    def base(self, soundings=True, contours=True):
        d, lons, lats, _ = bathy()
        self.ax.contourf(lons, lats, d, levels=[0, 5, 10, 20], colors=C["shoal"], zorder=1)
        if contours:
            self.ax.contour(lons, lats, _gauss(np.nan_to_num(d, nan=0), 1.2),
                            levels=[5, 10, 20, 50, 100, 200],
                            colors=C["contour"], linewidths=[.45, .4, .4, .32, .32, .32],
                            alpha=.8, zorder=2)
        self.ax.add_collection(PatchCollection(
            [Polygon(r) for r in land_rings()], facecolor=C["land"], edgecolor=C["coast"],
            lw=.55, zorder=20))
        self._soundings = soundings
        return self

    def _soundings_draw(self):
        d, lons, lats, _ = bathy()
        x0, x1, y0, y1 = self.box
        rng = np.random.default_rng(3)
        n = int(self.w * self.h / 2600)
        fs = max(4.2, self.w / 330)
        # sample only rows and columns inside the sheet, so a close-up gets as
        # many soundings per square centimetre as the whole of Denmark does
        ii = np.flatnonzero((lats > y0) & (lats < y1))
        jj = np.flatnonzero((lons > x0) & (lons < x1))
        for _ in range(n):
            i, j = rng.choice(ii), rng.choice(jj)
            v, x, y = d[i, j], lons[j], lats[i]
            if np.isnan(v) or v < 3 or not (x0 < x < x1 and y0 < y < y1):
                continue
            px, py = int((x - x0) / (x1 - x0) * (self.w - 1)), int((y1 - y) / (y1 - y0) * (self.h - 1))
            if self._wash[py, px] > .25:
                continue
            self.ax.text(x, y, f"{v:.0f}", fontsize=fs, color=C["sounding"], style="italic",
                         family="serif", ha="center", va="center", zorder=3, alpha=.85)

    # ---- data layers --------------------------------------------------------
    def wash(self, lon, lat, weight, color, pct=99.3, sigma_km=2.0, gamma=.6, alpha=.78, z=5):
        """Density as a transparent ink wash: every cell a soft spot, summed.

        Normalised at a high percentile of the non-empty pixels, so the lanes
        saturate and the open sea stays faint whatever the absolute counts."""
        x0, x1, y0, y1 = self.box
        h, *_ = np.histogram2d(lat, lon, bins=[self.h, self.w], range=[[y0, y1], [x0, x1]],
                               weights=weight)
        h = _gauss(h, sigma_km / self.km_per_px)[::-1]
        nz = h[h > h.max() * 1e-4]
        if not nz.size:
            return self
        v = np.clip(h / np.percentile(nz, pct), 0, 1) ** gamma
        self._wash = np.maximum(self._wash, v)
        rgba = np.zeros(v.shape + (4,))
        rgba[..., :3] = matplotlib.colors.to_rgb(C.get(color, color))
        rgba[..., 3] = v * alpha
        self.ax.imshow(rgba, extent=[x0, x1, y0, y1], aspect=ASPECT, zorder=z, interpolation="bilinear")
        return self

    def stipple(self, lon, lat, dots, radius_km, color, size=1.4, alpha=.8, seed=7, z=6):
        """dots[i] dots scattered at random over sea inside radius_km of each point.

        For small boats this IS the privacy grain: a cell's dots are placed by a
        seeded random draw, never by where a boat was, and only cells the export
        already floored at k >= 5 are ever passed in."""
        rnd = random.Random(seed)
        xs, ys = [], []
        dlat = radius_km / KM_PER_DEG_LAT
        for x, y, n in zip(lon, lat, dots):
            dlon = dlat * ASPECT
            for _ in range(int(n)):
                for _try in range(25):
                    a, r = rnd.uniform(0, 2 * math.pi), radius_km * math.sqrt(rnd.random())
                    px = x + math.cos(a) * r / KM_PER_DEG_LAT * ASPECT
                    py = y + math.sin(a) * r / KM_PER_DEG_LAT
                    if is_sea(np.array([px]), np.array([py]))[0]:
                        xs.append(px)
                        ys.append(py)
                        break
        # pen dots are never the same size twice
        sizes = size * np.random.default_rng(seed).lognormal(0, .35, len(xs))
        self.ax.scatter(xs, ys, s=sizes, c=C.get(color, color), alpha=alpha, lw=0, zorder=z)
        return len(xs)

    def tracks(self, segments, color, lw=.6, alpha=.9, z=22, hand=False):
        lc = LineCollection(segments, colors=C.get(color, color), lw=lw, alpha=alpha, zorder=z,
                            capstyle="round")
        if hand:                         # a pen, not a plotter: a slight tremor along the line
            lc.set_sketch_params(.7, 24, 2.5)
        self.ax.add_collection(lc)
        return self

    def flow(self, lon, lat, weight, color="graphite", pct=99.2, sigma_km=2.2, gamma=.6,
             strokes=34000, length_px=(5, 15), lw=.7, alpha=.85, seed=5, z=6):
        """Density as short pencil strokes laid ALONG the lanes, the way a hand
        shades a route: each stroke sits where the traffic is (drawn with
        probability by density) and points along the ridge of the density —
        perpendicular to its gradient — so the strokes run with the ships.
        (The idea is Kimi Code's, from its second-opinion sketch, 2026-10-01.)"""
        x0, x1, y0, y1 = self.box
        W, H = self.w, self.h
        h, *_ = np.histogram2d(lat, lon, bins=[H, W], range=[[y0, y1], [x0, x1]], weights=weight)
        D = _gauss(h, sigma_km / self.km_per_px)[::-1]
        nz = D[D > D.max() * 1e-4]
        if not nz.size:
            return self
        D = np.clip(D / np.percentile(nz, pct), 0, 1) ** gamma
        self._wash = np.maximum(self._wash, D)
        S = _gauss(D, 3.0)                       # the direction comes from a smoother field
        gy, gx = np.gradient(S)
        rng = np.random.default_rng(seed)
        p = D.ravel() / D.sum()
        idx = rng.choice(D.size, size=strokes, p=p)
        py, px = np.divmod(idx, W)
        px = px + rng.random(strokes); py = py + rng.random(strokes)
        iy, ix = py.astype(int).clip(0, H - 1), px.astype(int).clip(0, W - 1)
        ang = np.arctan2(gy[iy, ix], gx[iy, ix]) + np.pi / 2 + rng.normal(0, .22, strokes)
        L = rng.uniform(*length_px, strokes) * (.6 + .4 * D[iy, ix])
        dx, dy = np.cos(ang) * L / 2, np.sin(ang) * L / 2
        to_ll = lambda X, Y: np.c_[x0 + X / W * (x1 - x0), y1 - Y / H * (y1 - y0)]
        segs = [to_ll(np.array([a - c, a + c]), np.array([b - d, b + d])) for a, b, c, d in zip(px, py, dx, dy)]
        rgb = matplotlib.colors.to_rgb(C.get(color, color))
        cols = [(*rgb, a) for a in alpha * (.35 + .65 * D[iy, ix])]
        self.ax.add_collection(LineCollection(segs, colors=cols, lw=lw, zorder=z, capstyle="round"))
        return self

    def hatch(self, lon, lat, weight, color="graphite", pct=99.2, sigma_km=2.2, gamma=.55,
              layers=((38, 3.4, .16), (-50, 3.8, .45), (82, 4.4, .78)), lw=.55, alpha=.6, seed=3, z=6):
        """Density drawn the way a hand shades a chart: pencil strokes in parallel
        runs, laid only where the traffic is, a second direction over the busier
        water and a third over the lanes themselves (engraving's cross-hatch).
        Strokes lift and restart, wander a little and never quite line up.
        `layers` is (angle in degrees, spacing in px, density threshold)."""
        x0, x1, y0, y1 = self.box
        W, H = self.w, self.h
        h, *_ = np.histogram2d(lat, lon, bins=[H, W], range=[[y0, y1], [x0, x1]], weights=weight)
        D = _gauss(h, sigma_km / self.km_per_px)[::-1]
        nz = D[D > D.max() * 1e-4]
        if not nz.size:
            return self
        D = np.clip(D / np.percentile(nz, pct), 0, 1) ** gamma
        self._wash = np.maximum(self._wash, D)
        rng = np.random.default_rng(seed)
        diag = math.hypot(W, H)
        segs, cols = [], []
        rgb = matplotlib.colors.to_rgb(C.get(color, color))
        for angle, spacing, thresh in layers:
            k = -diag
            while k < diag:
                a = math.radians(angle + rng.normal(0, 1.4))
                dx, dy, nx, ny = math.cos(a), math.sin(a), -math.sin(a), math.cos(a)
                cx, cy = W / 2 + nx * k, H / 2 + ny * k
                ts = np.arange(-diag / 2, diag / 2, 1.5)
                px, py = cx + dx * ts, cy + dy * ts
                ok = (px >= 0) & (px < W - 1) & (py >= 0) & (py < H - 1)
                vals = np.zeros_like(ts)
                vals[ok] = D[py[ok].astype(int), px[ok].astype(int)]
                on = ok & (vals > thresh + rng.normal(0, .04, len(ts)))
                # the pencil lifts: chop long runs into strokes of 10-60 px
                lift = rng.random(len(ts)) < 1 / rng.uniform(6, 20)
                on &= ~lift
                edges = np.flatnonzero(np.diff(np.r_[0, on.astype(int), 0]))
                for st, en in zip(edges[::2], edges[1::2]):
                    if en - st < 3:
                        continue
                    wob = rng.normal(0, .5, en - st).cumsum() * .12
                    xs, ys = px[st:en] + nx * wob, py[st:en] + ny * wob
                    segs.append(np.c_[x0 + xs / W * (x1 - x0), y1 - ys / H * (y1 - y0)])
                    cols.append((*rgb, min(1, alpha * (.45 + vals[st:en].mean()))))
                k += spacing * rng.uniform(.75, 1.3)
        self.ax.add_collection(LineCollection(segs, colors=cols, lw=lw, zorder=z, capstyle="round"))
        return self

    # ---- output ---------------------------------------------------------------
    def save(self, name, quality=88):
        if getattr(self, "_soundings", False):
            self._soundings_draw()
        OUT.mkdir(parents=True, exist_ok=True)
        png = OUT / f"{name}.png"
        self.fig.savefig(png, facecolor=C["paper"], dpi=100)
        plt.close(self.fig)
        from PIL import Image
        Image.open(png).convert("RGB").save(OUT / f"{name}.webp", quality=quality, method=6)
        png.unlink()
        return {"src": f"media/charts/{name}.webp", "box": list(self.box), "w": self.w, "h": self.h}


def write_manifest(entries, page):
    """site/media/charts/<page>.js: window.SEAFOLK_CHARTS[id] = {src, box, w, h, ...}.
    A script tag, not fetch(), so the page still opens from file://."""
    body = json.dumps(entries, separators=(",", ":"))
    (OUT / f"{page}.js").write_text(
        f"// Written by scripts/charts_{page}.py. Do not edit.\n"
        f"window.SEAFOLK_CHARTS=Object.assign(window.SEAFOLK_CHARTS||{{}},{body});\n")
