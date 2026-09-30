/* Seafolk — the charts on "The sea by the hour", drawn as parts of a chart.
 *
 *   P1  four compass roses: a fleet's day with the hours round the rim
 *   P2  a tide table: one row a day, the sailing curve and the cargo line
 *   P3  a harbour plan: boats queueing to come in over the quay, and out
 *
 * Each draws into the responsive frame site/js/kit.js provides; every hue is a
 * CSS variable from site/css/site.css. The data is the page's own
 * <script type="application/json" id="data"> block, written by
 * scripts/site_data/pulse.py. Nothing is fetched.
 *
 * Geometry of P1: midnight at the top, hours clockwise, the ray for hour h
 * centred on h * 15 degrees, its length linear in the hour's share of the
 * fleet's own day from a hub to PEAK at the inner rim. scripts/render_clocks.py
 * and render_posters.py read the same "clocks" block.
 */
(function () {
"use strict";

const D = JSON.parse(document.getElementById("data").textContent);
const ink = kit.ink;
const MONO = '"IBM Plex Mono", ui-monospace, monospace';
const SERIF = '"Source Serif 4", Georgia, serif';

/* key, the reader's word, the fill token, the text token */
const FLEETS = [["sailing", "sailing boats", "accent", "accent-tx"],
                ["ferries", "ferries", "ferry", "ferry"],
                ["cargo", "cargo ships", "cargo", "cargo"],
                ["fishing", "fishing boats", "fishing", "fishing"]];
const NIGHT = [22, 23, 0, 1, 2, 3, 4];       // sql/24's night, as pulse.py's
const FLAT_DAY = 100 / 24;
const FLAT_WEEK = 100 / 168;
const DOW = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
             "Saturday", "Sunday"];
const hhmm = h => String(h).padStart(2, "0") + ":00";
const hh = h => String(h).padStart(2, "0");
const text = (g, x, y, str, font, fill, anchor) => g.append("text")
  .attr("x", x).attr("y", y).attr("text-anchor", anchor || "middle")
  .attr("fill", fill).style("font", font).text(str);


/* ====================== P1 — four compass roses ========================= */
const rad = deg => (deg - 90) * Math.PI / 180;
const at = (cx, cy, deg, r) => [cx + r * Math.cos(rad(deg)), cy + r * Math.sin(rad(deg))];
const poly = pts => "M" + pts.map(p => p.join(",")).join("L") + "Z";
const arc = (cx, cy, r0, r1, a0, a1) => {    // a ring segment, a0 < a1 in degrees
  const big = a1 - a0 > 180 ? 1 : 0;
  const [x1, y1] = at(cx, cy, a0, r1), [x2, y2] = at(cx, cy, a1, r1);
  const [x3, y3] = at(cx, cy, a1, r0), [x4, y4] = at(cx, cy, a0, r0);
  return `M${x1},${y1}A${r1},${r1} 0 ${big} 1 ${x2},${y2}L${x3},${y3}`
       + `A${r0},${r0} 0 ${big} 0 ${x4},${y4}Z`;
};

function moon(g, x, y, s, fill) {
  g.append("path").attr("fill", fill).attr("d",
    `M${x + s * .3},${y - s * .95}A${s},${s} 0 1 0 ${x + s * .3},${y + s * .95}`
    + `A${s * .8},${s * .8} 0 1 1 ${x + s * .3},${y - s * .95}Z`);
}
function sun(g, x, y, s, fill) {
  g.append("circle").attr("cx", x).attr("cy", y).attr("r", s * .48).attr("fill", fill);
  for (let k = 0; k < 8; k++) {
    const a = k * Math.PI / 4;
    g.append("line").attr("stroke", fill).attr("stroke-width", 1.3).attr("stroke-linecap", "round")
      .attr("x1", x + Math.cos(a) * s * .72).attr("y1", y + Math.sin(a) * s * .72)
      .attr("x2", x + Math.cos(a) * s * 1.05).attr("y2", y + Math.sin(a) * s * 1.05);
  }
}

/* One compass rose: a fleet's day as 24 two-tone points inside a rim whose
 * night is inked in, with the hours round the outside. Draws into `d` and
 * returns what the clock hand and the hover need. */
function rose(d, cx, cy, R, vals, col, PEAK, small) {
  const band = Math.max(4, R * .075), rim = R - band;
  const hub = R * .1, top = rim - Math.max(3, R * .05);
  const rv = v => hub + v / PEAK * (top - hub);

  // the rim: a double ring, the night filled in ink like the dark half of a
  // chart's border bar, a tick at every hour and quarter, the night in the dial
  d.append("path").attr("d", arc(cx, cy, hub, rim, 21.5 * 15, 360 + 4.5 * 15))
    .attr("fill", ink("sea-ink")).attr("fill-opacity", .09);
  d.append("path").attr("d", arc(cx, cy, rim, R, 21.5 * 15, 360 + 4.5 * 15)).attr("fill", ink("ink"));
  [R, rim].forEach(r => d.append("circle").attr("cx", cx).attr("cy", cy).attr("r", r)
    .attr("fill", "none").attr("stroke", ink("ink")).attr("stroke-width", r === R ? 1.3 : .8));
  for (let q = 0; q < 96; q++) {
    const a = (q + 2) * 3.75, hour = q % 4 === 0;     // boundaries between hour rays
    const [x1, y1] = at(cx, cy, a, rim), [x2, y2] = at(cx, cy, a, rim - (hour ? 5 : 2.5));
    d.append("line").attr("x1", x1).attr("y1", y1).attr("x2", x2).attr("y2", y2)
      .attr("stroke", ink("ink")).attr("stroke-width", hour ? .8 : .5).attr("opacity", .7);
  }
  d.append("circle").attr("cx", cx).attr("cy", cy).attr("r", rv(FLAT_DAY))   // a day with no rhythm
    .attr("fill", "none").attr("stroke", ink("ref")).attr("stroke-width", 1.1)
    .attr("stroke-dasharray", "3 3");

  // a kite per hour, shoulders at ±7 degrees a little over half way out, one
  // half solid and one half pale, the way a compass rose prints its points
  const kite = hour => {
    const a = hour * 15, len = rv(vals[hour]), sh = Math.max(hub * 1.05, len * .5);
    return [[cx, cy], at(cx, cy, a - 7, sh), at(cx, cy, a, len), at(cx, cy, a + 7, sh)];
  };
  vals.forEach((v, hour) => {
    const [c, l, tip, r] = kite(hour);
    d.append("path").attr("d", poly([c, l, tip])).attr("fill", col);
    d.append("path").attr("d", poly([c, tip, r])).attr("fill", col)
      .attr("fill-opacity", .3).attr("stroke", col).attr("stroke-width", .7)
      .attr("stroke-linejoin", "round");
  });
  const lit = d.append("path").attr("fill", "none").attr("stroke", ink("ink"))
    .attr("stroke-width", 1.4).attr("stroke-linejoin", "round").style("pointer-events", "none");
  d.append("circle").attr("cx", cx).attr("cy", cy).attr("r", hub * .55)
    .attr("fill", ink("surface")).attr("stroke", ink("ink")).attr("stroke-width", 1);
  d.append("circle").attr("cx", cx).attr("cy", cy).attr("r", 1.6).attr("fill", ink("ink"));

  // the hours round the outside; the moon at midnight, the sun at noon
  const nr = R + (small ? 9 : 12);
  (small ? [6, 18] : [3, 6, 9, 15, 18, 21]).forEach(hour => {
    const [x, y] = at(cx, cy, hour * 15, nr);
    kit.halo(text(d, x, y, hh(hour), `500 ${small ? 8.5 : 10}px ${MONO}`, ink("label")))
      .attr("dominant-baseline", "central");
  });
  moon(d, cx, cy - nr, small ? 4.5 : 6, ink("sea-ink"));
  sun(d, cx, cy + nr, small ? 4.5 : 6, ink("accent"));

  const hand = d.append("g").attr("opacity", 0).style("pointer-events", "none");
  hand.append("line").attr("stroke", ink("ink")).attr("stroke-width", 1.6).attr("stroke-linecap", "round");
  hand.append("circle").attr("r", 2.6).attr("fill", ink("ink"));
  return { cx, cy, R, hub, rim, rv, kite, lit, hand };
}

const PEAK = d3.max(FLEETS, f => d3.max(D.clocks[f[0]])) * 1.04;

/* The clock every rose on the page keeps: a hand sweeps the day in DAY_MS,
 * lighting the hour under it, and each readout says the time. It runs while
 * any rose is on screen, a click on a rose pauses it, and with reduced motion
 * there is no hand at all — the roses are the whole picture. */
const clock = (function () {
  const DAY_MS = 16000, dials = {}, readouts = [], seen = new Map();
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let last = reduced ? null : 0, t0 = null, raf = 0, paused = false;
  function show(t) {
    last = t;
    const hour = t === null ? -1 : Math.round(t) % 24;
    Object.values(dials).flat().forEach(d => {
      d.lit.attr("d", hour < 0 ? null : poly(d.kite(hour)));
      if (t === null) { d.hand.attr("opacity", 0); return; }
      const [x1, y1] = at(d.cx, d.cy, t * 15, d.hub * .55);
      const [x2, y2] = at(d.cx, d.cy, t * 15, d.rim - 2);
      d.hand.attr("opacity", 1).select("line").attr("x1", x1).attr("y1", y1).attr("x2", x2).attr("y2", y2);
      d.hand.select("circle").attr("cx", x2).attr("cy", y2);
    });
    readouts.forEach(([el, fmt]) => {
      el.style.display = t === null ? "none" : "";
      el.innerHTML = t === null ? "" : fmt(hour, paused);
    });
  }
  const visible = () => [...seen.values()].some(Boolean);
  function frame(now) {
    if (!visible() || paused) { raf = 0; return; }
    if (t0 === null) t0 = now - last / 24 * DAY_MS;
    show((now - t0) / DAY_MS * 24 % 24);
    raf = requestAnimationFrame(frame);
  }
  const go = () => { if (!raf && visible() && !paused) { t0 = null; raf = requestAnimationFrame(frame); } };
  return {
    /* a set of roses under a name, replaced whenever that figure redraws */
    set(name, list) { dials[name] = list; show(last); },
    watch(el, readout, fmt) {
      if (readout) readouts.push([readout, fmt]);
      if (reduced) { show(null); return; }
      new IntersectionObserver(([e]) => { seen.set(el, e.isIntersecting); go(); }).observe(el);
      el.addEventListener("click", () => { paused = !paused; show(last); go(); });
      show(last);
    },
  };
})();

function roses() {
  kit.figure(document.getElementById("c-p1"),
    { ratio: 0.31, ratioNarrow: 1.25,
      margin: { top: 4, right: 0, bottom: 4, left: 0 },
      marginNarrow: { top: 4, right: 0, bottom: 4, left: 0 } },
    (g, w, h, narrow) => {
      const cols = narrow ? 2 : 4, rows = 4 / cols;
      const cw = w / cols, chh = h / rows;
      const pad = narrow ? 16 : 22, foot = narrow ? 44 : 50;
      const R = Math.min(cw / 2 - pad, (chh - foot - 2 * pad) / 2);

      const dials = FLEETS.map(([key, label, fillTok, txTok], i) => {
        const cx = (i % cols) * cw + cw / 2;
        const cy = Math.floor(i / cols) * chh + pad + R;
        const vals = D.clocks[key], d = g.append("g");
        const r = rose(d, cx, cy, R, vals, ink(fillTok), PEAK, narrow);

        // the name, and the one number the headline is about
        const ny = cy + R + (narrow ? 25 : 34);
        text(d, cx, ny, label, `italic 600 ${narrow ? 14 : 17}px ${SERIF}`, ink(txTok));
        const night = d3.sum(NIGHT, hour => vals[hour]);
        const nt = text(d, cx, ny + (narrow ? 16 : 21), "", `500 ${narrow ? 10.5 : 12.5}px ${MONO}`, ink("label"))
          .style("letter-spacing", ".06em");
        nt.append("tspan").attr("fill", ink(txTok)).style("font-weight", 600).text(`${night.toFixed(0)} %`);
        nt.append("tspan").text(" at night");
        return { ...r, key, label, colour: ink(txTok) };
      });
      clock.set("p1", dials);

      kit.hover(g, w, h, (px, py) => {
        for (const d of dials) {
          const dx = px - d.cx, dy = py - d.cy;
          if (Math.hypot(dx, dy) > d.R + 6) continue;
          const a = (Math.atan2(dx, -dy) * 180 / Math.PI + 360) % 360;
          const hour = Math.round(a / 15) % 24, v = D.clocks[d.key][hour];
          const [x, y] = at(d.cx, d.cy, hour * 15, d.rv(v));
          return { x, y, color: d.colour, text: `${d.label}\n${hhmm(hour)}\n${v} % of the day` };
        }
        return null;
      });
    });
  clock.watch(document.getElementById("c-p1"), document.getElementById("k-p1"),
    (hour, paused) => `<span>${hhmm(hour)} in Denmark</span><b>${paused ? "paused — click to go on" : "click to pause"}</b>`);

  kit.table(document.getElementById("t-p1"), ["hour", ...FLEETS.map(f => f[1])],
    d3.range(24).map(hour => [hhmm(hour),
      ...FLEETS.map(([key]) => D.clocks[key][hour].toFixed(2) + " %")]));
}


/* ============ the hero: the South Funen waters, and a rose on them ======= */
/* The sheet (scripts/charts_pulse.py) carries July's small boats as stipple.
 * On the water, where a chart prints its compass rose, this prints the
 * sailing fleet's day. Its SVG is sized in CSS pixels and redrawn on resize. */
const ROSE_AT = { lon: 11.2, lat: 54.97 };
function hero() {
  const s = chart.sheet(document.getElementById("c-hero"), "pulse-hero", { eager: true,
    tag: "July 2025 · small boats",
    names: ["Storebælt",
      { name: "Det Sydfynske Øhav", lon: 10.5, lat: 54.93, kind: "water" },
      { name: "Østersøen", lon: 11.85, lat: 54.54, kind: "water", big: 1 },
      { name: "Sønderborg", lon: 9.79, lat: 54.91, kind: "place" },
      { name: "Svendborg", lon: 10.61, lat: 55.06, kind: "place" }],
    alt: "A nautical chart of the waters south of Funen, dotted with July's small boats, with the sailing boats' day printed on it as a compass rose" });
  if (!s) return;
  const ns = "http://www.w3.org/2000/svg";
  const svg = d3.select(s.box.appendChild(document.createElementNS(ns, "svg")))
    .attr("class", "frame").style("pointer-events", "auto");
  const draw = () => {
    const W = s.box.clientWidth, H = s.box.clientHeight;
    if (!W) return;
    svg.attr("viewBox", `0 0 ${W} ${H}`).selectAll("*").remove();
    const [ix, iy] = s.xy(ROSE_AT.lon, ROSE_AT.lat);
    const cx = ix / s.meta.w * W, cy = iy / s.meta.h * H, R = Math.max(40, H * .17);
    const g = svg.append("g");
    g.append("circle").attr("cx", cx).attr("cy", cy).attr("r", R + 3)
      .attr("fill", ink("surface")).attr("fill-opacity", .72);
    const r = rose(g, cx, cy, R, D.clocks.sailing, ink("accent"), PEAK, W < 640);
    kit.halo(text(g, cx, cy + R + (W < 640 ? 22 : 30), "the small boats' day",
      `italic 600 ${W < 640 ? 11 : 14}px ${SERIF}`, ink("accent-tx")));
    clock.set("hero", [r]);
  };
  if (s.img.complete) draw(); else s.img.addEventListener("load", draw);
  new ResizeObserver(draw).observe(s.box);
  clock.watch(s.box, document.getElementById("k-hero"),
    hour => `<span>${hhmm(hour)}</span><b>${D.clocks.sailing[hour].toFixed(1)} % of the sailing day</b>`);
}


/* ===================== P2 — the week as a tide table ==================== */
function week() {
  const W = D.week;
  const day = (key, d) => W[key].slice(24 * d, 24 * d + 24);
  kit.figure(document.getElementById("c-p2"),
    { ratio: 0.56, ratioNarrow: 1.1,
      margin: { top: 30, right: 70, bottom: 52, left: 96 },
      marginNarrow: { top: 26, right: 44, bottom: 52, left: 38 } },
    (g, w, h, narrow) => {
      const rowH = h / 7.4, base = d => rowH * 1.4 + d * rowH;
      const amp = d3.scaleLinear([0, d3.max(W.sailing)], [0, rowH * 1.7]);
      const x = i => (i + .5) / 24 * w;
      const hx = hour => hour / 24 * w;

      // the hours across the top, as a tide table heads its columns
      [0, 6, 12, 18, 24].forEach(hour => {
        text(g, hx(hour), -14, hh(hour), `500 ${narrow ? 10 : 11}px ${MONO}`, ink("label"),
             hour ? hour === 24 ? "end" : "middle" : "start");
        if (hour % 24) g.append("line").attr("x1", hx(hour)).attr("x2", hx(hour))
          .attr("y1", -6).attr("y2", base(6)).attr("stroke", ink("hairline"));
      });
      text(g, w + 10, -14, narrow ? "top" : "top hour", `italic 400 ${narrow ? 11 : 13}px ${SERIF}`,
           ink("label"), "start");

      for (let d = 0; d < 7; d++) {
        const weekend = d >= 5, row = g.append("g").attr("transform", `translate(0,${base(d)})`);
        const s = day("sailing", d), c = day("cargo", d);
        const pts = [s[0], ...s, s[23]];             // run the hill to both edges
        const ax = i => i === 0 ? 0 : i === 25 ? w : x(i - 1);
        const hill = d3.area().x((v, i) => ax(i)).y1(v => -amp(v)).y0(0).curve(d3.curveMonotoneX);
        row.append("path").attr("d", hill(pts)).attr("fill", ink("surface"));
        row.append("path").attr("d", hill(pts)).attr("fill", ink("accent"))
          .attr("fill-opacity", weekend ? .42 : .16);
        row.append("line").attr("x1", 0).attr("x2", w).attr("stroke", ink("ink")).attr("stroke-width", .8);
        row.append("line").attr("x1", 0).attr("x2", w).attr("y1", -amp(FLAT_WEEK)).attr("y2", -amp(FLAT_WEEK))
          .attr("stroke", ink("ref")).attr("stroke-dasharray", "3 3");
        row.append("path").attr("d", hill.lineY1()(pts)).attr("fill", "none")
          .attr("stroke", ink(weekend ? "accent" : "accent-tx")).attr("stroke-width", weekend ? 2.4 : 1.5)
          .attr("stroke-linejoin", "round");
        row.append("path").attr("d", hill.lineY1()([c[0], ...c, c[23]])).attr("fill", "none").attr("stroke", ink("cargo"))
          .attr("stroke-width", 1.6);

        // the day, and its high water
        text(row, -12, -5, narrow ? DOW[d].slice(0, 3) : DOW[d],
             `italic ${weekend ? 600 : 400} ${narrow ? 13 : 16}px ${SERIF}`,
             ink(weekend ? "accent-tx" : "ink"), "end");
        const top = d3.maxIndex(s);
        row.append("circle").attr("cx", x(top)).attr("cy", -amp(s[top])).attr("r", weekend ? 3.2 : 2.4)
          .attr("fill", ink(weekend ? "accent" : "accent-tx"));
        text(row, w + 10, -5, s[top].toFixed(1) + (narrow ? "" : " %"),
             `${weekend ? 600 : 400} ${narrow ? 11 : 13}px ${MONO}`,
             ink(weekend ? "accent-tx" : "label"), "start");
      }

      // direct labels on the Monday row, over its own line where nothing else is
      const m = day("sailing", 0), mc = day("cargo", 0);
      kit.halo(text(g, x(8), base(0) - amp(m[8]) - 10, "sailing boats",
        `600 ${narrow ? 12 : 14}px ${SERIF}`, ink("accent-tx"), "end"));
      kit.halo(text(g, x(21), base(0) - amp(mc[21]) - 8, "cargo ships",
        `600 ${narrow ? 12 : 14}px ${SERIF}`, ink("cargo"), "middle"));

      // the one annotation: a mark down from Sunday's hill to a line of text
      const top = d3.maxIndex(W.sailing), sx = x(top % 24);
      g.append("line").attr("x1", sx).attr("x2", sx).attr("y1", base(6) + 4).attr("y2", base(6) + 22)
        .attr("stroke", ink("accent-tx"));
      kit.note(g, { x: sx, y: base(6) + 38, anchor: "middle", color: ink("accent-tx"),
        size: narrow ? 12 : 13.5,
        text: `${DOW[top / 24 | 0]} ${hhmm(top % 24)}: the busiest hour of the sailing week` });

      kit.hover(g, w, h, (px, py) => {
        const d = Math.max(0, Math.min(6, Math.round((py - rowH * 1.4) / rowH + .35)));
        const i = Math.max(0, Math.min(23, Math.floor(px / w * 24))), slot = 24 * d + i;
        return { x: x(i), y: base(d) - amp(W.sailing[slot]), color: ink("accent"),
                 text: `${DOW[d]} ${hhmm(i)}\nsailing boats ${W.sailing[slot].toFixed(2)} %\n`
                     + `cargo ships ${W.cargo[slot].toFixed(2)} %` };
      });
    });

  kit.table(document.getElementById("t-p2"),
    ["day", "sailing boats, % of the week", "cargo ships, % of the week", "sailing boats, busiest hour"],
    DOW.map((name, d) => [name,
      d3.sum(day("sailing", d)).toFixed(1) + " %", d3.sum(day("cargo", d)).toFixed(1) + " %",
      hhmm(d3.maxIndex(day("sailing", d)))]));
}


/* ======================= P3 — the harbour plan ========================== */
/* A hull seen from above, bow up, centred on 0,0: a pointed bow, a square
 * transom. The same outline is inlined in the page's key under P3. */
const hull = (L, W) => `M0,${-L / 2}C${W * .5},${-L * .28} ${W * .5},${-L * .05} ${W * .5},${L * .12}`
  + `L${W * .4},${L / 2}L${-W * .4},${L / 2}L${-W * .5},${L * .12}`
  + `C${-W * .5},${-L * .05} ${-W * .5},${-L * .28} 0,${-L / 2}Z`;

function harbour() {
  const H = D.harbour;
  const maxA = d3.max(H.appeared), maxV = d3.max(H.vanished);
  kit.figure(document.getElementById("c-p3"),
    { ratio: 0.5, ratioNarrow: 1.0,
      margin: { top: 8, right: 4, bottom: 8, left: 4 },
      marginNarrow: { top: 50, right: 6, bottom: 8, left: 6 } },
    (g, w, h, narrow) => {
      const moleH = narrow ? 20 : 26;
      const unit = (h - moleH) / (maxA + 1.2 + maxV + .8);
      const moleY = (maxA + 1.2) * unit, moleB = moleY + moleH;
      const step = w / 24, cx = i => (i + .5) * step;
      const hl = unit * .86, hwid = Math.min(step * .62, hl * .42);

      // the plan: open water above, the basin below in shoal blue, the quay
      g.append("rect").attr("y", moleB).attr("width", w).attr("height", h - moleB)
        .attr("fill", ink("shoal")).attr("opacity", .75);

      // the stacks: one hull a boat, stacked out from the quay, the last one
      // cut where the average ends. The first `near` boats' worth is solid —
      // they sailed; the rest are ghosts. Two clipped copies of one column.
      const id = "p3" + Math.random().toString(36).slice(2, 7);
      const stack = (vals, near, sign) => vals.forEach((v, i) => {
        const band = (a, b) => sign > 0 ? [moleB + a * unit, (b - a) * unit]
                                         : [moleY - b * unit, (b - a) * unit];
        [[0, near[i], true], [near[i], v, false]].forEach(([a, b, solid], j) => {
          const clip = `${id}-${sign > 0 ? "o" : "i"}${i}-${j}`, [y0, bh] = band(a, b);
          g.append("clipPath").attr("id", clip).append("rect")
            .attr("x", cx(i) - step / 2).attr("width", step).attr("y", y0).attr("height", bh);
          const col = g.append("g").attr("clip-path", `url(#${clip})`);
          for (let k = Math.floor(a); k < Math.ceil(b); k++) {
            const y = sign > 0 ? moleB + (k + .5) * unit : moleY - (k + .5) * unit;
            col.append("path").attr("d", hull(hl, hwid))
              .attr("transform", `translate(${cx(i)},${y})${sign > 0 ? "" : " scale(1,-1)"}`)
              .attr("fill", solid ? ink("accent") : ink("surface"))
              .attr("stroke", ink("accent")).attr("stroke-width", solid ? .8 : 1.1)
              .attr("stroke-dasharray", solid ? null : "2.2 1.6");
          }
        });
      });
      stack(H.appeared, H.from_ring, -1);
      stack(H.vanished, H.to_ring, 1);

      // the point: one hour holds both the longest queue in and the longest out
      const pin = d3.maxIndex(H.appeared);
      const bx = cx(pin) - step / 2 + 1, by = moleY - H.appeared[pin] * unit - 6;
      const bh = moleB + H.vanished[pin] * unit + 6 - by;
      g.append("rect").attr("x", bx).attr("y", by).attr("width", step - 2).attr("height", bh)
        .attr("fill", "none").attr("stroke", ink("ink")).attr("stroke-width", 1.1)
        .attr("stroke-dasharray", "4 3");
      // the quay, with the hours along it like numbers painted on bollards
      g.append("rect").attr("y", moleY).attr("width", w).attr("height", moleH)
        .attr("fill", ink("land")).attr("stroke", ink("ink")).attr("stroke-width", 1.2);
      d3.range(24).forEach(i => {
        const show = narrow ? i % 6 === 0 : i % 3 === 0;
        if (show) text(g, cx(i), moleY + moleH / 2, hh(i), `500 ${narrow ? 9 : 10.5}px ${MONO}`,
                       ink("ink")).attr("dominant-baseline", "central");
        else g.append("circle").attr("cx", cx(i)).attr("cy", moleY + moleH / 2).attr("r", 1.3)
          .attr("fill", ink("ink")).attr("opacity", .5);
      });

      // which way is which, lettered like water names
      const wfont = `italic 500 ${narrow ? 12 : 15}px ${SERIF}`;
      kit.halo(text(g, 6, moleY - (narrow ? 2.4 : 2.2) * unit, "coming in ↓", wfont, ink("sea-ink"), "start"))
        .style("letter-spacing", ".06em");
      text(g, 6, moleB + (narrow ? 2.6 : 2.4) * unit, "going out ↑", wfont, ink("sea-ink"), "start")
        .style("letter-spacing", ".06em");
      if (!narrow) {
        const tag = g.append("g").attr("transform", `translate(${w - 6},${14})`);
        const t = text(tag, -10, 0, H.place.toUpperCase(), `500 11px ${MONO}`, ink("ink"), "end")
          .attr("dominant-baseline", "central").style("letter-spacing", ".2em");
        const bb = t.node().getBBox();
        tag.insert("rect", "text").attr("x", bb.x - 8).attr("y", bb.y - 5)
          .attr("width", bb.width + 16).attr("height", bb.height + 10)
          .attr("fill", ink("surface")).attr("stroke", ink("ink"));
      }

      kit.note(g, narrow
        ? { x: 0, y: -36, color: ink("ink"), size: 12.5,
            text: ["noon, the dashed column: the most boats", "come in and the most go out"] }
        : { x: bx, y: by + 2, dx: -16, dy: 6, anchor: "end", leader: true, color: ink("ink"), size: 14,
            text: ["noon: the most boats come in", "and the most boats go out"] });

      kit.hover(g, w, h, px => {
        const i = Math.max(0, Math.min(23, Math.floor(px / step)));
        return { x: cx(i), y: moleY, color: ink("accent"),
                 text: `${hhmm(i)}\n${H.appeared[i]} came in, ${H.from_ring[i]} of them from next door\n`
                     + `${H.vanished[i]} went out, ${H.to_ring[i]} of them to next door` };
      });
    });

  kit.table(document.getElementById("t-p3"),
    ["hour", "appeared", "of those, from next door", "disappeared", "of those, to next door"],
    d3.range(24).map(i => [hhmm(i), H.appeared[i], H.from_ring[i], H.vanished[i], H.to_ring[i]]));
}


hero();
roses();
week();
harbour();
})();
