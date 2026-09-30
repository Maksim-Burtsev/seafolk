/* Seafolk — the charts on site/storms.html (chapter four).
 *
 * Four figures. T2 and T1 are the same fourteen storms read two ways, and the
 * page shows them in that order: T2 is the exact head count — a boat either
 * covered a mile that day or it did not — and every number in the prose comes
 * from it; T1 is the hour-by-hour message ratio underneath it, good for shape
 * and useless as a ruler. T3 is the negative result. T4 mounts the player S14
 * built (site/js/storm-player.js).
 *
 * Same rules as site/js/index.js: no colour literal anywhere — every hue is a
 * CSS variable read at draw time, so light and dark are one code path — and
 * the data comes from the page's own <script id="data"> block, written by
 * scripts/site_data/storms.py. Nothing is fetched.
 *
 * This file deliberately does NOT import index.js's storm panel. The two
 * pages draw the same shape with different emphasis (this one has all fourteen
 * storms, a URL parameter and the per-storm notes) and a shared function with
 * five flags in it would be worse than the fifty lines it saved.
 */
(function () {
"use strict";

const D = JSON.parse(document.getElementById("data").textContent);
const ink = kit.ink;
const Q = new URLSearchParams(location.search);
const pc = v => Math.round(100 * v) + " %";

/* Split a series into runs of consecutive x, so a line breaks over a hole in
 * the window instead of being drawn straight across it. */
const runs = (pts, gap) => pts.reduce((acc, p, i) => {
  if (i && p[0] - pts[i - 1][0] <= gap) acc[acc.length - 1].push(p);
  else acc.push([p]);
  return acc;
}, []);

/* "2018-09-21" + 1 day -> "21 September 2018"; two days -> "21–22 September". */
function when(start, days) {
  const from = d3.utcParse("%Y-%m-%d")(start);
  const to = d3.utcDay.offset(from, days - 1);
  return days > 1
    ? d3.utcFormat("%-d")(from) + "–" + d3.utcFormat("%-d %B %Y")(to)
    : d3.utcFormat("%-d %B %Y")(from);
}
const year = start => start.slice(0, 4);


/* ==================== T1 — one storm, every fleet ======================= */
/* Four public fleets, and no sailing line: hour by hour that fleet is a ratio
 * over a few dozen boats, it swings from 5 % to 418 % inside one storm, and it
 * pulled the eye straight off the claim. It is counted by the boat in T2,
 * where the number is exact. scripts/site_data/storms.py does not emit it. */
const LINES = [
  ["fishing", "fishing boats", "fishing", "accent",    2.8, null],
  ["cargo",   "cargo ships",   "cargo",   "ink",       2.2, null],
  ["ferries", "ferries",       "ferries", "working",   1.5, null],
  ["work",    "work boats",    "work",    "ref",       1.5, null],
];
const LABEL_INK = { fishing: "accent-tx", cargo: "ink", ferries: "working",
                    work: "ref" };
const CEILING = 150;

function panel() {
  const S = D.t1;
  const names = Object.keys(S.panels).sort((a, b) =>
    d3.ascending(S.panels[a].start, S.panels[b].start));
  // ?storm=amy picks a panel for a screenshot; anything unknown falls back to
  // the panel the build chose, so a stale link still renders the page.
  const asked = (Q.get("storm") || "").toLowerCase();
  let current = names.find(n => n.toLowerCase() === asked) || S.default;

  const keys = d3.select("#k-t1").selectAll("button").data(names).join("button")
    .attr("type", "button").text(d => d)
    .attr("aria-pressed", d => String(d === current))
    .on("click", (e, d) => {
      current = d;
      keys.attr("aria-pressed", k => String(k === d));
      redraw(); after();
    });

  let redraw = () => {};
  kit.figure(document.getElementById("c-t1"),
    { ratio: 0.46, ratioNarrow: 0.95,
      margin: { top: 30, right: 104, bottom: 46, left: 48 },
      marginNarrow: { right: 62, left: 46 } },
    (g, w, h, narrow) => { redraw = () => draw(g, w, h, narrow); redraw(); });

  function draw(g, w, h, narrow) {
    g.selectAll("*").remove();
    const P = S.panels[current];
    const hi = 24 * P.days + 71;
    const x = d3.scaleLinear([-72, hi], [0, w]);
    const y = d3.scaleLinear([0, CEILING], [h, 0]);

    g.append("rect").attr("x", x(0)).attr("width", x(24 * P.days) - x(0))
      .attr("y", 0).attr("height", h).attr("fill", ink("hairline")).attr("opacity", 0.55);
    // inside the plot, not above it: at 380 px the band above the frame belongs
    // to the y-axis title, and the two collide there.
    kit.halo(g.append("text").attr("x", x(12 * P.days)).attr("y", 13)
      .attr("text-anchor", "middle").attr("fill", ink("label"))
      .style("font", `500 ${narrow ? 11 : 12}px "IBM Plex Mono", ui-monospace, monospace`)
      .call(t => (narrow ? [current, when(P.start, P.days)]
                         : [`${current} · ${when(P.start, P.days)}`])
        .forEach((line, i) => t.append("tspan").attr("x", x(12 * P.days))
          .attr("dy", i ? "1.3em" : 0).text(line))));

    kit.axis(g, y, { side: "left", values: [0, 50, 100, 150], fmt: d => d + " %",
                     grid: w,
                     title: narrow ? "% of a normal day" : "movement, against a normal day" });
    kit.axis(g, x, { side: "bottom", at: h, values: d3.range(-48, hi, 48),
                     fmt: d => d === 0 ? (narrow ? "storm" : "the storm")
                       : (d > 0 ? "+" : "−") + Math.abs(d / 24) +
                         (narrow ? " d" : Math.abs(d) === 24 ? " day" : " days"),
                     title: narrow ? null : "days from the start of the storm" });
    g.append("line").attr("x1", 0).attr("x2", w).attr("y1", y(100)).attr("y2", y(100))
      .attr("stroke", ink("ref")).attr("stroke-dasharray", "4 4");

    const line = d3.line().x(d => x(d[0])).y(d => y(Math.min(d[1], CEILING)));
    const ends = [];
    LINES.forEach(([key, label, short, colour, width, dash]) => {
      const pts = P.lines[key];
      if (!pts) return;
      runs(pts, 1).forEach(run => g.append("path").attr("d", line(run))
        .attr("fill", "none").attr("stroke", ink(colour)).attr("stroke-width", width)
        .attr("stroke-dasharray", dash).attr("stroke-linecap", "round"));
      // a line over the top of the axis is marked rather than given a taller
      // axis: one winter night of work boats reaches four times a normal day
      // and would flatten every other line on the page. ONE triangle per
      // excursion, not one per hour — a fleet that spends a day over the
      // ceiling used to draw a picket fence along it.
      const over = pts.filter((d, i) => d[1] > CEILING
        && !(i && pts[i - 1][1] > CEILING && d[0] - pts[i - 1][0] === 1));
      g.selectAll(null).data(over).join("path")
        .attr("d", d3.symbol(d3.symbolTriangle, 26))
        .attr("transform", d => `translate(${x(d[0])},${y(CEILING) - 5})`)
        .attr("fill", ink(colour));
      ends.push({ y: y(Math.min(pts.at(-1)[1], CEILING)), text: narrow ? short : label,
                  color: ink(LABEL_INK[key]),
                  weight: key === "fishing" || key === "cargo" ? 600 : 500 });
    });
    kit.endLabels(g, w, ends);

    // The one annotation, and it sits on the claim the headline makes: where
    // the fishing line already is at the first midnight of the date the
    // weather service named — before any of the storm has happened. It points
    // left, into the run-up, because the storm band is to its right.
    const zero = P.lines.fishing.find(d => d[0] === 0);
    if (zero) kit.note(g, { x: x(0), y: y(Math.min(zero[1], CEILING)),
      dx: -10, dy: -18, leader: true, anchor: "end", color: ink("accent-tx"),
      text: narrow ? [`${Math.round(zero[1])} % when`, "the date began"]
                   : ["when the storm's own date began, fishing was",
                      `already at ${Math.round(zero[1])} % of a normal day`] });

    const flat = LINES.flatMap(([key, label]) =>
      (P.lines[key] || []).map(d => [d[0], d[1], label, LABEL_INK[key]]));
    kit.hover(g, w, h, (px, py) => {
      const d = d3.least(flat, p =>
        (x(p[0]) - px) ** 2 + (y(Math.min(p[1], CEILING)) - py) ** 2);
      return Math.abs(x(d[0]) - px) > 40 ? null : {
        x: x(d[0]), y: y(Math.min(d[1], CEILING)), color: ink(d[3]),
        text: `${d[2]}\n${(d[0] < 0 ? "" : "+") + (d[0] / 24).toFixed(1)} days\n${d[1]} % of a normal day` };
    });
  }

  /* The per-storm caveat, under the chart rather than in the caption: it is
   * different for every panel and two of the fourteen need one badly. */
  function after() {
    const P = S.panels[current];
    document.getElementById("n-t1").textContent = P.notes.length
      ? `${current}: ${P.notes.join("; ")}.` : "";
    const days = d3.range(-3, P.days + 3);
    kit.table(document.getElementById("t-t1"),
      [`${current} — % of a normal day`, ...days.map(d =>
        d < 0 ? `${d} d` : d < P.days ? `storm ${d + 1}` : `+${d - P.days + 1} d`)],
      LINES.filter(([k]) => P.lines[k]).map(([k, label]) => [label,
        ...days.map(dy => {
          const v = P.lines[k].filter(p => Math.floor(p[0] / 24) === dy);
          return v.length ? Math.round(d3.mean(v, p => p[1])) + " %" : "—";
        })]));
  }

  after();
}


/* ============ T2 — who was out at all, per storm (the page opens here) ==== */
/* Drawn: fishing and cargo, the two ends of the range, plus the sailing fleet
 * on the three storms where it was at sea. Ferries and work boats live in the
 * prose and in the table: on this axis they sit right on top of the two lines
 * the chart is about (work boats overlap fishing, ferries overlap cargo) and
 * five dumbbells a row is a picture of nothing. */
const T2_ROWS = [
  ["fishing", "fishing boats", "accent", "accent-tx", 3.0, 0],
  ["cargo",   "cargo ships",   "ink",    "ink",       2.2, 0],
  ["sailing", "sailing boats", "accent-tx", "accent-tx", 1.6, 7],
];
const T2_TABLE = [["fishing", "fishing"], ["work", "work boats"],
                  ["ferries", "ferries"], ["cargo", "cargo"],
                  ["sailing", "sailing"]];

function stayed() {
  const rows = D.t2.rows;
  kit.figure(document.getElementById("c-t2"),
    { ratio: 0.42, ratioNarrow: 1.12,
      margin: { top: 64, right: 26, bottom: 44, left: 112 },
      marginNarrow: { left: 88, right: 14, top: 58, bottom: 40 } },
    (g, w, h, narrow) => {
      const x = d3.scaleLinear([0, 100], [0, w]);
      const y = d3.scalePoint(rows.map(r => r.storm), [0, h]).padding(0.5);
      kit.axis(g, x, { side: "bottom", at: h, values: [0, 25, 50, 75, 100],
                       fmt: d => d + (narrow ? "" : " %"), grid: null,
                       title: narrow ? null
                         : "boats that covered a mile that day, out of every hundred heard" });
      // one rule per row, so a long dumbbell can be read back to its name
      g.selectAll(null).data(rows).join("line")
        .attr("x1", 0).attr("x2", w)
        .attr("y1", r => y(r.storm)).attr("y2", r => y(r.storm))
        .attr("stroke", ink("hairline"));

      rows.forEach(r => {
        T2_ROWS.forEach(([key, label, colour, tx, width, dy]) => {
          const v = r[key];
          if (!v) return;
          const yy = y(r.storm) + dy;
          const a = x(100 * v[0]), b = x(100 * v[1]);
          g.append("line").attr("x1", a).attr("x2", b).attr("y1", yy).attr("y2", yy)
            .attr("stroke", ink(colour)).attr("stroke-width", width)
            .attr("stroke-dasharray", key === "sailing" ? "3 3" : null)
            .attr("stroke-linecap", "round");
          g.append("circle").attr("cx", a).attr("cy", yy).attr("r", width + 1.4)
            .attr("fill", ink("surface")).attr("stroke", ink(colour))
            .attr("stroke-width", 1.6);
          g.append("circle").attr("cx", b).attr("cy", yy).attr("r", width + 1.4)
            .attr("fill", ink(colour));
        });
        g.append("text").attr("x", -12).attr("y", y(r.storm)).attr("dy", "0.34em")
          .attr("text-anchor", "end").attr("fill", ink("ink"))
          .style("font", `500 ${narrow ? 12 : 13}px "Source Serif 4", Georgia, serif`)
          .text(narrow ? r.storm : `${r.storm} · ${year(r.start)}`);
      });

      // the two named groups, over the first row — a legend would be a box off
      // to the side, which this site does not draw.
      const top = rows[0];
      [["fishing", top.fishing], ["cargo", top.cargo]].forEach(([key, v]) => {
        const [, label, , tx] = T2_ROWS.find(t => t[0] === key);
        kit.halo(g.append("text")
          .attr("x", x(100 * (v[0] + v[1]) / 2)).attr("y", y(top.storm) - 42)
          .attr("text-anchor", "middle").attr("fill", ink(tx))
          .style("font", `600 ${narrow ? 11 : 13}px "Source Serif 4", Georgia, serif`)
          .text(narrow ? label.split(" ")[0] : label));
      });
      const sail = rows.find(r => r.sailing);
      if (sail && !narrow) kit.halo(g.append("text")
        .attr("x", x(100 * sail.sailing[0]) + 10).attr("y", y(sail.storm) + 7)
        .attr("dy", "0.34em").attr("fill", ink("accent-tx"))
        .style("font", '500 12px "Source Serif 4", Georgia, serif')
        .text("sailing boats"));

      // The point of the chart a reader does not already expect, written under
      // the cargo label rather than pointed at from inside the plot: the
      // channel between the two clusters looks empty and is not — it is where
      // the three sailing dumbbells run.
      kit.note(g, { x: narrow ? w : x(100 * (top.cargo[0] + top.cargo[1]) / 2),
        y: y(top.storm) - 22, anchor: narrow ? "end" : "middle",
        color: ink("label"),
        text: narrow ? ["four in five moved anyway"]
                     : ["about four in five moved anyway, in every storm"] });

      kit.hover(g, w, h, (px, py) => {
        let best = null;
        rows.forEach(r => T2_ROWS.forEach(([key, label]) => {
          const v = r[key];
          if (!v) return;
          const dy = key === "sailing" ? 7 : 0;
          [0, 1].forEach(i => {
            const d = (x(100 * v[i]) - px) ** 2 + (y(r.storm) + dy - py) ** 2;
            if (!best || d < best.d)
              best = { d, x: x(100 * v[i]), y: y(r.storm) + dy, color: ink(T2_ROWS.find(t => t[0] === key)[2]),
                       text: `${r.storm} · ${label}\n${pc(v[i])} covered a mile\n${i ? "on the storm's dates" : "a fortnight earlier"}` };
          });
        }));
        return best && best.d < 900 ? best : null;
      });
    });

  kit.table(document.getElementById("t-t2"),
    ["storm", ...T2_TABLE.flatMap(([, label]) => [`${label}, usual`, `${label}, storm`])],
    rows.map(r => [`${r.storm} · ${year(r.start)}`,
      ...T2_TABLE.flatMap(([key]) => r[key] ? [pc(r[key][0]), pc(r[key][1])] : ["—", "—"])]));
}


/* ======================= T3 — the anchorages =========================== */
function anchorages() {
  const A = D.t3;
  const by = d3.group(A.rows, r => r.name);
  kit.figure(document.getElementById("c-t3"),
    { ratio: 0.36, ratioNarrow: 0.9,
      margin: { top: 34, right: 26, bottom: 46, left: 132 },
      marginNarrow: { left: 104, right: 16, bottom: 42 } },
    (g, w, h, narrow) => {
      const lo = Math.min(0.4, d3.min(A.rows, r => r.ratio) - 0.05);
      const hi = Math.max(1.7, d3.max(A.rows, r => r.ratio) + 0.05);
      const x = d3.scaleLinear([lo, hi], [0, w]);
      const y = d3.scalePoint(A.names, [0, h]).padding(0.6);
      kit.axis(g, x, { side: "bottom", at: h,
                       values: narrow ? [0.5, 1, 1.5] : [0.5, 0.75, 1, 1.25, 1.5],
                       fmt: d => d === 1 ? "same" : "×" + d,
                       title: narrow ? null
                         : "ships at anchor during the storm, against the three days before" });

      // the whole chart is a claim about one vertical line, so the line is the
      // accent and every dot is ink.
      g.append("line").attr("x1", x(1)).attr("x2", x(1)).attr("y1", -18).attr("y2", h)
        .attr("stroke", ink("accent")).attr("stroke-width", 2);
      kit.halo(g.append("text").attr("x", x(1)).attr("y", -24)
        .attr("text-anchor", "middle").attr("fill", ink("accent-tx"))
        .style("font", '600 13px "Source Serif 4", Georgia, serif')
        .text("no change"));

      A.names.forEach(name => {
        g.append("line").attr("x1", 0).attr("x2", w)
          .attr("y1", y(name)).attr("y2", y(name)).attr("stroke", ink("hairline"));
        g.append("text").attr("x", -12).attr("y", y(name)).attr("dy", "0.34em")
          .attr("text-anchor", "end").attr("fill", ink("ink"))
          .style("font", `500 ${narrow ? 11.5 : 13}px "Source Serif 4", Georgia, serif`)
          .text(name);
        // filled and half-transparent, so that a pile of storms on one spot
        // reads as a pile rather than as a moiré of rings
        (by.get(name) || []).forEach(r => g.append("circle")
          .attr("cx", x(r.ratio)).attr("cy", y(name)).attr("r", 5.5)
          .attr("fill", ink("working")).attr("opacity", 0.55));
      });

      const worst = d3.least(A.rows, r => r.ratio);
      kit.note(g, { x: x(worst.ratio), y: y(worst.name), dx: 10, dy: -26,
        leader: true, color: ink("label"),
        text: narrow ? ["the one that moved most", "emptied, not filled"]
                     : [`the one that moved most emptied — ${worst.name},`,
                        `under ${worst.storm}`] });

      kit.hover(g, w, h, (px, py) => {
        const d = d3.least(A.rows, r =>
          (x(r.ratio) - px) ** 2 + (y(r.name) - py) ** 2);
        return Math.abs(y(d.name) - py) > 18 ? null : {
          x: x(d.ratio), y: y(d.name), color: ink("working"),
          text: `${d.name} · ${d.storm}\n${d.pre} ships an hour before\n${d.during} during the storm` };
      });
    });

  kit.table(document.getElementById("t-t3"),
    ["storm", ...A.names],
    [...d3.group(A.rows, r => r.storm).entries()].map(([storm, rs]) =>
      [storm, ...A.names.map(n => {
        const r = rs.find(v => v.name === n);
        return r ? "×" + r.ratio.toFixed(2) : "—";
      })]));
}


/* ======================== T4 — the animation ============================ */
function sea() {
  const host = document.getElementById("c-t4");
  const first = D.t4.default;
  // Same behaviour as I6 on the story page: the figure keeps its place and
  // says what went wrong, rather than leaving a captioned empty box.
  if (!window.SeafolkStorm || !window.SEAFOLK_LAND) {
    host.textContent = "The animation could not be loaded — open "
      + `site/media/storm-${first}.mp4`;
    return;
  }
  SeafolkStorm.load(D.t4.clips, got =>
    got.length ? mountAll(host, got) : SeafolkStorm.unavailable(host, first));
}


function mountAll(host, clips) {
  const asked = (Q.get("clip") || Q.get("storm") || "").toLowerCase();
  let current = clips.includes(asked) ? asked
    : (clips.includes(D.t4.default) ? D.t4.default : clips[0]);
  let player = null;

  const keys = d3.select("#k-t4").selectAll("button").data(clips).join("button")
    .attr("type", "button").text(k => window.SEAFOLK_STORM[k].name)
    .attr("aria-pressed", k => String(k === current))
    .on("click", (e, k) => {
      current = k;
      keys.attr("aria-pressed", j => String(j === k));
      mount();
    });

  function mount() {
    if (player) player.destroy();
    player = SeafolkStorm.mount(host, current);
  }
  mount();
}


stayed();
panel();
anchorages();
sea();
})();
