/* Seafolk — the charts on the ferries page.
 *
 * Four figures, one function each, drawn into the responsive frame from
 * site/js/kit.js. No colour literal anywhere: every hue is a CSS variable from
 * site/css/site.css read at draw time, so light and dark are the same code.
 *
 * The data comes from the page's own <script type="application/json" id="data">
 * block, written by scripts/site_data/ferries.py. Nothing is fetched, because
 * the page has to open by double-click from file://.
 */
(function () {
"use strict";

const D = JSON.parse(document.getElementById("data").textContent);
const ink = kit.ink;
const MONTH = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"];
const DAY = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
             "Saturday"];
const MONO = '"IBM Plex Mono", ui-monospace, monospace';
const SANS = "Karla, ui-sans-serif, sans-serif";

/* A typical-day count is a median of whole crossings, so it is either a whole
 * number or a half. */
const fmt = v => (Number.isInteger(v) ? String(v) : v.toFixed(1));

/* Every position in a state string that carries one letter. The strings are
 * one character per day of the year — see day_state() in the page module. */
const where = (state, letter) => {
  const out = [];
  for (let i = 0; i < state.length; i++) if (state[i] === letter) out.push(i);
  return out;
};


/* ====================== F1 — one island's whole year ===================== */
/* The four states a day can be in, in the order the key prints them. `c` and
 * `u` are drawn wider than one day would be, because at 380 px a day is under
 * a pixel and the whole point of both marks is that they are visible. */
/* The key doubles as the y-axis title — the first swatch names the unit — so
 * that the top margin holds two rows of text and not three. */
const STATES = [["s", "crossings that day", "crossings", "accent"],
                ["c", "did not sail", "did not sail", "ink"],
                ["u", "nothing heard", "not heard", "ref"]];

function lifeline() {
  const F = D.f1;
  const names = Object.keys(F.lines);
  let current = F.default, redraw = () => {};

  const keys = d3.select("#k-f1").selectAll("button").data(names).join("button")
    .attr("type", "button").text(d => d)
    .attr("aria-pressed", d => String(d === current))
    .on("click", (e, d) => {
      current = d;
      keys.attr("aria-pressed", k => String(k === d));
      redraw();
      table();
    });

  kit.figure(document.getElementById("c-f1"),
    { ratio: 0.36, ratioNarrow: 0.9,
      margin: { top: 54, right: 16, bottom: 42, left: 50 },
      marginNarrow: { left: 42, right: 10 } },
    (g, w, h, narrow) => { redraw = () => panel(g, w, h, narrow); redraw(); });

  function panel(g, w, h, narrow) {
    g.selectAll("*").remove();
    const L = F.lines[current], n = L.counts.length;
    const x = d3.scaleLinear([0, n], [0, w]);
    const y = d3.scaleLinear([0, d3.max(L.counts) * 1.12], [h, 0]);
    const bw = w / n, wide = Math.max(bw, 2.5);
    const first = d3.range(12).map(m => d3.utcDay.count(
      new Date(Date.UTC(F.year, 0, 1)), new Date(Date.UTC(F.year, m, 1))));

    kit.axis(g, y, { side: "left", ticks: 4, grid: w });
    kit.axis(g, x, { side: "bottom", at: h,
                     values: [first[0], first[3], first[6], first[9]],
                     fmt: d => MONTH[first.indexOf(d)].slice(0, 3) });

    // a day nothing usable was heard on is a band over the whole height: the
    // chart is saying "no answer here", which is not the same as a zero and
    // must not look like one.
    g.selectAll(null).data(where(L.state, "u")).join("rect")
      .attr("x", d => x(d)).attr("width", wide).attr("y", 0).attr("height", h)
      .attr("fill", ink("ref")).attr("opacity", 0.38);
    g.selectAll(null).data(where(L.state, "s")).join("rect")
      .attr("x", d => x(d)).attr("width", bw)
      .attr("y", d => y(L.counts[d])).attr("height", d => h - y(L.counts[d]))
      .attr("fill", ink("accent"));
    // a day the line owed and did not sail hangs below the axis, where there
    // is nothing else to confuse it with.
    g.selectAll(null).data(where(L.state, "c")).join("rect")
      .attr("x", d => x(d)).attr("width", wide)
      .attr("y", h + 2).attr("height", 9).attr("fill", ink("ink"));

    // the two typical days, drawn as short rules over the months they were
    // measured on: the seasonal step is the second half of this chart's
    // sentence and a daily bar is too noisy to carry it on its own.
    [["january", "January", 0], ["july", "July", 6]].forEach(([key, name, m]) => {
      const v = L[key];
      if (v == null) return;
      const a = first[m], b = m === 11 ? n : first[m + 1];
      g.append("line").attr("x1", x(a)).attr("x2", x(b))
        .attr("y1", y(v)).attr("y2", y(v))
        .attr("stroke", ink("ink")).attr("stroke-width", 1.4)
        .attr("stroke-dasharray", "3 3");
      kit.halo(g.append("text").attr("x", x(a) + 2).attr("y", y(v) - 8)
        .attr("fill", ink("ink")).style("font", `500 12px ${MONO}`)
        .text(narrow ? `${fmt(v)} in ${name.slice(0, 3)}`
                     : `${fmt(v)} a day in ${name}`));
    });

    // the title and the key live in the top margin, one under the other, so
    // they read the same way at both widths.
    kit.halo(g.append("text").attr("x", 0).attr("y", -32)
      .attr("fill", ink("ink"))
      .style("font", `500 ${narrow ? 13 : 15}px ${SANS}`)
      .text(`${current} · ${F.year}`));
    let at = 0;
    STATES.filter(([c]) => c === "s" || where(L.state, c).length)
      .forEach(([c, long, short, colour]) => {
        const text = narrow ? short : long;
        g.append("rect").attr("x", at).attr("y", -20).attr("width", 9)
          .attr("height", 9).attr("fill", ink(colour))
          .attr("opacity", c === "u" ? 0.38 : 1);
        g.append("text").attr("x", at + 13).attr("y", -12)
          .attr("fill", ink("label")).style("font", `400 11.5px ${SANS}`)
          .text(text);
        at += 22 + text.length * (narrow ? 5.7 : 6.1);
      });

    // the note sits above the bars AROUND the day it is about, not above the
    // whole year: a fixed height would float in the middle of a busy line and
    // land on the axis of a thin one.
    if (L.note) {
      const i = L.note.i, right = x(i) > w * 0.55;
      // how many days of the year the text itself will cover, so the note can
      // clear the bars it is actually going to sit over rather than the ones
      // next to the leader.
      const days = Math.ceil(d3.max(L.note.text, t => t.length) * 6.6 / bw);
      const local = d3.max(L.counts.slice(right ? Math.max(0, i - days) : i,
                                          right ? i + 1 : i + days)) || 0;
      kit.note(g, { x: x(i) + wide / 2, y: h + 11,
        dx: right ? -10 : 10, dy: Math.max(6, y(local) - 34) - (h + 11),
        anchor: right ? "end" : "start", leader: true,
        color: ink("ink"), text: L.note.text });
    }

    kit.hover(g, w, h, px => {
      const i = Math.max(0, Math.min(n - 1, Math.floor(x.invert(px))));
      const when = new Date(Date.UTC(F.year, 0, 1 + i));
      const what = { s: `${L.counts[i]} crossings`, c: "did not sail",
                     u: "nothing heard", o: "no sailing due" }[L.state[i]];
      return { x: x(i) + bw / 2, y: y(L.counts[i]), color: ink("accent"),
               text: `${DAY[when.getUTCDay()]} ${when.getUTCDate()} `
                     + `${MONTH[when.getUTCMonth()]}\n${what}` };
    });
  }

  function table() {
    const L = F.lines[current];
    const by = d3.range(12).map(() => ({ c: [], miss: 0, unknown: 0 }));
    L.counts.forEach((v, i) => {
      const m = new Date(Date.UTC(F.year, 0, 1 + i)).getUTCMonth();
      if (L.state[i] === "s") by[m].c.push(v);
      if (L.state[i] === "c") by[m].miss++;
      if (L.state[i] === "u") by[m].unknown++;
    });
    kit.table(document.getElementById("t-f1"),
      ["month", "typical crossings a day", "days it did not sail",
       "days nothing was heard"],
      by.map((m, i) => [MONTH[i],
                        m.c.length ? Math.round(d3.median(m.c)) : "—",
                        m.miss || "—", m.unknown || "—"]));
  }

  table();
}


/* ================== F2 — the winter timetable, line by line ============== */
function winter() {
  const R = D.f2.rows;
  kit.figure(document.getElementById("c-f2"),
    { ratio: 0.62, ratioNarrow: 1.6,
      margin: { top: 34, right: 84, bottom: 46, left: 116 },
      marginNarrow: { left: 96, right: 40, top: 30 } },
    (g, w, h, narrow) => {
      const x = d3.scaleLinear([0, Math.max(100, d3.max(R, d => d.share))], [0, w]);
      const y = d3.scalePoint(R.map(d => d.label), [0, h]).padding(0.5);
      kit.axis(g, x, { side: "bottom", at: h, values: [0, 25, 50, 75, 100],
                       fmt: d => d + " %",
                       title: narrow ? "January, % of July"
                         : "sailings on a January weekday, against the same line in July" });
      g.append("line").attr("x1", x(100)).attr("x2", x(100))
        .attr("y1", -6).attr("y2", h)
        .attr("stroke", ink("ref")).attr("stroke-dasharray", "4 4");

      R.forEach(d => {
        const yy = y(d.label);
        g.append("line").attr("x1", x(d.share)).attr("x2", x(100))
          .attr("y1", yy).attr("y2", yy)
          .attr("stroke", ink("hairline")).attr("stroke-width", 3);
        g.append("circle").attr("cx", x(100)).attr("cy", yy).attr("r", 4.5)
          .attr("fill", ink("working"));
        g.append("circle").attr("cx", x(d.share)).attr("cy", yy).attr("r", 5.5)
          .attr("fill", ink("accent"));
        g.append("text").attr("x", -12).attr("y", yy).attr("dy", "0.34em")
          .attr("text-anchor", "end").attr("fill", ink("ink"))
          .style("font", `${d.share === 100 ? 500 : 600} ${narrow ? 12 : 13}px ${SANS}`)
          .text(d.label);
        // the two counts ride along at the dots: the position carries the
        // share, the labels carry what it is a share of.
        if (!narrow) {
          kit.halo(g.append("text").attr("x", x(d.share) - 10).attr("y", yy)
            .attr("dy", "0.34em").attr("text-anchor", "end")
            .attr("fill", ink("accent-tx")).style("font", `500 12px ${MONO}`)
            .text(fmt(d.winter)));
          kit.halo(g.append("text").attr("x", x(100) + 10).attr("y", yy)
            .attr("dy", "0.34em").attr("fill", ink("label"))
            .style("font", `400 12px ${MONO}`).text(fmt(d.summer)));
        }
      });

      // the series labels go on the top row, where the gap is widest, and
      // nothing on this chart needs a legend box.
      const top = R[0].label;
      kit.note(g, { x: x(R[0].share), y: y(top), dy: -16, anchor: "start",
        color: ink("accent-tx"), text: narrow ? ["January"] : ["a January weekday"] });
      kit.note(g, { x: x(100), y: y(top), dy: -16, anchor: "end",
        color: ink("label"), text: narrow ? ["July"] : ["a July weekday"] });

      kit.hover(g, w, h, (px, py) => {
        const d = d3.least(R, r => Math.abs(y(r.label) - py));
        return Math.abs(y(d.label) - py) > 14 ? null : {
          x: x(d.share), y: y(d.label), color: ink("accent"),
          text: `${d.label}\n${fmt(d.summer)} a day in July\n`
                + `${fmt(d.winter)} a day in January` };
      });
    });

  kit.table(document.getElementById("t-f2"),
    ["island line", "July weekday", "January weekday", "winter, % of summer"],
    R.map(d => [d.label, fmt(d.summer), fmt(d.winter), d.share + " %"]));
}


/* ================= F3 — storms: the small lines and the big ============== */
const POOLS = [["island", "the island lines", "islands", "accent"],
               ["big", "the four big lines", "big lines", "working"]];

function storms() {
  const R = D.f3.rows;
  kit.figure(document.getElementById("c-f3"),
    { ratio: 0.52, ratioNarrow: 1.3,
      margin: { top: 44, right: 46, bottom: 46, left: 116 },
      marginNarrow: { left: 92, right: 34, top: 40 } },
    (g, w, h, narrow) => {
      const x = d3.scaleLinear([0, Math.max(110, d3.max(R, d => d.big) + 8)], [0, w]);
      const y = d3.scaleBand(R.map(d => d.storm), [0, h]).padding(0.34);
      const sub = d3.scaleBand(POOLS.map(p => p[0]), [0, y.bandwidth()])
        .padding(0.22);
      kit.axis(g, x, { side: "bottom", at: h, values: [0, 50, 100],
                       fmt: d => d + " %",
                       title: narrow ? "% of a usual day's crossings"
                         : "share of a usual day's crossings that sailed" });
      g.append("line").attr("x1", x(100)).attr("x2", x(100))
        .attr("y1", -10).attr("y2", h)
        .attr("stroke", ink("ref")).attr("stroke-dasharray", "4 4");

      R.forEach((d, row) => {
        POOLS.forEach(([key, long, short, colour]) => {
          const yy = y(d.storm) + sub(key);
          g.append("rect").attr("x", 0).attr("y", yy)
            .attr("width", x(d[key])).attr("height", sub.bandwidth())
            .attr("fill", ink(colour));
          // The FIRST value on the chart says what the number is, so a reader
          // meeting "52 %" cold does not read it as "lost 52 %". The rest are
          // bare percentages, under a label that now says the same thing.
          kit.halo(g.append("text").attr("x", x(d[key]) + 7)
            .attr("y", yy + sub.bandwidth() / 2).attr("dy", "0.34em")
            .attr("fill", ink(colour === "accent" ? "accent-tx" : "label"))
            .style("font", `500 12px ${MONO}`)
            .text(!row && key === POOLS[0][0] && !narrow
              ? `sailed ${d[key]} % of a usual day`
              : d[key] + " %"));
          // direct labels, on the top pair only: two bars in two colours need
          // saying once, not a legend in the corner. The first goes above its
          // bar and the second below its own, so neither sits on the other's.
          if (!row) {
            g.append("text").attr("x", 4)
              .attr("y", key === "island" ? yy - 7 : yy + sub.bandwidth() + 15)
              .attr("fill", ink(colour === "accent" ? "accent-tx" : "label"))
              .style("font", `600 ${narrow ? 11.5 : 12.5}px ${SANS}`)
              .text(narrow ? short : long);
          }
        });
        g.append("text").attr("x", -12).attr("y", y(d.storm) + y.bandwidth() / 2)
          .attr("dy", "0.34em").attr("text-anchor", "end").attr("fill", ink("ink"))
          .style("font", `600 ${narrow ? 12 : 13.5}px ${SANS}`)
          .call(t => d.storm.split(" · ").forEach((part, i, all) =>
            t.append("tspan").attr("x", -12)
              .attr("dy", i ? "1.15em" : `${-0.55 * (all.length - 1)}em`)
              .text(part)));
      });

      // the one exception on the chart, pointed at rather than left for the
      // reader to find: in Malik the big lines lost more than the islands.
      const d = R.find(s => s.storm === "Malik");
      if (d) {
        const under = y(d.storm) + sub("big") + sub.bandwidth();
        kit.note(g, narrow
          ? { x: 4, y: under + 15, color: ink("label"),
              text: ["Malik: the big lines lost more"] }
          : { x: x(d.big), y: under, dx: 6, dy: 22, leader: true,
              color: ink("label"),
              text: ["the one storm that hit the big lines harder"] });
      }
    });

  kit.table(document.getElementById("t-f3"),
    ["storm", "worst day", "island lines", "big lines"],
    R.map(d => [d.storm, d.day, d.island + " %", d.big + " %"]));
}


/* ==================== F4 — what the battery ferry did ==================== */
function ellen() {
  const F = D.f4;
  kit.figure(document.getElementById("c-f4"),
    { ratio: 0.44, ratioNarrow: 0.86,
      margin: { top: 46, right: 26, bottom: 44, left: 56 },
      marginNarrow: { left: 50, right: 16 } },
    (g, w, h, narrow) => {
      const x = d3.scalePoint(F.years.map(String), [0, w]).padding(0.55);
      const lo = d3.min(F.minutes) - 7, hi = d3.max(F.minutes) + 5;
      const y = d3.scaleLinear([lo, hi], [h, 0]);
      kit.axis(g, y, { side: "left", ticks: 4, grid: w,
                       title: narrow ? "minutes" : "minutes for the crossing" });
      kit.axis(g, x, { side: "bottom", at: h });

      // one run per ship, so the line breaks where the ship changed and the
      // step is a change of vessel rather than a bend in one curve.
      const runs = [];
      F.vessel.forEach((v, i) => {
        if (i && v === F.vessel[i - 1]) runs[runs.length - 1].push(i);
        else runs.push([i]);
      });
      const line = d3.line().x(i => x(String(F.years[i]))).y(i => y(F.minutes[i]));
      runs.forEach((run, k) => {
        const colour = ink(k === runs.length - 1 ? "accent" : "working");
        g.append("path").attr("d", line(run)).attr("fill", "none")
          .attr("stroke", colour).attr("stroke-width", 2.6)
          .attr("stroke-linecap", "round");
        g.selectAll(null).data(run).join("circle")
          .attr("cx", i => x(String(F.years[i]))).attr("cy", i => y(F.minutes[i]))
          .attr("r", 5).attr("fill", colour);
        kit.halo(g.append("text")
          .attr("x", x(String(F.years[run[0]])))
          .attr("y", y(d3.max(run, i => F.minutes[i])) - 34)
          .attr("fill", ink(k === runs.length - 1 ? "accent-tx" : "label"))
          .style("font", `600 ${narrow ? 12 : 13.5}px ${SANS}`)
          .text(F.vessel[run[0]]));
      });
      // the axis does not start at zero, so every point carries its value.
      kit.halo(g.selectAll(null).data(d3.range(F.years.length)).join("text")
        .attr("x", i => x(String(F.years[i]))).attr("y", i => y(F.minutes[i]) - 14)
        .attr("text-anchor", "middle").attr("fill", ink("label"))
        .style("font", `500 12px ${MONO}`).text(i => F.minutes[i]));

      const step = F.vessel.findIndex(v => v === F.vessel[F.vessel.length - 1]);
      kit.note(g, { x: x(String(F.years[step])), y: y(F.minutes[step]),
        dx: narrow ? -14 : 16, dy: 34, leader: true,
        anchor: narrow ? "end" : "start", color: ink("accent-tx"),
        text: narrow ? ["a battery ferry", "took over"]
                     : ["a battery ferry took over the crossing"] });
    });

  kit.table(document.getElementById("t-f4"),
    ["year", "ship", "minutes for the crossing"],
    F.years.map((yr, i) => [yr, F.vessel[i], F.minutes[i]]));
}


lifeline();
winter();
storms();
ellen();
})();
