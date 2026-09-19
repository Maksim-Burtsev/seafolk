/* Seafolk — the charts on "The sea by the hour".
 *
 * One function per figure, each drawing into the responsive frame that
 * site/js/kit.js provides. No chart here knows a colour literal: every hue is a
 * CSS variable from site/css/site.css, read at draw time, so light and dark are
 * the same code.
 *
 * The data comes from the page's own <script type="application/json" id="data">
 * block, written by scripts/site_data/pulse.py. Nothing is fetched.
 *
 * The dial geometry is the one prototyped for the S3 day clocks and
 * reproduced by notes/plot_ch02.py: midnight at the top, hours clockwise, an
 * inner hole, and the radius linear in the hour's share of the fleet's own day
 * up to PEAK at the rim. Three drawings of one shape, so a reader who meets it
 * twice meets the same thing.
 */
(function () {
"use strict";

const D = JSON.parse(document.getElementById("data").textContent);
const ink = kit.ink;

/* key, the reader's word, whether this is the fleet the page is about. */
const FLEETS = [["sailing", "sailing boats", true],
                ["ferries", "ferries", false],
                ["cargo", "cargo ships", false],
                ["fishing", "fishing boats", false]];
const FLAT_DAY = 100 / 24;             // 4.17 % — a day with no rhythm
const FLAT_WEEK = 100 / 168;           // 0.60 % — a week with no shape
const PEAK = 13;                       // the share that reaches a dial's rim
const DOW = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
             "Saturday", "Sunday"];
/* The four hours a clock face needs named, in words rather than in numbers:
 * a reader who has to work out which way round the dial goes has already been
 * lost (docs/SITE.md § Chart rules). */
const MARKS = [[0, "midnight"], [6, "6 am"], [12, "noon"], [18, "6 pm"]];
const hhmm = h => String(h).padStart(2, "0") + ":00";


/* ====================== P1 — four fleets, four clocks =================== */
/* 0 degrees is straight up; hours run clockwise, as on a clock. */
const rad = deg => (deg - 90) * Math.PI / 180;
const at = (cx, cy, deg, r) => [cx + r * Math.cos(rad(deg)),
                                cy + r * Math.sin(rad(deg))];

function wedge(cx, cy, hour, r0, r1) {
  const half = 7.5 - 0.9, c = hour * 15;          // a 15 deg hour, gapped
  const [x1, y1] = at(cx, cy, c - half, r0), [x2, y2] = at(cx, cy, c - half, r1);
  const [x3, y3] = at(cx, cy, c + half, r1), [x4, y4] = at(cx, cy, c + half, r0);
  return `M${x1} ${y1}L${x2} ${y2}A${r1} ${r1} 0 0 1 ${x3} ${y3}`
       + `L${x4} ${y4}A${r0} ${r0} 0 0 0 ${x1} ${y1}Z`;
}

function clocks() {
  let dials = [];                       // rebuilt on every resize and theme flip
  let playing = false, raf = 0, started = 0;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)");
  const bar = d3.select("#k-p1");
  const button = bar.append("button").attr("type", "button")
    .attr("aria-pressed", "false").text("play the day")
    .on("click", () => (playing ? stop() : start()));
  const readout = bar.append("span").attr("class", "source")
    .attr("aria-live", "polite");

  /* The hand, and the hour it is over. `t` is a float hour so the hand sweeps;
   * the wedge it lights up is the whole hour under it. A reader who has asked
   * for less motion gets the same walk through the day in whole-hour steps
   * instead of a sweep — the information is the point, the movement is not. */
  function apply(t) {
    const on = t !== null;
    const hour = on ? Math.floor(t) % 24 : -1;
    dials.forEach(d => {
      d.wedges.attr("fill", (v, i) => i === hour ? ink("ink") : d.fill);
      const [hx, hy] = at(d.cx, d.cy, (on ? t : 0) * 15, d.R);
      const [bx, by] = at(d.cx, d.cy, (on ? t : 0) * 15, d.rIn);
      d.hand.attr("x1", bx).attr("y1", by).attr("x2", hx).attr("y2", hy)
        .attr("opacity", on ? 1 : 0);
    });
    readout.text(on ? hhmm(hour) + " · " + FLEETS
      .map(([key, label]) => `${label} ${D.clocks[key][hour].toFixed(1)} %`)
      .join(" · ") : "");
  }

  function frame(now) {
    if (!started) started = now;
    const t = (now - started) / 1000 * (24 / 14) % 24;   // a day in 14 seconds
    apply(reduce.matches ? Math.floor(t) : t);
    raf = requestAnimationFrame(frame);
  }
  function start() {
    playing = true; started = 0; raf = requestAnimationFrame(frame);
    button.text("pause").attr("aria-pressed", "true");
  }
  function stop() {
    playing = false; cancelAnimationFrame(raf); apply(null);
    button.text("play the day").attr("aria-pressed", "false");
  }

  kit.figure(document.getElementById("c-p1"),
    { ratio: 0.30, ratioNarrow: 1.5,
      margin: { top: 6, right: 4, bottom: 10, left: 4 },
      marginNarrow: { top: 6, right: 4, bottom: 10, left: 4 } },
    (g, w, h, narrow) => {
      // four across on a screen, two by two on a phone. The radius is whatever
      // is left once the fleet's name has its band above the dial and the word
      // "noon" has room below it.
      // `foot` is what is left under the word "noon": at 380 px the next row's
      // fleet name is under it and the two read as one caption unless the rows
      // are pushed apart.
      const cols = narrow ? 2 : 4, band = narrow ? 24 : 30, gap = narrow ? 18 : 24;
      const foot = narrow ? 30 : 14;
      const cw = w / cols, ch = h / (4 / cols);
      const R = Math.min(cw / 2 - 4, (ch - band - gap - foot) / 2);
      const rIn = R * 0.22;
      const rv = v => rIn + Math.min(v, PEAK) / PEAK * (R - rIn);

      dials = FLEETS.map(([key, label, subject], i) => {
        const cx = (i % cols) * cw + cw / 2;
        const top = Math.floor(i / cols) * ch;
        const cy = top + band + gap + R;
        const fill = ink(subject ? "accent" : "working");
        const d = g.append("g");

        d.append("text").attr("x", cx).attr("y", top + band - 11)
          .attr("text-anchor", "middle")
          .attr("fill", ink(subject ? "accent-tx" : "ink"))
          .style("font", `${subject ? 600 : 500} ${narrow ? 12 : 15}px Karla, ui-sans-serif, sans-serif`)
          .text(label);
        d.append("circle").attr("cx", cx).attr("cy", cy).attr("r", rv(FLAT_DAY))
          .attr("fill", "none").attr("stroke", ink("ref"))
          .attr("stroke-dasharray", "3 3");
        const wedges = d.selectAll(null).data(D.clocks[key]).join("path")
          .attr("d", (v, hour) => wedge(cx, cy, hour, rIn, rv(v)))
          .attr("fill", fill);

        // midnight and noon outside the rim, six and eighteen inside it: only
        // the sailing dial reaches past four fifths of its radius, and it does
        // so at noon, so the two side words never sit on a wedge.
        MARKS.forEach(([hour, text]) => {
          const out = hour % 12 === 0;
          const [tx, ty] = at(cx, cy, hour * 15, out ? R + 12 : R * 0.80);
          kit.halo(d.append("text").attr("x", tx).attr("y", ty)
            .attr("text-anchor", "middle").attr("dominant-baseline", "central")
            .attr("fill", ink("label"))
            .style("font", `400 ${narrow ? 9 : 11}px "IBM Plex Mono", ui-monospace, monospace`)
            .text(text));
        });
        const hand = d.append("line").attr("stroke", ink("ink"))
          .attr("stroke-width", 2).attr("stroke-linecap", "round")
          .attr("opacity", 0).style("pointer-events", "none");
        return { key, label, cx, cy, R, rIn, rv, wedges, hand, fill,
                 colour: ink(subject ? "accent-tx" : "ink") };
      });
      apply(playing ? 0 : null);

      kit.hover(g, w, h, (px, py) => {
        for (const d of dials) {
          const dx = px - d.cx, dy = py - d.cy;
          if (Math.hypot(dx, dy) > d.R + 6) continue;
          const a = (Math.atan2(dx, -dy) * 180 / Math.PI + 360) % 360;
          const hour = Math.round(a / 15) % 24, v = D.clocks[d.key][hour];
          const [x, y] = at(d.cx, d.cy, hour * 15, d.rv(v));
          return { x, y, color: d.colour,
                   text: `${d.label}\n${hhmm(hour)}\n${v} % of the day` };
        }
        return null;
      });
    });

  kit.table(document.getElementById("t-p1"),
    ["hour", ...FLEETS.map(f => f[1])],
    d3.range(24).map(hour => [hhmm(hour),
      ...FLEETS.map(([key]) => D.clocks[key][hour].toFixed(2) + " %")]));
}


/* ======================= P2 — the sailing week ========================== */
function week() {
  const W = D.week;
  const SERIES = [["sailing", "sailing boats", "accent", "accent-tx", 2.4],
                  ["cargo", "cargo ships", "working", "working", 2]];
  kit.figure(document.getElementById("c-p2"),
    { ratio: 0.42, ratioNarrow: 0.92,
      margin: { top: 28, right: 16, bottom: 46, left: 48 },
      marginNarrow: { left: 40, right: 10, bottom: 44 } },
    (g, w, h, narrow) => {
      const x = d3.scaleLinear([0, 167], [0, w]);
      const y = d3.scaleLinear([0, d3.max(W.sailing) * 1.16], [h, 0]);

      // Saturday and Sunday, shaded. The two tallest bells stand inside it and
      // that is the whole of the chart's first sentence.
      g.append("rect").attr("x", x(120)).attr("width", w - x(120))
        .attr("y", 0).attr("height", h)
        .attr("fill", ink("hairline")).attr("opacity", 0.5);
      kit.halo(g.append("text").attr("x", (x(120) + w) / 2).attr("y", -9)
        .attr("text-anchor", "middle").attr("fill", ink("label"))
        .style("font", `500 ${narrow ? 10 : 11.5}px "IBM Plex Mono", ui-monospace, monospace`)
        .text(narrow ? "the weekend" : "Saturday and Sunday"));

      kit.axis(g, y, { side: "left", values: [0, 1, 2], fmt: d => d + " %",
                       grid: w,
                       title: narrow ? "% of the week" : "% of the fleet's week, in that hour" });
      kit.axis(g, x, { side: "bottom", at: h, values: [] });
      for (let d = 1; d < 7; d++)
        g.append("line").attr("x1", x(24 * d)).attr("x2", x(24 * d))
          .attr("y1", 0).attr("y2", h).attr("stroke", ink("hairline"));
      for (let d = 0; d < 7; d++)
        g.append("text").attr("x", x(24 * d + 12)).attr("y", h + 18)
          .attr("text-anchor", "middle").attr("fill", ink("label"))
          .style("font", '400 12px "IBM Plex Mono", ui-monospace, monospace')
          .text(narrow ? DOW[d][0] : DOW[d].slice(0, 3));
      g.append("line").attr("x1", 0).attr("x2", w)
        .attr("y1", y(FLAT_WEEK)).attr("y2", y(FLAT_WEEK))
        .attr("stroke", ink("ref")).attr("stroke-dasharray", "4 4");

      const line = d3.line().x((v, i) => x(i)).y(v => y(v));
      SERIES.forEach(([key, , colour, , width]) =>
        g.append("path").attr("d", line(W[key])).attr("fill", "none")
          .attr("stroke", ink(colour)).attr("stroke-width", width)
          .attr("stroke-linejoin", "round"));

      // direct labels, each over its own line where nothing else is: the
      // sailing name above the Thursday bell, the cargo name over Monday night.
      kit.halo(g.append("text").attr("x", x(84)).attr("y", y(W.sailing[84]) - 12)
        .attr("text-anchor", "middle").attr("fill", ink("accent-tx"))
        .style("font", `600 ${narrow ? 12 : 13.5}px Karla, ui-sans-serif, sans-serif`)
        .text("sailing boats"));
      kit.halo(g.append("text").attr("x", x(2)).attr("y", y(W.cargo[2]) - 15)
        .attr("fill", ink("working"))
        .style("font", `500 ${narrow ? 12 : 13.5}px Karla, ui-sans-serif, sans-serif`)
        .text("cargo ships"));

      // the one annotation, anchored at its END so that the leader leaves the
      // peak on the side the text is not on. A kit.note leader stops 5 px past
      // the anchor, so pointing at something to the RIGHT of the text and
      // anchoring "start" draws the line straight through the words.
      const top = d3.maxIndex(W.sailing);
      kit.note(g, { x: x(top), y: y(W.sailing[top]), dx: -14, dy: -11,
        anchor: "end", leader: true, color: ink("accent-tx"),
        text: narrow ? ["Sunday noon: the busiest hour"]
                     : ["Sunday noon — the busiest hour of the sailing week"] });

      kit.hover(g, w, h, px => {
        const slot = Math.max(0, Math.min(167, Math.round(x.invert(px))));
        return { x: x(slot), y: y(W.sailing[slot]), color: ink("accent"),
                 text: `${DOW[slot / 24 | 0]} ${hhmm(slot % 24)}\n`
                     + SERIES.map(([key, label]) =>
                         `${label} ${W[key][slot].toFixed(2)} %`).join("\n") };
      });
    });

  kit.table(document.getElementById("t-p2"),
    ["day", ...SERIES.map(s => s[1] + ", % of the week"),
     "sailing boats, busiest hour"],
    DOW.map((name, d) => {
      const day = W.sailing.slice(24 * d, 24 * d + 24);
      return [name, ...SERIES.map(([key]) =>
        d3.sum(W[key].slice(24 * d, 24 * d + 24)).toFixed(1) + " %"),
        hhmm(d3.maxIndex(day))];
    }));
}


/* ==================== P3 — one marina, hour by hour ===================== */
function harbour() {
  const H = D.harbour;
  kit.figure(document.getElementById("c-p3"),
    { ratio: 0.46, ratioNarrow: 1.22,
      margin: { top: 22, right: 18, bottom: 46, left: 56 },
      // at 380 px every part of the plot is occupied by a bar, so the note
      // moves out of it and becomes a standfirst in the top margin.
      marginNarrow: { top: 72, left: 44, right: 10 } },
    (g, w, h, narrow) => {
      const x = d3.scaleBand(d3.range(24), [0, w]).padding(0.24);
      const span = d3.max([...H.appeared, ...H.vanished]) * 1.2;
      const y = d3.scaleLinear([-span, span], [h, 0]);
      const bw = x.bandwidth();

      kit.axis(g, y, { side: "left", values: [-6, -3, 0, 3, 6],
                       fmt: d => Math.abs(d), grid: w, title: "boats an hour" });
      kit.axis(g, x, { side: "bottom", at: h, values: MARKS.map(m => m[0]),
                       fmt: d => MARKS.find(m => m[0] === d)[1] });

      // pale = everything that appeared (vanished); solid = the part of it that
      // was in the water next door an hour before.
      const bars = (values, sign, opacity) => g.selectAll(null).data(values)
        .join("rect").attr("x", (v, i) => x(i)).attr("width", bw)
        .attr("y", v => sign > 0 ? y(v) : y(0))
        .attr("height", v => Math.abs(y(v) - y(0)))
        .attr("fill", ink("accent")).attr("opacity", opacity);
      bars(H.appeared, 1, 0.34);
      bars(H.vanished.map(v => -v), -1, 0.34);
      bars(H.from_ring, 1, 1);
      bars(H.to_ring.map(v => -v), -1, 1);
      g.append("line").attr("x1", 0).attr("x2", w).attr("y1", y(0)).attr("y2", y(0))
        .attr("stroke", ink("label"));

      // which half of the axis is which, at the quiet end of the day rather
      // than over the y-axis title.
      [[span * 0.92, "boats appearing"], [-span * 0.92, "boats disappearing"]]
        .forEach(([v, text]) => kit.halo(g.append("text").attr("x", w).attr("y", y(v))
          .attr("dy", "0.34em").attr("text-anchor", "end").attr("fill", ink("label"))
          .style("font", `500 ${narrow ? 11 : 13}px Karla, ui-sans-serif, sans-serif`)
          .text(text)));

      // the point of the chart, pointing into the pale half of the noon bar.
      // Anchored at its end so the leader leaves the bar on the side the text
      // is not on; at 380 px there is no room for a leader at all, so the note
      // sits alone in the empty small hours (the same trick as chart I5).
      const hour = 12, mid = (H.appeared[hour] + H.from_ring[hour]) / 2;
      kit.note(g, narrow
        ? { x: 0, y: -58,
            text: ["the pale part had no trace on the", "water an hour before:",
                   "a radio switching on at the berth"],
            color: ink("accent-tx") }
        : { x: x(hour) + bw / 2, y: y(mid),
            dx: x(10) - x(hour) - bw / 2, dy: y(span * 0.82) - y(mid),
            anchor: "end", leader: true, color: ink("accent-tx"),
            text: ["the pale part had no trace on the water an hour",
                   "earlier — a radio switching on at the berth"] });

      kit.hover(g, w, h, px => {
        const i = Math.max(0, Math.min(23, Math.floor(px / x.step())));
        return { x: x(i) + bw / 2, y: y(H.appeared[i]), color: ink("accent"),
                 text: `${hhmm(i)}\n${H.appeared[i]} boats appeared\n`
                     + `${H.vanished[i]} boats left` };
      });
    });

  kit.table(document.getElementById("t-p3"),
    ["hour", "appeared", "of those, from next door", "disappeared",
     "of those, to next door"],
    d3.range(24).map(i => [hhmm(i), H.appeared[i], H.from_ring[i],
                           H.vanished[i], H.to_ring[i]]));
}


clocks();
week();
harbour();

/* ?play starts the clock hand on load, for the same reason kit.js has ?only and
 * ?theme: scripts/shot.sh can photograph a page but it cannot press a button,
 * and the moving state of P1 is something a reviewer has to be able to see. */
if (new URLSearchParams(location.search).has("play"))
  document.querySelector("#k-p1 button").click();
})();
