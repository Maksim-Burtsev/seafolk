/* Seafolk — the charts on the story page.
 *
 * One function per figure, each drawing into the responsive frame that
 * site/js/kit.js provides. No chart here knows a colour literal: every hue is
 * a CSS variable from site/css/site.css, read at draw time, so light and dark
 * are the same code.
 *
 * The data comes from the page's own <script type="application/json" id="data">
 * block, written by scripts/site_data/index.py. Nothing is fetched.
 */
(function () {
"use strict";

const D = JSON.parse(document.getElementById("data").textContent);
const ink = kit.ink;
const MONTH = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"];
const sp = n => Math.round(n).toLocaleString("en-GB").replace(/,/g, " ");

/* Day of the year -> a date, on a non-leap calendar. Used for the x axis of
 * chart I1 and for its readout; the six years are drawn on one calendar and a
 * leap day is a fifth of a pixel at this width. */
const DOY = d3.range(0, 12).map(m => 1 + d3.timeDay.count(
  new Date(2001, 0, 1), new Date(2001, m, 1)));
const dayLabel = doy => {
  const d = new Date(2001, 0, doy);
  return `${d.getDate()} ${MONTH[d.getMonth()]}`;
};

/* Split a series into runs of consecutive x, so a line breaks over an unloaded
 * stretch of calendar instead of being drawn straight across it. */
const runs = (pts, gap) => pts.reduce((acc, p, i) => {
  if (i && p[0] - pts[i - 1][0] <= gap) acc[acc.length - 1].push(p);
  else acc.push([p]);
  return acc;
}, []);


/* ============================ I1 — the season ============================ */
function season() {
  const years = Object.keys(D.season).sort();
  const line = d3.line().x(d => x(d[0])).y(d => y(d[1]));
  let x, y;

  kit.figure(document.getElementById("c-i1"),
    { ratio: 0.46, ratioNarrow: 0.8, margin: { top: 26, right: 44, bottom: 42, left: 52 },
      marginNarrow: { right: 38, left: 44 } },
    (g, w, h, narrow) => {
      x = d3.scaleLinear([1, 366], [0, w]);
      y = d3.scaleLinear([0, d3.max(years, k => d3.max(D.season[k], d => d[1])) * 1.06], [h, 0]);

      // the empty half of the calendar, said twice: once as a shaded band and
      // once in words. Nothing is drawn on top of it.
      [[1, DOY[2] + 30], [DOY[10], 366]].forEach(([a, b]) => g.append("rect")
        .attr("x", x(a)).attr("width", x(b) - x(a)).attr("y", 0).attr("height", h)
        .attr("fill", ink("hairline")).attr("opacity", 0.4));

      kit.axis(g, y, { side: "left", ticks: 4, grid: w, fmt: sp,
                       title: "boats out that day" });
      kit.axis(g, x, { side: "bottom", at: h, values: [DOY[0], DOY[3], DOY[6], DOY[9]],
                       fmt: d => MONTH[DOY.indexOf(d)].slice(0, 3) });

      // Only the first year and the last are drawn as lines a reader is meant
      // to follow. The four in between are hairlines: they say "and it went up
      // like this in between" without four more greys to tell apart.
      const ends = [];
      years.forEach((k, i) => {
        const first = i === 0, last = i === years.length - 1;
        const strong = first || last;
        const colour = last ? ink("accent") : first ? ink("ink") : ink("pale");
        runs(D.season[k], 1).forEach(run => g.append("path").attr("d", line(run))
          .attr("fill", "none").attr("stroke", colour)
          .attr("stroke-width", last ? 2.8 : first ? 2 : 1).attr("stroke-linecap", "round"));
        const peak = d3.greatest(D.season[k], d => d[1]);
        if (strong) g.append("circle").attr("cx", x(peak[0])).attr("cy", y(peak[1]))
          .attr("r", 3).attr("fill", colour);
        ends.push({ y: y(peak[1]), x: x(peak[0]), text: k, color: colour,
                    size: strong ? 14 : 11, weight: strong ? 600 : 400 });
      });
      ends.sort((a, b) => a.y - b.y);
      for (let i = 1; i < ends.length; i++)
        ends[i].y = Math.max(ends[i].y, ends[i - 1].y + 15);
      kit.halo(g.selectAll(null).data(ends).join("text")
        .attr("x", d => d.x + 8).attr("y", d => d.y).attr("dy", "0.34em")
        .attr("fill", d => d.color)
        .style("font", d => `${d.weight} ${d.size}px Karla, ui-sans-serif, sans-serif`)
        .text(d => d.text));

      // inside the shaded winter band, clear of every line
      kit.note(g, { x: x(6), y: y(0), dy: -Math.max(h * 0.44, 44),
        text: narrow ? ["November", "to March:", "almost", "nobody out"]
                     : ["November to March:", "almost nobody is out"] });

      const flat = years.flatMap(k => D.season[k].map(d => [d[0], d[1], k]));
      kit.hover(g, w, h, (px, py) => {
        const d = d3.least(flat, p => (x(p[0]) - px) ** 2 + (y(p[1]) - py) ** 2);
        return Math.abs(x(d[0]) - px) > 40 ? null
          : { x: x(d[0]), y: y(d[1]), color: ink("accent"),
              text: `${dayLabel(d[0])} ${d[2]}\n${sp(d[1])} boats out` };
      });
    });

  // a 366-row table is not a table anyone reads: the months are.
  kit.table(document.getElementById("t-i1"),
    ["boats out, average per day", ...MONTH.map(m => m.slice(0, 3))],
    years.map(k => {
      const by = d3.rollup(D.season[k], v => d3.mean(v, d => d[1]),
                           d => d3.bisect(DOY, d[0]) - 1);
      return [k, ...d3.range(12).map(m => by.has(m) ? sp(by.get(m)) : "—")];
    }));
}


/* ====================== I2 — the fleet and the control ================== */
function fleet() {
  const F = D.fleet;
  kit.figure(document.getElementById("c-i2"),
    { ratio: 0.46, ratioNarrow: 0.85, margin: { top: 26, right: 96, bottom: 40, left: 54 },
      marginNarrow: { right: 30, left: 48 } },
    (g, w, h, narrow) => {
      const x = d3.scaleBand(F.years.map(String), [0, w]).padding(0.34);
      const y = d3.scaleLinear([0, d3.max(F.small_boats) * 1.1], [h, 0]);
      kit.axis(g, y, { side: "left", ticks: 4, grid: w, fmt: sp,
                       title: "boats and ships heard, March to August" });
      kit.axis(g, x, { side: "bottom", at: h });

      g.selectAll(null).data(F.years).join("rect")
        .attr("x", d => x(String(d))).attr("width", x.bandwidth())
        .attr("y", (d, i) => y(F.small_boats[i]))
        .attr("height", (d, i) => h - y(F.small_boats[i]))
        .attr("fill", ink("accent"));
      [0, F.years.length - 1].forEach(i => kit.halo(g.append("text")
        .attr("x", x(String(F.years[i])) + x.bandwidth() / 2)
        .attr("y", y(F.small_boats[i]) - 8).attr("text-anchor", "middle")
        .attr("fill", ink("accent-tx"))
        .style("font", '500 13px "IBM Plex Mono", ui-monospace, monospace')
        .text(sp(F.small_boats[i]))));

      const mid = d => x(String(d)) + x.bandwidth() / 2;
      g.append("path").attr("fill", "none").attr("stroke", ink("working"))
        .attr("stroke-width", 2.4)
        .attr("d", d3.line().x(mid).y((d, i) => y(F.big_ships[i]))(F.years));
      g.selectAll(null).data(F.years).join("circle")
        .attr("cx", mid).attr("cy", (d, i) => y(F.big_ships[i])).attr("r", 3.4)
        .attr("fill", ink("working"));

      if (!narrow) kit.endLabels(g, w, [
        { y: y(F.small_boats.at(-1)), text: "small boats", color: ink("accent-tx"), weight: 600 },
        { y: y(F.big_ships.at(-1)), text: "big ships", color: ink("working") }]);
      else {
        kit.halo(g.append("text").attr("x", 2).attr("y", y(F.big_ships[0]) - 12)
          .attr("fill", ink("working"))
          .style("font", '500 12px Karla, ui-sans-serif, sans-serif').text("big ships"));
        kit.halo(g.append("text").attr("x", 2).attr("y", 12)
          .attr("fill", ink("accent-tx"))
          .style("font", '600 12px Karla, ui-sans-serif, sans-serif').text("small boats"));
      }
      // the empty band above the first bars and below the last two is the only
      // place a two-line note fits without sitting on an orange bar.
      kit.note(g, { x: mid(F.years[0]), y: y(F.big_ships[0]), dx: 8,
        dy: y(d3.max(F.small_boats) * 0.95) - y(F.big_ships[0]),
        color: ink("working"), leader: true,
        text: narrow ? ["commercial ships,", "the same weeks —", "flat"]
                     : ["commercial ships, the same weeks —",
                        "if antennas were the story, this would climb too"] });

      kit.hover(g, w, h, px => {
        const i = d3.bisect(F.years.map(d => mid(d) + x.step() / 2), px);
        return F.years[i] === undefined ? null : {
          x: mid(F.years[i]), y: y(F.small_boats[i]), color: ink("accent"),
          text: `${F.years[i]}\n${sp(F.small_boats[i])} small boats\n${sp(F.big_ships[i])} big ships` };
      });
    });

  kit.table(document.getElementById("t-i2"), ["year", "small boats", "big ships"],
    F.years.map((yr, i) => [yr, sp(F.small_boats[i]), sp(F.big_ships[i])]));
}


/* ============================= I3 — the flags =========================== */
/* One accent for the subject and a descending ramp of ink for the rest, so
 * that any two neighbouring bands differ by more than a shade. */
const FLAG_INK = { German: "accent", Danish: "ink", Swedish: "working",
                   Norwegian: "ref", Dutch: "pale", "everyone else": "hairline" };

function flags() {
  const F = D.flags;
  kit.figure(document.getElementById("c-i3"),
    { ratio: 0.45, ratioNarrow: 0.98, margin: { top: 22, right: 128, bottom: 40, left: 40 },
      marginNarrow: { right: 96, left: 36 } },
    (g, w, h, narrow) => {
      const x = d3.scaleBand(F.years.map(String), [0, w]).padding(0.3);
      const y = d3.scaleLinear([0, 100], [h, 0]);
      kit.axis(g, y, { side: "left", values: [0, 50, 100], fmt: d => d + " %" });
      kit.axis(g, x, { side: "bottom", at: h });

      let base = F.years.map(() => 0);
      const ends = [];
      F.order.forEach(flag => {
        const v = F.shares[flag], token = FLAG_INK[flag];
        g.selectAll(null).data(F.years).join("rect")
          .attr("x", d => x(String(d))).attr("width", x.bandwidth())
          .attr("y", (d, i) => y(base[i] + v[i]))
          .attr("height", (d, i) => y(base[i]) - y(base[i] + v[i]))
          .attr("fill", ink(token))
          .attr("stroke", ink("surface")).attr("stroke-width", 1);
        ends.push({ y: y(base.at(-1) + v.at(-1) / 2),
                    text: `${flag} ${Math.round(v.at(-1))} %`,
                    color: token === "accent" ? ink("accent-tx") : ink("label"),
                    weight: token === "accent" ? 600 : 500 });
        base = base.map((b, i) => b + v[i]);
      });
      kit.endLabels(g, w, ends, narrow ? 15 : 17);
    });

  kit.table(document.getElementById("t-i3"), ["year", ...F.order],
    F.years.map((yr, i) => [yr, ...F.order.map(f => F.shares[f][i] + " %")]));
}


/* ====================== I4 — one storm, every fleet ===================== */
/* The headline is about fishing against cargo, so those two are drawn to be
 * followed and the rest is context: same hue family, thinner, paler, still
 * labelled. `short` is the label at 380 px, where the gutter is 62 px. */
const LINES = [
  ["fishing", "fishing boats", "fishing", "accent", 3.2, null],
  ["cargo", "cargo ships", "cargo", "ink", 2.2, null],
  ["ferries", "ferries", "ferries", "working", 1.3, null],
  ["work", "work boats", "work", "ref", 1.3, null],
  ["sailing", "sailing boats", "sailing", "accent-tx", 1.6, "4 3"],
];

function storms() {
  const S = D.storms;
  const names = Object.keys(S.panels).sort((a, b) =>
    d3.ascending(S.panels[a].start, S.panels[b].start));
  // ?storm=<name> so scripts/shot.sh can photograph a storm that is not the
  // default; anything unknown falls back to the default the build chose.
  const asked = new URLSearchParams(location.search).get("storm");
  let current = names.find(n => n.toLowerCase() === (asked || "").toLowerCase())
    || S.default;

  const keys = d3.select("#k-i4").selectAll("button").data(names).join("button")
    .attr("type", "button").text(d => d)
    .attr("aria-pressed", d => String(d === current))
    .on("click", (e, d) => { current = d; keys.attr("aria-pressed", k => String(k === d)); draw(); });

  const day = o => d3.utcDay.offset(d3.utcParse("%Y-%m-%d")(S.panels[current].start), o);

  let redraw = () => {};
  kit.figure(document.getElementById("c-i4"),
    { ratio: 0.46, ratioNarrow: 0.95,
      margin: { top: 30, right: 104, bottom: 46, left: 50 },
      marginNarrow: { right: 62, left: 46 } },
    (g, w, h, narrow) => { redraw = () => panel(g, w, h, narrow); redraw(); });

  function panel(g, w, h, narrow) {
    g.selectAll("*").remove();
    const P = S.panels[current];
    const lo = d3.min(P.lines.fishing, d => d[0]);
    const hi = d3.max(P.lines.fishing, d => d[0]);
    const x = d3.scaleLinear([lo, hi], [0, w]);
    const y = d3.scaleLinear([0, 100], [h, 0]);

    // the storm's own calendar dates, shaded across the whole panel
    const pad = (x(1) - x(0)) / 2;
    g.append("rect").attr("x", x(0) - pad).attr("width", x(P.days - 1) - x(0) + 2 * pad)
      .attr("y", 0).attr("height", h).attr("fill", ink("hairline")).attr("opacity", 0.55);
    const month = narrow ? "%-d %b %Y" : "%-d %B %Y";
    const when = P.days > 1
      ? d3.utcFormat("%-d")(day(0)) + "\u2013" + d3.utcFormat(month)(day(P.days - 1))
      : d3.utcFormat(month)(day(0));
    kit.halo(g.append("text").attr("x", x((P.days - 1) / 2)).attr("y", 13)
      .attr("text-anchor", "middle").attr("fill", ink("label"))
      .style("font", `500 ${narrow ? 11 : 12}px "IBM Plex Mono", ui-monospace, monospace`)
      .call(t => (narrow ? [current, when] : [`${current} \u00b7 ${when}`])
        .forEach((line, i) => t.append("tspan").attr("x", x((P.days - 1) / 2))
          .attr("dy", i ? "1.3em" : 0).text(line))));

    kit.axis(g, y, { side: "left", values: [0, 25, 50, 75, 100], fmt: d => d + " %",
                     grid: w, title: narrow ? "% that went out"
                       : "of every 100 boats heard, how many went out" });
    // three dated ticks, not eight: the dots say where the days are.
    kit.axis(g, x, { side: "bottom", at: h, values: [lo, 0, hi],
                     fmt: o => d3.utcFormat(o === 0 && !narrow ? "%-d %B" : "%-d %b")(day(o)) });

    const line = d3.line().x(d => x(d[0])).y(d => y(d[1]));
    const ends = [];
    LINES.forEach(([key, label, short, colour, width, dash]) => {
      const pts = P.lines[key];
      if (!pts) return;
      g.append("path").attr("d", line(pts))
        .attr("fill", "none").attr("stroke", ink(colour)).attr("stroke-width", width)
        .attr("stroke-dasharray", dash).attr("stroke-linejoin", "round")
        .attr("stroke-linecap", "round");
      g.selectAll(null).data(pts).join("circle")
        .attr("cx", d => x(d[0])).attr("cy", d => y(d[1]))
        .attr("r", key === "fishing" ? 3.4 : 2.6).attr("fill", ink(colour));
      ends.push({ y: y(pts.at(-1)[1]), text: narrow ? short : label,
                  color: colour === "accent" ? ink("accent-tx") : ink(colour),
                  weight: key === "fishing" || key === "cargo" ? 600 : 400 });
    });
    kit.endLabels(g, w, ends);

    // one annotation, on the day the fishing fleet stayed in
    // under the low point, where nothing else can be: every line on this chart
    // is a share of a fleet, so the band between the worst day and zero is the
    // one piece of the panel that is always empty.
    const own = P.lines.fishing.filter(d => d[0] >= 0 && d[0] < P.days);
    const low = d3.least(own, d => d[1]);
    const say = [`${Math.round(low[1])} of every 100 fishing boats went out`];
    const room = h - 6 - y(low[1]);   // space under the point, inside the plot
    const late = x(low[0]) > w * 0.55;
    kit.note(g, narrow
      ? { x: 0, y: h - 4, size: 11.5, color: ink("accent-tx"), text: say }
      : room >= 22
        ? { x: x(low[0]), y: y(low[1]), dy: 22, anchor: "middle",
            color: ink("accent-tx"), text: say }
        // a fleet that went to almost nothing leaves no room underneath, so the
        // label goes above it instead of over the date ticks.
        : { x: x(low[0]), y: y(low[1]), dy: -18, dx: late ? -10 : 10,
            anchor: late ? "end" : "start", color: ink("accent-tx"), text: say });

    const flat = LINES.flatMap(([key, label, short, colour]) =>
      (P.lines[key] || []).map(d => [...d, label, colour]));
    kit.hover(g, w, h, (px, py) => {
      const d = d3.least(flat, p => (x(p[0]) - px) ** 2 + (y(p[1]) - py) ** 2);
      return Math.abs(x(d[0]) - px) > x(1) - x(0) ? null : {
        x: x(d[0]), y: y(d[1]), color: ink(d[4]),
        text: `${d[3]}\n${d3.utcFormat("%-d %B %Y")(day(d[0]))}\n${d[1]} % went out` +
              (d[2] === null ? "" : `\nof ${sp(d[2])} heard`) };
    });
  }

  function draw() { redraw(); table(); }

  function table() {
    const P = S.panels[current];
    const offs = P.lines.fishing.map(d => d[0]);
    kit.table(document.getElementById("t-i4"),
      [`${current} — % of the boats heard that went out`,
       ...offs.map(o => d3.utcFormat("%-d %b")(day(o)))],
      LINES.filter(([k]) => P.lines[k]).map(([k, label]) => {
        const by = new Map(P.lines[k].map(d => [d[0], d[1]]));
        return [label, ...offs.map(o => by.has(o) ? by.get(o) + " %" : "—")];
      }));
  }

  table();
}


/* ========================== I5 — who goes in first ====================== */
/* A fleet that crossed the half-way line in fewer than this share of the
 * storms is not drawn as "stopping at hour N" — it is drawn as carrying on,
 * because a median over two storms out of fourteen is not a habit. */
const RARE = 0.25;

function onset() {
  const rows = D.onset.rows;
  kit.figure(document.getElementById("c-i5"),
    { ratio: 0.36, ratioNarrow: 0.8, margin: { top: 26, right: 30, bottom: 48, left: 112 },
      marginNarrow: { left: 92, right: 16, bottom: 46 } },
    (g, w, h, narrow) => {
      const kept = rows.filter(r => r.storms >= RARE * r.of && r.hour !== null);
      const lo = Math.min(0, d3.min(kept, r => r.hour) - 3);
      const x = d3.scaleLinear([lo, d3.max(kept, r => r.hour) + (narrow ? 21 : 8)], [0, w]);
      const y = d3.scalePoint(rows.map(r => r.fleet), [0, h]).padding(0.6);
      kit.axis(g, x, { side: "bottom", at: h,
                       values: d3.range(0, d3.max(kept, r => r.hour) + 1, narrow ? 12 : 6),
                       fmt: d => d ? "+" + d + " h" : "0 h",
                       title: narrow ? null : "hours after the storm's day began" });
      g.append("line").attr("x1", x(0)).attr("x2", x(0)).attr("y1", -6).attr("y2", h)
        .attr("stroke", ink("ref"));

      const arrow = g.append("defs").append("marker").attr("id", "i5-arrow")
        .attr("viewBox", "0 0 8 8").attr("refX", 7).attr("refY", 4)
        .attr("markerWidth", 6).attr("markerHeight", 6).attr("orient", "auto");
      arrow.append("path").attr("d", "M0 0 L8 4 L0 8 Z").attr("fill", ink("working"));

      rows.forEach(r => {
        const rare = r.storms < RARE * r.of;
        const colour = ink(r.fleet === "fishing" || r.fleet === "sailing"
                           ? "accent" : "working");
        g.append("text").attr("x", -14).attr("y", y(r.fleet)).attr("dy", "0.34em")
          .attr("text-anchor", "end").attr("fill", ink("ink"))
          .style("font", `${r.fleet === "fishing" || r.fleet === "sailing" ? 600 : 500} `
                 + `${narrow ? 12 : 13}px Karla, ui-sans-serif, sans-serif`)
          .text(r.label);

        if (rare) {
          // no dot, on purpose: this fleet did not stop. The line leaves the
          // chart to the right, which is what "kept sailing" looks like.
          g.append("line").attr("x1", x(0)).attr("x2", w - 2)
            .attr("y1", y(r.fleet)).attr("y2", y(r.fleet))
            .attr("stroke", ink("working")).attr("stroke-width", 1.6)
            .attr("marker-end", "url(#i5-arrow)");
          kit.halo(g.append("text").attr("x", x(0) + 10).attr("y", y(r.fleet) - 11)
            .attr("fill", ink("label"))
            .style("font", `400 ${narrow ? 11 : 12.5}px Karla, ui-sans-serif, sans-serif`)
            .text(narrow ? `kept sailing in ${r.of - r.storms}/${r.of}`
                         : `kept sailing in ${r.of - r.storms} of ${r.of} storms`));
          return;
        }
        g.append("line").attr("x1", x(Math.min(0, r.hour))).attr("x2", x(Math.max(0, r.hour)))
          .attr("y1", y(r.fleet)).attr("y2", y(r.fleet))
          .attr("stroke", colour).attr("stroke-width", 3).attr("stroke-linecap", "round");
        g.append("circle").attr("cx", x(r.hour)).attr("cy", y(r.fleet)).attr("r", 6)
          .attr("fill", colour);
        const half = r.storms < 0.5 * r.of;
        // a fleet that goes in BEFORE the storm's date has its dot left of the
        // zero line; its label still starts right of it, in the same column as
        // every other row, rather than running back over the fleet names.
        kit.halo(g.append("text").attr("x", Math.max(x(r.hour), x(0)) + 13)
          .attr("y", y(r.fleet))
          .attr("dy", "0.34em").attr("fill", ink("label"))
          .style("font", `400 ${narrow ? 11 : 12.5}px Karla, ui-sans-serif, sans-serif`)
          .text(`${r.hour >= 0 ? "+" : "\u2212"}${Math.abs(r.hour)} h \u00b7 ` + (narrow
            ? `${r.storms}/${r.of}`
            : `${half ? "only " : ""}${r.storms} of ${r.of} storms`)));
      });
    });

  kit.table(document.getElementById("t-i5"),
    ["fleet", "goes in at", "storms it went in"],
    rows.map(r => [r.label,
      r.storms < RARE * r.of || r.hour === null ? "kept sailing"
        : `${r.hour >= 0 ? "+" : "\u2212"}${Math.abs(r.hour)} h`,
      `${r.storms} of ${r.of}`]));
}


/* ========================= I6 — the sea empties ========================= */
function seaEmpties() {
  const host = document.getElementById("c-i6");
  const key = D.storms.media;
  // The figure STAYS, and says so. Hiding it left the paragraph above
  // promising "here is the same storm as a map" and nothing underneath.
  const fail = () => SeafolkStorm.unavailable(host, key);
  if (!window.SeafolkStorm || !window.SEAFOLK_LAND) {
    host.textContent = "The animation could not be loaded — open "
      + `site/media/storm-${key}.mp4`;
    return;
  }
  SeafolkStorm.load([key], got => {
    if (!got.length) return fail();
    try { SeafolkStorm.mount(host, key); } catch (e) { fail(); }
  });
}


/* ======================= I7 — days that cannot happen =================== */
function impossible() {
  const I = D.impossible;
  const months = I.months.map(([m, v, dup]) => [d3.utcParse("%Y-%m")(m), v, dup, m]);
  const TOP = 1.2;
  kit.figure(document.getElementById("c-i7"),
    { ratio: 0.42, ratioNarrow: 0.78, margin: { top: 30, right: 20, bottom: 40, left: 52 },
      marginNarrow: { left: 46 } },
    (g, w, h, narrow) => {
      const x = d3.scaleUtc([new Date(Date.UTC(2014, 11, 1)), new Date(Date.UTC(2026, 9, 1))], [0, w]);
      const y = d3.scaleLinear([0, TOP], [h, 0]);
      const bw = Math.max(2, w / 145);
      kit.axis(g, y, { side: "left", values: [0, 0.5, 1], fmt: d => d + " %", grid: w,
                       title: narrow ? "impossible days"
                         : "share of ships' days with impossible message counts" });
      kit.axis(g, x, { side: "bottom", at: h,
                       values: [2015, 2018, 2021, 2024, 2026].map(k => new Date(Date.UTC(k, 0, 1))),
                       fmt: d3.utcFormat("%Y") });

      g.selectAll(null).data(months).join("rect")
        .attr("x", d => x(d[0]) - bw / 2).attr("width", bw)
        .attr("y", d => y(Math.min(d[1], TOP)))
        .attr("height", d => h - y(Math.min(d[1], TOP)))
        .attr("fill", d => d[3] >= I.step ? ink("accent") : ink("working"));
      // the one bar that runs off the top keeps its value rather than a taller
      // axis, which would flatten the wall this chart is about.
      months.filter(d => d[1] > TOP).forEach(d => {
        g.append("path").attr("d", d3.symbol(d3.symbolTriangle, 30))
          .attr("transform", `translate(${x(d[0])},-7)`).attr("fill", ink("working"));
        kit.halo(g.append("text").attr("x", x(d[0]) + 9).attr("y", 14)
          .attr("fill", ink("label"))
          .style("font", '400 12px "IBM Plex Mono", ui-monospace, monospace')
          .text(`${d[1].toFixed(1)} % in ${d3.utcFormat("%B %Y")(d[0])}`));
      });

      // the empty middle of the chart, pointing right at where the wall starts.
      const step = months.find(d => d[3] === I.step);
      kit.note(g, { x: x(step[0]), y: y(TOP * 0.5), dx: -14, anchor: "end",
        leader: true, color: ink("accent-tx"), text: narrow
          ? ["from December 2023", "on: every month"]
          : ["from December 2023 onward, every single month",
             "holds days that cannot have happened"] });

      kit.hover(g, w, h, px => {
        const d = d3.least(months, m => Math.abs(x(m[0]) - px));
        return Math.abs(x(d[0]) - px) > 12 ? null : {
          x: x(d[0]), y: y(Math.min(d[1], TOP)), color: ink("accent"),
          text: `${d3.utcFormat("%B %Y")(d[0])}\n${d[1]} % of that month's ships' days` };
      });
    });

  kit.table(document.getElementById("t-i7"),
    ["month", "days above the ceiling"],
    months.map(d => [d3.utcFormat("%B %Y")(d[0]), d[1] + " %"]));
}


/* ====================== I8 — Copenhagen, mirrored ======================= */
function mirror() {
  const M = D.mirror;
  kit.figure(document.getElementById("c-i8"),
    { ratio: 0.45, ratioNarrow: 0.68, margin: { top: 18, right: 18, bottom: 18, left: 18 } },
    (g, w, h, narrow) => {
      const x = d3.scaleLinear([-180, 180], [0, w]);
      const y = d3.scaleLinear([80, -58], [0, h]);
      const path = d3.line().x(d => x(d[0])).y(d => y(d[1]));

      // the land runs past the bottom of the frame (Antarctica) and the figure's
      // SVG deliberately does not clip, so that end labels can sit in the margin.
      // This one group is clipped instead.
      const id = "land-clip";
      g.append("clipPath").attr("id", id).append("rect")
        .attr("x", -4).attr("y", -4).attr("width", w + 8).attr("height", h + 8);
      g.append("g").attr("clip-path", `url(#${id})`)
        .selectAll("path").data(M.land).join("path")
        .attr("d", d => path(d) + "Z").attr("fill", ink("hairline"));

      // the mirror is a reflection across lat = lon, so the line itself is the
      // explanation: the two dots are the same point on either side of it.
      g.append("line").attr("x1", x(y.domain()[1])).attr("y1", y(y.domain()[1]))
        .attr("x2", x(y.domain()[0])).attr("y2", y(y.domain()[0]))
        .attr("stroke", ink("ref")).attr("stroke-dasharray", "5 5");
      g.append("line")
        .attr("x1", x(M.cph[1])).attr("y1", y(M.cph[0]))
        .attr("x2", x(M.mirrored[1])).attr("y2", y(M.mirrored[0]))
        .attr("stroke", ink("accent")).attr("stroke-width", 1.2)
        .attr("stroke-dasharray", "3 4");

      const dot = (lat, lon, filled) => g.append("circle")
        .attr("cx", x(lon)).attr("cy", y(lat)).attr("r", 6)
        .attr("fill", filled ? ink("accent") : ink("surface"))
        .attr("stroke", ink("accent")).attr("stroke-width", 2.4);
      dot(M.cph[0], M.cph[1], true);
      dot(M.mirrored[0], M.mirrored[1], false);

      kit.note(g, { x: x(M.cph[1]), y: y(M.cph[0]), dx: -12, dy: -14, anchor: "end",
        color: ink("ink"), text: narrow ? ["Copenhagen,", "where it is"]
                                        : ["Copenhagen, where it is"] });
      kit.note(g, { x: x(M.mirrored[1]), y: y(M.mirrored[0]), dx: 12, dy: 16,
        color: ink("accent-tx"),
        text: narrow ? ["where my grid", "put it"]
                     : ["where my grid put it — the Arabian Sea,", "and every other boat with it"] });
      // the South Pacific is the one large piece of empty water on this map.
      kit.halo(g.append("text").attr("x", x(-176)).attr("y", y(-26))
        .attr("fill", ink("label"))
        .style("font", '400 12px Karla, ui-sans-serif, sans-serif')
        .call(t => (narrow ? ["every point mirrored", "across the line where",
                              "latitude equals longitude"]
                           : ["every point mirrored across the line",
                              "where latitude equals longitude"])
          .forEach((line, i) => t.append("tspan").attr("x", x(-176))
            .attr("dy", i ? "1.3em" : 0).text(line))));
    });

  kit.table(document.getElementById("t-i8"),
    ["point", "latitude", "longitude"],
    [["Copenhagen", M.cph[0] + " N", M.cph[1] + " E"],
     ["where the first grid put it", M.mirrored[0] + " N", M.mirrored[1] + " E"]]);
}


season();
fleet();
flags();
storms();
onset();
seaEmpties();
impossible();
mirror();
})();
