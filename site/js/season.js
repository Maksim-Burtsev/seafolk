/* Seafolk — chapter one, "A year under sail". Four charts.
 *
 * Same contract as site/js/index.js: one function per figure, each drawing into
 * the responsive frame from site/js/kit.js, no colour literal anywhere (every
 * hue is a CSS variable read at draw time, so light and dark are one code
 * path), and all the numbers come from this page's own
 * <script type="application/json" id="data"> block, written by
 * scripts/site_data/season.py. Nothing is fetched.
 */
(function () {
"use strict";

const D = JSON.parse(document.getElementById("data").textContent);
const ink = kit.ink;
const MONTH = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/* First day of each month in a COMMON year — the calendar the build maps every
 * date onto, so six years lie over one axis (scripts/site_data/season.py). */
const MONTH_DOY = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335];
const sp = n => Math.round(n).toLocaleString("en-GB").replace(/,/g, " ");
const monthOf = doy => MONTH[d3.bisect(MONTH_DOY, doy) - 1];


/* ======================= S1 — the peak walks earlier ===================== */
function season() {
  const R = D.season.rows;
  const shift = R[0].peak - R.at(-1).peak;

  kit.figure(document.getElementById("c-s1"),
    { ratio: 0.42, ratioNarrow: 0.92,
      margin: { top: 26, right: 62, bottom: 40, left: 52 },
      marginNarrow: { right: 54, left: 44, top: 46 } },
    (g, w, h, narrow) => {
      const x = d3.scaleLinear([d3.min(R, r => r.start) - 12,
                                d3.max(R, r => r.end) + 6], [0, w]);
      const y = d3.scalePoint(R.map(r => r.year), [0, h]).padding(0.62);
      const bar = Math.min(16, y.step() * 0.42);

      kit.axis(g, y, { side: "left", values: R.map(r => r.year) });
      kit.axis(g, x, { side: "bottom", at: h,
                       values: [121, 152, 182, 213, 244],
                       fmt: monthOf });

      // where the busiest week fell in the first year, carried down the rows:
      // the dots walking away from this line IS the chart.
      g.append("line").attr("x1", x(D.season.guide)).attr("x2", x(D.season.guide))
        .attr("y1", -8).attr("y2", h + 4)
        .attr("stroke", ink("ref")).attr("stroke-dasharray", "4 5");

      R.forEach(r => {
        g.append("rect").attr("x", x(r.start)).attr("y", y(r.year) - bar / 2)
          .attr("width", x(r.end) - x(r.start)).attr("height", bar)
          .attr("fill", ink("hairline"));
        // a bar that ends where the ARCHIVE ends, not where the season did,
        // is cut off rather than capped — 2026, whose last loaded day is
        // 26 August, in the middle of its own season.
        [r.cut_start && x(r.start), r.cut_end && x(r.end)]
          .filter(at => at !== false).forEach(at =>
            g.append("line").attr("x1", at).attr("x2", at)
              .attr("y1", y(r.year) - bar).attr("y2", y(r.year) + bar)
              .attr("stroke", ink("label")).attr("stroke-width", 1.4));
      });

      g.append("path").attr("fill", "none").attr("stroke", ink("accent"))
        .attr("stroke-width", 1.4).attr("opacity", 0.8)
        .attr("d", d3.line().x(r => x(r.peak)).y(r => y(r.year))(R));
      g.selectAll(null).data(R).join("circle")
        .attr("cx", r => x(r.peak)).attr("cy", r => y(r.year))
        .attr("r", (r, i) => i === R.length - 1 ? 7 : 5.5)
        .attr("fill", ink("accent"))
        .attr("stroke", ink("surface")).attr("stroke-width", 1.5);

      // the dates in the right margin, a column that marches up the page
      kit.halo(g.selectAll(null).data(R).join("text")
        .attr("x", w + 8).attr("y", r => y(r.year)).attr("dy", "0.34em")
        .attr("fill", (r, i) => i === R.length - 1 ? ink("accent-tx") : ink("label"))
        .style("font", (r, i) => `${i === R.length - 1 ? 500 : 400} ${narrow ? 11 : 12}px "IBM Plex Mono", ui-monospace, monospace`)
        .text(r => r.peak_label.slice(0, r.peak_label.indexOf(" ") + 4)));

      // wide: between the guide line and the last dot, in the empty half of
      // the plot. narrow: the rows are 40 px apart and a note between two of
      // them lands on both, so it goes above the frame instead.
      if (narrow)
        kit.note(g, { x: x(D.season.guide) - 4, y: -32, anchor: "end",
          color: ink("accent-tx"), text: [shift + " days", "earlier by 2026"] });
      else
        kit.note(g, { x: x(R.at(-1).peak), y: y(R.at(-1).year), dx: -12, dy: -22,
          anchor: "end", leader: true, color: ink("accent-tx"),
          text: [shift + " days earlier than 2015"] });

      kit.hover(g, w, h, (px, py) => {
        const r = d3.least(R, r => Math.abs(y(r.year) - py));
        return Math.abs(y(r.year) - py) > y.step() / 2 ? null : {
          x: x(r.peak), y: y(r.year), color: ink("accent"),
          text: `${r.year}\nbusiest week: ${r.peak_label}\n${sp(r.small_boats_peak)} boats out a day\nseason: ${r.start_label} to ${r.end_label}` };
      });
    });

  kit.table(document.getElementById("t-s1"),
    ["year", "season", "days", "busiest week", "boats out that week"],
    R.map(r => [r.year, `${r.start_label} – ${r.end_label}`, r.len,
                r.peak_label, sp(r.small_boats_peak)]));
}


/* ========================== S2 — the summer week ======================== */
function week() {
  const W = D.week;
  const best = d3.greatest(W.days, d => d.small_boats);

  kit.figure(document.getElementById("c-s2"),
    { ratio: 0.42, ratioNarrow: 0.86,
      margin: { top: 30, right: 20, bottom: 38, left: 56 },
      marginNarrow: { left: 48, right: 12 } },
    (g, w, h, narrow) => {
      const x = d3.scaleBand(W.days.map(d => d.short), [0, w]).padding(0.28);
      const y = d3.scaleLinear([0, d3.max(W.days, d => d.small_boats) * 1.14], [h, 0]);

      kit.axis(g, y, { side: "left", ticks: 4, grid: w, fmt: sp,
                       title: "boats out that day" });
      kit.axis(g, x, { side: "bottom", at: h,
                       fmt: d => narrow ? d[0] : d });

      g.selectAll(null).data(W.days).join("rect")
        .attr("x", d => x(d.short)).attr("width", x.bandwidth())
        .attr("y", d => y(d.small_boats)).attr("height", d => h - y(d.small_boats))
        .attr("fill", d => d.ratio >= 1.2 ? ink("accent") : ink("working"));

      // the line the bars are read against: the average Monday to Friday
      g.append("line").attr("x1", 0).attr("x2", w)
        .attr("y1", y(W.weekday)).attr("y2", y(W.weekday))
        .attr("stroke", ink("ink")).attr("stroke-dasharray", "5 4");
      kit.halo(g.append("text").attr("x", 2).attr("y", y(W.weekday) - 8)
        .attr("fill", ink("ink"))
        .style("font", `500 ${narrow ? 11 : 12.5}px Karla, ui-sans-serif, sans-serif`)
        .text(narrow ? "a weekday" : "an ordinary weekday"));

      // at 380 px two four-figure numbers over two neighbouring bars run into
      // each other, so only the taller of the pair keeps its value there.
      (narrow ? [best] : [W.days[5], W.days[6]]).forEach(d => kit.halo(g.append("text")
        .attr("x", x(d.short) + x.bandwidth() / 2).attr("y", y(d.small_boats) - 9)
        .attr("text-anchor", "middle").attr("fill", ink("accent-tx"))
        .style("font", `500 ${narrow ? 11 : 13}px "IBM Plex Mono", ui-monospace, monospace`)
        .text(sp(d.small_boats))));

      // the same number as the headline — the build computes it once. Wide it
      // sits over the weekend bars; narrow it goes to the top right, where the
      // y-axis title is not.
      kit.note(g, narrow
        ? { x: w, y: -12, anchor: "end", color: ink("accent-tx"),
            text: ["+" + W.more + " % on the weekend"] }
        : { x: x(best.short) + x.bandwidth() / 2, y: y(best.small_boats) - 34,
            anchor: "middle", color: ink("accent-tx"),
            text: ["the weekend runs " + W.more + " % above a weekday"] });

      kit.hover(g, w, h, px => {
        const i = Math.max(0, Math.min(6, Math.floor(px / x.step())));
        const d = W.days[i];
        return { x: x(d.short) + x.bandwidth() / 2, y: y(d.small_boats),
                 color: ink("accent"),
                 text: `${d.name}\n${sp(d.small_boats)} boats out\n${d.ratio.toFixed(2)} × a weekday` };
      });
    });

  kit.table(document.getElementById("t-s2"),
    ["day", "boats out, average", "against a weekday", "days counted"],
    W.days.map(d => [d.name, sp(d.small_boats), d.ratio.toFixed(2) + " ×", d.days]));
}


/* ===================== S3 — a hundred days of a radio ==================== */
const SHADE = { stayed: "accent", short: "ref", mid: "working", long: "ink" };

function hundred() {
  const G = D.hundred.groups;
  // a hundred dots in reading order, each carrying the group it belongs to
  const dots = G.flatMap((grp, gi) =>
    d3.range(grp.share).map(() => ({ key: grp.key, gi })));

  kit.figure(document.getElementById("c-s3"),
    { ratio: 0.46, ratioNarrow: 1.34,
      margin: { top: 16, right: 16, bottom: 12, left: 16 },
      marginNarrow: { top: 10, bottom: 8 } },
    (g, w, h, narrow) => {
      // wide: the grid on the left, the four labels down the right. narrow:
      // the grid on top, the labels under it — a label beside a 34 px grid
      // would have eight characters to itself.
      const side = narrow ? w : Math.min(h, w * 0.52);
      const cell = side / 10, r = cell * 0.3;
      const at = i => [cell * (i % 10) + cell / 2, cell * Math.floor(i / 10) + cell / 2];

      g.selectAll(null).data(dots).join("circle")
        .attr("cx", (d, i) => at(i)[0]).attr("cy", (d, i) => at(i)[1])
        .attr("r", r).attr("fill", d => ink(SHADE[d.key]));

      // where each group starts and ends, so a label can point at its own dots
      let first = 0;
      const spans = G.map(grp => {
        const span = { grp, from: first, to: first + grp.share - 1 };
        first += grp.share;
        return span;
      });

      if (!narrow) {
        const items = spans.map(s => ({
          y: (at(s.from)[1] + at(s.to)[1]) / 2,
          text: `${s.grp.share} — ${s.grp.label}`,
          color: s.grp.key === "stayed" ? ink("accent-tx") : ink("label"),
          weight: s.grp.key === "stayed" ? 600 : 500 }));
        kit.endLabels(g, side + 6, items, 26);
        // a leader from each label to the row its group ends on. It starts at
        // the edge of the grid rather than at the dot, so that it never
        // crosses the dots of the group above it.
        g.selectAll(null).data(spans).join("line")
          .attr("x1", side).attr("y1", s => at(s.to)[1])
          .attr("x2", side + 10).attr("y2", (s, i) => items[i].y)
          .attr("stroke", ink("hairline"));
      } else {
        const rows = g.append("g").attr("transform", `translate(0,${side + 14})`);
        spans.forEach((s, i) => {
          const yy = i * 24 + 10;
          rows.append("circle").attr("cx", r).attr("cy", yy - 4).attr("r", r)
            .attr("fill", ink(SHADE[s.grp.key]));
          rows.append("text").attr("x", 2 * r + 8).attr("y", yy)
            .attr("fill", s.grp.key === "stayed" ? ink("accent-tx") : ink("label"))
            .style("font", `${s.grp.key === "stayed" ? 600 : 500} 13px Karla, ui-sans-serif, sans-serif`)
            .text(`${s.grp.share} — ${s.grp.label}`);
        });
      }
    });

  kit.table(document.getElementById("t-s3"),
    ["out of a hundred days with the radio on", "days"],
    G.map(grp => [grp.label, grp.share]));
}


/* ======================== S4 — the day of the race ====================== */
function race() {
  const R = D.race.rows;

  kit.figure(document.getElementById("c-s4"),
    { ratio: 0.42, ratioNarrow: 0.92,
      margin: { top: 34, right: 58, bottom: 42, left: 52 },
      marginNarrow: { right: 48, left: 44, top: 40 } },
    (g, w, h, narrow) => {
      const x = d3.scaleLinear([0, d3.max(R, r => r.small_boats_race) * 1.06], [0, w]);
      const y = d3.scalePoint(R.map(r => r.year), [0, h]).padding(0.66);

      kit.axis(g, y, { side: "left", values: R.map(r => r.year) });
      kit.axis(g, x, { side: "bottom", at: h, ticks: 4, fmt: sp,
                       title: narrow ? "boats in the harbour"
                                     : "small boats in the harbour area that day" });

      R.forEach((r, i) => {
        g.append("line")
          .attr("x1", x(r.small_boats_usual)).attr("x2", x(r.small_boats_race))
          .attr("y1", y(r.year)).attr("y2", y(r.year))
          .attr("stroke", ink("ref")).attr("stroke-width", 2);
        g.append("circle").attr("cx", x(r.small_boats_usual)).attr("cy", y(r.year))
          .attr("r", 5).attr("fill", ink("surface"))
          .attr("stroke", ink("working")).attr("stroke-width", 2);
        g.append("circle").attr("cx", x(r.small_boats_race)).attr("cy", y(r.year))
          .attr("r", 7).attr("fill", ink("accent"));
        kit.halo(g.append("text").attr("x", x(r.small_boats_race) + 12)
          .attr("y", y(r.year)).attr("dy", "0.34em").attr("fill", ink("accent-tx"))
          .style("font", `500 ${narrow ? 11 : 13}px "IBM Plex Mono", ui-monospace, monospace`)
          .text("×" + r.times.toFixed(1)));
      });

      // the two dots named once instead of a legend, on the row where they are
      // furthest apart: the first one wide, the last one at 380 px, where the
      // 2015 pair is forty pixels from end to end and two labels would overlap.
      const named = narrow ? R.at(-1) : R[0];
      kit.note(g, { x: x(named.small_boats_usual), y: y(named.year) - 16,
        anchor: "middle", color: ink("label"), text: ["a usual day"] });
      kit.note(g, { x: x(named.small_boats_race), y: y(named.year) - 16,
        anchor: "middle", color: ink("accent-tx"), text: ["race day"] });

      kit.hover(g, w, h, (px, py) => {
        const r = d3.least(R, r => Math.abs(y(r.year) - py));
        return Math.abs(y(r.year) - py) > y.step() / 2 ? null : {
          x: x(r.small_boats_race), y: y(r.year), color: ink("accent"),
          text: `${r.date} ${r.year}, a ${r.weekday}\n${sp(r.small_boats_race)} boats on race day\n${sp(r.small_boats_usual)} on a usual ${r.weekday}` };
      });
    });

  kit.table(document.getElementById("t-s4"),
    ["race day", "boats that day", "a usual day", "times"],
    R.map(r => [`${r.date} ${r.year}`, sp(r.small_boats_race),
                sp(r.small_boats_usual), "×" + r.times.toFixed(1)]));
}


season();
week();
hundred();
race();
})();
