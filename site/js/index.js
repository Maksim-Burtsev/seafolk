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
        .style("font", d => `${d.weight} ${d.size}px "Source Serif 4", Georgia, serif`)
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
          .style("font", '500 12px "Source Serif 4", Georgia, serif').text("big ships"));
        kit.halo(g.append("text").attr("x", 2).attr("y", 12)
          .attr("fill", ink("accent-tx"))
          .style("font", '600 12px "Source Serif 4", Georgia, serif').text("small boats"));
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


/* ========================= I4 — every storm at once ====================== */
/* Round 2: no selector. Two fleets, their mean over every storm with a whole
 * window, and each of those storms behind them as a hairline of its own hue.
 * The reader gets the claim without touching anything. */
const I4 = [["fishing", "fishing boats", "accent", "accent-tx"],
            ["cargo", "cargo ships", "ink", "ink"]];

function storms() {
  const S = D.storms;
  const OFF = S.offsets;
  const off = o => (o > 0 ? "+" : o < 0 ? "−" : "") + Math.abs(o);
  const line = d3.line().x(d => x(d[0])).y(d => y(d[1]));
  let x, y;

  kit.figure(document.getElementById("c-i4"),
    { ratio: 0.46, ratioNarrow: 0.95,
      margin: { top: 24, right: 106, bottom: 46, left: 50 },
      marginNarrow: { right: 70, left: 46 } },
    (g, w, h, narrow) => {
      x = d3.scaleLinear(d3.extent(OFF), [0, w]);
      y = d3.scaleLinear([0, 100], [h, 0]);

      // the storm's own date, one day wide, shaded across the panel
      const pad = (x(1) - x(0)) / 2;
      g.append("rect").attr("x", x(0) - pad).attr("width", 2 * pad)
        .attr("y", 0).attr("height", h)
        .attr("fill", ink("hairline")).attr("opacity", 0.55);
      kit.halo(g.append("text").attr("x", x(0)).attr("y", 11)
        .attr("text-anchor", "middle").attr("fill", ink("label"))
        .style("font", `500 ${narrow ? 11 : 12}px "IBM Plex Mono", ui-monospace, monospace`)
        .text("the storm"));

      kit.axis(g, y, { side: "left", values: [0, 25, 50, 75, 100], fmt: d => d + " %",
                       grid: w, title: narrow ? "% that went out"
                         : "of every 100 boats heard, how many went out" });
      kit.axis(g, x, { side: "bottom", at: h, values: OFF,
                       fmt: o => o === 0 ? "day" : off(o) });

      // every storm first, as its fleet's hue at a fifth of the weight: the
      // spread is the evidence that the mean is not one lucky gale.
      I4.forEach(([key, , tok]) => S[key].each.forEach(pts => g.append("path")
        .attr("d", line(pts)).attr("fill", "none").attr("stroke", ink(tok))
        .attr("stroke-width", 1).attr("opacity", 0.22)
        .attr("stroke-linejoin", "round")));

      const ends = [];
      I4.forEach(([key, label, tok, txt]) => {
        g.append("path").attr("d", line(S[key].mean)).attr("fill", "none")
          .attr("stroke", ink(tok)).attr("stroke-width", 3.4)
          .attr("stroke-linejoin", "round").attr("stroke-linecap", "round");
        g.selectAll(null).data(S[key].mean).join("circle")
          .attr("cx", d => x(d[0])).attr("cy", d => y(d[1])).attr("r", 3.6)
          .attr("fill", ink(tok));
        ends.push({ y: y(S[key].mean.at(-1)[1]), color: ink(txt), weight: 600,
                    text: narrow ? label.split(" ")[0] : label + ", all storms" });
      });
      kit.endLabels(g, w, ends);

      // one annotation, under the fishing mean on the storm's own date: every
      // line here is a share of a fleet, so the band down to zero is empty.
      const low = S.fishing.mean.find(d => d[0] === 0)[1];
      const n = D.n.storm_fishing_day;
      kit.note(g, narrow
        ? { x: 0, y: h - 24, size: 11.5, color: ink("accent-tx"),
            text: [`on the storm day ${n} of every`, "100 fishing boats went out"] }
        : { x: x(0), y: y(low), dy: 22, anchor: "middle", color: ink("accent-tx"),
            text: [`on the storm day ${n} of every 100 fishing boats went out`] });

      const flat = I4.flatMap(([key, label, tok]) =>
        S[key].mean.map(d => [...d, label, tok]));
      kit.hover(g, w, h, (px, py) => {
        const d = d3.least(flat, p => (x(p[0]) - px) ** 2 + (y(p[1]) - py) ** 2);
        return Math.abs(x(d[0]) - px) > (x(1) - x(0)) / 2 ? null : {
          x: x(d[0]), y: y(d[1]), color: ink(d[3]),
          text: `${d[2]}, mean of ${S.storms.length} storms\nday ${off(d[0])}\n${d[1]} % went out` };
      });
    });

  kit.table(document.getElementById("t-i4"),
    ["mean over the storms — % of the boats heard that went out",
     ...OFF.map(o => o === 0 ? "the storm" : "day " + off(o))],
    I4.map(([key, label]) => [label, ...S[key].mean.map(d => d[1] + " %")])
      .concat([["storms in the mean", ...OFF.map(() => S.storms.length)]]));
}


/* ====================== I5 — who stays in, per fleet ===================== */
function stayedIn() {
  const rows = D.stayed;
  kit.figure(document.getElementById("c-i5"),
    { ratio: 0.42, ratioNarrow: 0.8,
      margin: { top: 12, right: 64, bottom: 44, left: 116 },
      marginNarrow: { left: 96, right: 52, bottom: 42 } },
    (g, w, h, narrow) => {
      const x = d3.scaleLinear([0, 100], [0, w]);
      const y = d3.scaleBand(rows.map(r => r.fleet), [0, h]).padding(0.42);
      const pooled = d3.max(rows, r => r.storms);
      kit.axis(g, x, { side: "bottom", at: h, values: [0, 25, 50, 75, 100],
                       fmt: d => d + " %",
                       title: narrow ? null : "of every 100 that go out on a usual day" });

      rows.forEach(r => {
        const own = r.fleet === "fishing";
        const colour = ink(own ? "accent" : "working");
        g.append("rect").attr("x", 0).attr("y", y(r.fleet))
          .attr("width", Math.max(x(r.value), 1)).attr("height", y.bandwidth())
          .attr("fill", colour);
        g.append("text").attr("x", -14).attr("y", y(r.fleet) + y.bandwidth() / 2)
          .attr("dy", "0.34em").attr("text-anchor", "end").attr("fill", ink("ink"))
          .style("font", `${own ? 600 : 500} ${narrow ? 12 : 13.5}px `
                 + '"Source Serif 4", Georgia, serif')
          .text(r.label);
        kit.halo(g.append("text").attr("x", x(r.value) + 9)
          .attr("y", y(r.fleet) + y.bandwidth() / 2).attr("dy", "0.34em")
          .attr("fill", own ? ink("accent-tx") : ink("label"))
          .style("font", `${own ? 600 : 500} 13px "IBM Plex Mono", ui-monospace, monospace`)
          .text(Math.round(r.value)));
        // every fleet is measured over every storm except the sailing one,
        // which has only the storms with enough boats out to divide by. That
        // row says so; the rest would say the same thing five times.
        if (r.storms !== pooled) kit.halo(g.append("text")
          .attr("x", 4).attr("y", y(r.fleet) - 5).attr("fill", ink("label"))
          .style("font", '400 11.5px "Source Serif 4", Georgia, serif')
          .text(`${r.storms} storms`));
      });
    });

  kit.table(document.getElementById("t-i5"),
    ["fleet", "stayed in, of every 100", "storms pooled"],
    rows.map(r => [r.label, r.value + " %", r.storms]));
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


/* ======================== the static map figures ========================= */
/* site/js/minimap.js + site/media/maps.js belong to another session. If they
 * are not on the page the slot stays empty and the story still opens from
 * file://, rather than one missing component taking the page down with it.
 * Each map's own title and note come out of the data (see minimap.js), so the
 * only thing said here is which layer and which one is the subject. */
function maps(id, method, list) {
  const el = document.getElementById(id);
  if (!el || !list.length) return;
  if (!window.SeafolkMap || typeof SeafolkMap[method] !== "function") return;
  try { SeafolkMap[method](el, method === "draw" ? list[0] : list); }
  catch (e) { el.textContent = ""; console.error("minimap " + id, e); }
}


/* ======================= I7 — a day that cannot happen =================== */
/* A figure of chart sheets, side by side on a wide screen. `key` is the one
 * line under them that says what a mark is; the dot scale comes from the
 * build's manifest, never from this file. */
function sheets(id, list, names, key) {
  const el = document.getElementById(id);
  const row = el.appendChild(document.createElement("div"));
  row.className = list.length > 1 ? "sheets" : "";
  list.forEach(([cid, tag]) => chart.sheet(row, cid, { names, tag, ticks: list.length === 1 }));
  if (key) {
    const k = el.appendChild(document.createElement("ul"));
    k.className = "key";
    k.innerHTML = key.map(([cls, colour, text]) =>
      `<li style="color:var(--${colour})"><i class="${cls}"></i><span style="color:var(--label)">${text}</span></li>`).join("");
  }
}

function impossible() {
  const I = D.impossible;
  const months = I.months.map(([m, v, dup]) => [d3.utcParse("%Y-%m")(m), v, dup, m]);

  /* the picture: two bars, to scale, one against the other. */
  kit.figure(document.getElementById("c-i7"),
    { ratio: 0.14, ratioNarrow: 0.5,
      margin: { top: 10, right: 16, bottom: 4, left: 0 },
      marginNarrow: { right: 8, left: 0 } },
    (g, w, h, narrow) => {
      const x = d3.scaleLinear([0, I.worst.msgs], [0, w]);
      const bars = [
        { v: I.cap, tok: "working", tx: "label",
          label: narrow ? ["the most a ship's radio", "can send in a day"]
                        : ["the most a ship's radio can send in a day"] },
        { v: I.worst.msgs, tok: "accent", tx: "accent-tx",
          label: narrow ? ["what this archive holds for", "one ship on its worst day"]
                        : ["what this archive holds for one ship on its worst day"] }];
      const row = h / 2, bh = Math.min(30, row * 0.38);
      bars.forEach((b, i) => {
        const top = i * row;
        b.label.forEach((t, k) => g.append("text").attr("x", 0)
          .attr("y", top + 12 + k * 15).attr("fill", ink(b.tx))
          .style("font", `${i ? 600 : 500} ${narrow ? 12.5 : 14}px `
                 + '"Source Serif 4", Georgia, serif').text(t));
        const by = top + 12 + b.label.length * 15;
        g.append("rect").attr("x", 0).attr("y", by)
          .attr("width", Math.max(x(b.v), 2)).attr("height", bh)
          .attr("fill", ink(b.tok));
        // a bar that fills the frame has no room beside it for its own number,
        // so on a phone the long one carries it inside instead.
        const out = x(b.v) < w * 0.72;
        kit.halo(g.append("text")
          .attr("x", out ? x(b.v) + 9 : x(b.v) - 10).attr("y", by + bh / 2)
          .attr("text-anchor", out ? "start" : "end")
          .attr("dy", "0.34em").attr("fill", out ? ink(b.tx) : ink("surface"))
          .style("font", `${i ? 600 : 500} ${narrow ? 12 : 13.5}px `
                 + '"IBM Plex Mono", ui-monospace, monospace')
          .text(sp(b.v) + (i ? `  \u00d7${I.worst.times}` : "")))
          .attr("stroke", out ? ink("surface") : ink(b.tok));
      });
    });

  /* …and under it, quietly, when it started. */
  const TOP = 1.2;
  kit.figure(document.getElementById("c-i7b"),
    { ratio: 0.17, ratioNarrow: 0.32,
      margin: { top: 16, right: 16, bottom: 30, left: 44 },
      marginNarrow: { left: 40 } },
    (g, w, h, narrow) => {
      const x = d3.scaleUtc([new Date(Date.UTC(2014, 11, 1)), new Date(Date.UTC(2026, 9, 1))], [0, w]);
      const y = d3.scaleLinear([0, TOP], [h, 0]);
      const bw = Math.max(2, w / 150);
      kit.axis(g, y, { side: "left", values: [0, 1], fmt: d => d + " %" });
      kit.axis(g, x, { side: "bottom", at: h,
                       values: [2015, 2018, 2021, 2024].map(k => new Date(Date.UTC(k, 0, 1))),
                       fmt: d3.utcFormat("%Y") });
      g.selectAll(null).data(months).join("rect")
        .attr("x", d => x(d[0]) - bw / 2).attr("width", bw)
        .attr("y", d => y(Math.min(d[1], TOP)))
        .attr("height", d => h - y(Math.min(d[1], TOP)))
        .attr("fill", d => d[3] >= I.step ? ink("accent") : ink("working"));
      // the one bar that runs off the top keeps its value rather than a taller
      // axis, which would flatten the wall this strip is about.
      months.filter(d => d[1] > TOP).forEach(d => kit.halo(g.append("text")
        .attr("x", x(d[0]) + 7).attr("y", 8).attr("fill", ink("label"))
        .style("font", '400 11px "IBM Plex Mono", ui-monospace, monospace')
        .text(`${d[1].toFixed(1)} %`)));
      kit.halo(g.append("text").attr("x", x(new Date(Date.UTC(2023, 11, 1))) + 6)
        .attr("y", 11).attr("fill", ink("accent-tx"))
        .style("font", '400 12px "Source Serif 4", Georgia, serif')
        .text(narrow ? "from 2024 on" : "every month from December 2023 on"));

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


hero(document.getElementById("c-hero"), document.getElementById("hero-clock"),
     document.getElementById("hero-count"));
document.getElementById("hero-day").textContent = window.SEAFOLK_FERRY_DAY
  ? d3.utcFormat("%A %-d %B %Y")(new Date(SEAFOLK_FERRY_DAY.day)) : "";
season();
const perDot = ((window.SEAFOLK_CHARTS || {})["i1-jul"] || {}).per_dot;
const smallKey = [["dots", "accent", `one dot: ${perDot} boat-days, placed at random inside its patch of sea`]];
sheets("c-i1-maps", [["i1-jul", "July 2025"], ["i1-jan", "January 2025"]],
       ["Kattegat", "Øresund", "Storebælt"], smallKey);
fleet();
sheets("c-i2-maps", [["i2-2015", "July 2015"], ["i2-2025", "July 2025"]],
       ["Kattegat", "Øresund", "Storebælt"], smallKey);
flags();
// Who else is out there: the three public fleets, each on its own sheet.
sheets("c-i3-cargo", [["i3-cargo", "July 2025"]],
       ["Skagerrak", "Kattegat", "Nordsøen", "Østersøen", "Storebælt", "Øresund", "Femern Bælt", "Skagen", "København", "Kiel"],
       [["wash", "cargo", "cargo ships and tankers under way, darker where more of them pass"]]);
sheets("c-i3-ferries", [["i3-ferries", "July 2025"]],
       ["Kattegat", "Storebælt", "Øresund", "Rødby", "Rønne", "Frederikshavn", "Göteborg", "Hirtshals", "Samsø", "Læsø", "Ærø", "Anholt"],
       [["", "ferry", "every passenger ship's own track, one thin line per crossing"]]);
sheets("c-i3-fishing", [["i3-fishing", "2025"]],
       ["Skagerrak", "Nordsøen", "Kattegat", "Østersøen", "Skagen", "Hirtshals", "Hanstholm", "Thyborøn", "Hvide Sande"],
       [["dots", "fishing", "fishing boats under way; the denser the stipple, the more hours of fishing"]]);
storms();
stayedIn();
seaEmpties();
// the three keys, and their titles, are the build's — this page only says
// which storm, and it is the storm the animation above is playing.
if (window.SeafolkMap) maps("c-i6-triptych", "triptych",
  (SeafolkMap.storm(D.storms.media) || []).map((layer, i) =>
    ({ layer, colour: i === 1 ? "accent" : "ink" })));
impossible();
})();
