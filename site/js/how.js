/* Seafolk — the three figures on "How it was made".
 *
 * Two diagrams and one chart, all three built the way every other figure on
 * this site is: a function that draws into the frame site/js/kit.js provides,
 * with no colour literal anywhere — the hues are CSS variables from
 * site/css/site.css, read at draw time, so light and dark are the same code
 * and the screenshots need no second stylesheet.
 *
 * The numbers come from the page's own <script type="application/json" id="data">
 * block, written by scripts/site_data/how.py. Nothing is fetched and nothing is
 * typed here — including the seven hexagons of H1, which are an illustration
 * and are declared as one in the module that invents them.
 */
(function () {
"use strict";

const D = JSON.parse(document.getElementById("data").textContent);
const ink = kit.ink;
const FONT = '"Source Serif 4", Georgia, serif';
const MONO = '"IBM Plex Mono", ui-monospace, monospace';

/* A pointy-top hexagon of radius r, centred on the origin. */
const hexPath = r => d3.range(6)
  .map(i => [r * Math.sin(i * Math.PI / 3), -r * Math.cos(i * Math.PI / 3)])
  .map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + "," + p[1].toFixed(1))
  .join("") + "Z";

/* n dots in rows of at most four, centred on the origin, in grid units. Few
 * enough that a reader counts them instead of reading a number, which is the
 * only reason to draw the rule rather than state it. */
function dots(n) {
  const per = n <= 3 ? n : n <= 8 ? Math.ceil(n / 2) : 4;
  const rows = [];
  for (let left = n; left > 0; left -= per) rows.push(Math.min(per, left));
  return rows.flatMap((count, r) => d3.range(count).map(c =>
    [c - (count - 1) / 2, r - (rows.length - 1) / 2]));
}


/* ================= H1 — the rule, drawn ================================= */
function picture() {
  const P = D.picture;
  const wide = Math.max(...P.rows.map(r => r.length));

  kit.figure(document.getElementById("c-h1"),
    { ratio: 0.46, ratioNarrow: 0.80,
      margin: { top: 12, right: 10, bottom: 14, left: 10 } },
    (g, w, h, narrow) => {
      // each hexagon owns its own width plus the type underneath it; the half
      // cell on the right is where the offset second row hangs. On a phone
      // "not published" is wider than a hexagon, so there it takes two lines.
      const label = narrow ? 28 : 22;
      const mark = narrow ? ["not", "published"] : ["not published"];
      const r = Math.min(w / ((wide + 0.5) * Math.sqrt(3)),
                         (h - label * P.rows.length) / (2 * P.rows.length + 0.4));
      const sx = Math.sqrt(3) * r, sy = 2 * r + label;
      const y0 = (h - sy * P.rows.length) / 2 + r;

      P.rows.forEach((row, ri) => {
        const x0 = (w - sx * row.length) / 2 + sx / 2 + (ri % 2 ? sx / 2 : 0);
        row.forEach((n, ci) => {
          const kept = n >= P.floor;
          const cell = g.append("g")
            .attr("transform", `translate(${x0 + ci * sx},${y0 + ri * sy})`);
          cell.append("path").attr("d", hexPath(r * 0.93))
            .attr("fill", kept ? ink("surface") : "none")
            .attr("stroke", kept ? ink("accent") : ink("ref"))
            .attr("stroke-width", kept ? 2.2 : 1)
            .attr("stroke-dasharray", kept ? null : "4 4");
          cell.selectAll(null).data(dots(n)).join("circle")
            .attr("cx", d => d[0] * r * 0.40).attr("cy", d => d[1] * r * 0.42)
            .attr("r", Math.max(2.4, r * 0.085))
            .attr("fill", kept ? ink("accent") : ink("ref"));
          cell.append("text").attr("y", r + (narrow ? 15 : label * 0.66))
            .attr("text-anchor", "middle")
            .attr("fill", kept ? ink("accent-tx") : ink("label"))
            .style("font", `${kept ? 500 : 400} ${narrow ? 10 : 12}px ${MONO}`)
            .call(t => (kept ? [n] : mark).forEach((line, k) =>
              t.append("tspan").attr("x", 0).attr("dy", k ? "1.15em" : 0).text(line)));
        });
      });

      // the instructive cell is the one that is a single boat short, and it is
      // the only thing on this figure that needs saying in words.
      const short = P.rows[0].indexOf(P.floor - 1);
      if (short >= 0) {
        const x0 = (w - sx * P.rows[0].length) / 2 + sx / 2;
        kit.note(g, { x: x0 + short * sx, y: y0 - r, dy: -8, anchor: "middle",
          color: ink("label"),
          text: narrow ? "one short" : "four boats — one short" });
      }
    });
}


/* ================= H2 — what the rule costs ============================= */
function cost() {
  const F = D.floor;
  const bars = [{ key: "map squares", value: F.cells_pct, accent: false },
                { key: "boat movement", value: F.moving_pct, accent: true }];

  kit.figure(document.getElementById("c-h2"),
    { ratio: 0.32, ratioNarrow: 0.68,
      margin: { top: 14, right: 16, bottom: 46, left: 16 } },
    (g, w, h, narrow) => {
      const x = d3.scaleLinear([0, 100], [0, w]);
      const row = h / 2, bh = Math.min(40, row * 0.42);

      bars.forEach((b, i) => {
        const y = i * row + row * 0.48;
        const colour = ink(b.accent ? "accent" : "working");
        g.append("text").attr("y", y - 11).attr("fill", ink("ink"))
          .style("font", `${b.accent ? 600 : 400} ${narrow ? 14.5 : 17}px ${FONT}`)
          .text(b.key + " kept by the rule");
        g.append("rect").attr("y", y).attr("width", w).attr("height", bh)
          .attr("fill", ink("hairline"));
        g.append("rect").attr("y", y).attr("width", x(b.value)).attr("height", bh)
          .attr("fill", colour);
        // outside the bar the label needs a halo to clear the track; inside it
        // sits on solid colour, where a halo in the surface tone would eat it.
        const out = b.value < 55;
        const t = g.append("text")
          .attr("x", x(b.value) + (out ? 10 : -10))
          .attr("y", y + bh / 2).attr("dy", "0.36em")
          .attr("text-anchor", out ? "start" : "end")
          .attr("fill", out ? colour : ink("surface"))
          .style("font", `500 ${narrow ? 15 : 18}px ${MONO}`)
          .text(Math.round(b.value) + " %");
        if (out) kit.halo(t);
      });

      kit.axis(g, x, { side: "bottom", at: h, values: [0, 50, 100],
                       fmt: d => d + " %",
                       title: narrow ? "of what the private fleet left behind"
                                     : "of everything the private fleet left behind" });
    });

  kit.table(document.getElementById("t-h2"),
    ["counted as", "published", "dropped by the rule"],
    [["map squares", F.cells_pct + " %", (100 - F.cells_pct).toFixed(1) + " %"],
     ["boat movement", F.moving_pct + " %", (100 - F.moving_pct).toFixed(1) + " %"]]);
}


/* ================= H3 — the pipeline ==================================== */
function pipeline() {
  const n = D.n;
  const steps = [
    { tag: "the archive", big: n.pulled_tb + " TB",
      lines: ["of zip files, downloaded", "from a Danish web server"] },
    { tag: "one file at a time", big: n.files,
      lines: ["downloaded, unzipped and", "streamed into the database"] },
    { tag: "counted", big: n.rows_billion + " billion",
      lines: ["lines of radio, added up", "per hexagon per hour"] },
    { tag: "what is left", big: n.store_gb + " GB",
      lines: ["of counts — " + n.days + " days,", "charts, a map, a dataset"] }];
  const loop = ["the zip is deleted, the next one starts",
                "— " + n.files + " times"];

  kit.figure(document.getElementById("c-h3"),
    { ratio: 0.26, ratioNarrow: 1.80,
      margin: { top: 10, right: 10, bottom: 10, left: 10 } },
    (g, w, h, narrow) => {
      // wide: four boxes in a row, the return loop in the strip below them.
      // narrow: four boxes in a column, the loop in a gutter down the right
      // and its label in the widened gap under "counted", which is the box the
      // loop leaves from. GAPS are the space AFTER each box.
      const gutter = 40, gap = 24;
      const GAPS = [gap, gap, 64, gap];
      const bw = narrow ? w - gutter : (w - 3 * 30) / 4;
      const bh = narrow ? (h - d3.sum(GAPS)) / 4 : Math.min(118, h * 0.55);
      const top = i => i * bh + d3.sum(GAPS.slice(0, i));
      const step = bw + 30;

      steps.forEach((s, i) => {
        const b = g.append("g").attr("transform",
          narrow ? `translate(0,${top(i)})` : `translate(${i * step},0)`);
        b.append("rect").attr("width", bw).attr("height", bh)
          .attr("fill", ink("surface")).attr("stroke", ink("hairline"));
        b.append("text").attr("x", 15).attr("y", 22).attr("fill", ink("label"))
          .style("font", `500 11px ${MONO}`).style("letter-spacing", ".14em")
          .text(s.tag.toUpperCase());
        b.append("text").attr("x", 15).attr("y", 50)
          .attr("fill", ink(i === 3 ? "accent-tx" : "ink"))
          .style("font", `500 23px ${MONO}`).text(s.big);
        s.lines.forEach((line, k) => b.append("text")
          .attr("x", 15).attr("y", 72 + k * 17).attr("fill", ink("label"))
          .style("font", `400 13px ${FONT}`).text(line));

        if (i < 3) {                       // the arrow into the next box
          // narrow keeps the arrows off to the right so that the loop's two
          // lines of type can sit in the widened gap without being crossed.
          const run = (narrow ? GAPS[i] : 30) - 12;
          const a = b.append("g").attr("stroke", ink("ref"))
            .attr("stroke-width", 1.6).attr("fill", "none")
            .attr("transform", narrow ? `translate(${bw - 24},${bh + 6})`
                                      : `translate(${bw + 6},${bh / 2})`);
          a.append("line").attr("x2", narrow ? 0 : run).attr("y2", narrow ? run : 0);
          a.append("path").attr("d", narrow
            ? `M-4,${run - 6} L0,${run} L4,${run - 6}`
            : `M${run - 6},-4 L${run},0 L${run - 6},4`);
        }
      });

      // The loop is what makes this a pipeline and not a download: the raw file
      // goes the moment it has been counted, and the disk never fills.
      const back = g.append("g").attr("fill", "none")
        .attr("stroke", ink("accent")).attr("stroke-width", 1.4);
      const dashed = d => back.append("path").attr("d", d)
        .attr("stroke-dasharray", "5 5");
      const head = d => back.append("path").attr("d", d);
      const text = g.append("text").attr("fill", ink("accent-tx"))
        .style("font", `400 ${narrow ? 12 : 13.5}px ${FONT}`);
      const say = (x, anchor, y) => text.attr("text-anchor", anchor)
        .call(t => loop.forEach((line, i) => t.append("tspan")
          .attr("x", x).attr("y", y).attr("dy", `${i * 1.3}em`).text(line)));

      if (narrow) {
        const x = bw, far = bw + gutter - 10;
        const from = top(2) + bh + 18, to = top(1) + 16;
        dashed(`M${x},${from} H${far} V${to} H${x + 4}`);
        head(`M${x + 10},${to - 5} L${x + 4},${to} L${x + 10},${to + 5}`);
        say(0, "start", top(2) + bh + 26);
      } else {
        const x1 = 2 * step + bw / 2, x2 = step + bw / 2;
        const y = bh + (h - bh) * 0.42;
        dashed(`M${x1},${bh + 6} V${y} H${x2} V${bh + 12}`);
        head(`M${x2 - 5},${bh + 18} L${x2},${bh + 12} L${x2 + 5},${bh + 18}`);
        say((x1 + x2) / 2, "middle", y + 22);
      }
    });

  kit.table(document.getElementById("t-h3"), ["what", "how much"],
    [["archive files downloaded and deleted", n.files],
     ["lines of radio read", n.rows_billion + " billion"],
     ["lines kept after filtering", n.kept_billion + " billion"],
     ["days of sea", n.days],
     ["hexagons the store knows", n.cells],
     ["lines a second, a usual file", n.rate_million + " million"],
     ["database time, whole reload", n.load_hours + " hours"],
     ["wall clock, whole reload", n.reload_hours + " hours"],
     ["counts left on disk", n.store_gb + " GB"]]);
}


picture();
cost();
pipeline();
})();
