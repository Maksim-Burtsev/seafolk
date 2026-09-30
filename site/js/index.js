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


/* ============================= boat glyphs ============================== */
/* The unit charts on this page are crowds of little boats. Each kind is one
 * path standing on a waterline at y = 0, bow to the right, about 24 units long
 * and up to 21 high; a chart scales it to its cell. A sailing boat tied up in
 * harbour has its sails down: a bare mast. */
const GLYPH = {
  sail:    "M-10.5,-3.6H10.5Q8.6,0 6,0H-6Q-8.6,0 -10.5,-3.6Z"
         + "M-1.6,-4.7V-21.5Q-5.4,-12 -9.8,-4.7Z M0,-20Q5.2,-11 8.8,-4.7H0Z",
  moored:  "M-10.5,-3.6H10.5Q8.6,0 6,0H-6Q-8.6,0 -10.5,-3.6Z M-1.5,-3.6V-19H-0.1V-3.6Z",
  fishing: "M-11,-4.5H8.5L11.5,-8.5L9.5,0H-9.5Z M-7,-4.5V-11.5H0V-4.5Z"
         + "M2.5,-4.5V-18H3.7V-4.5Z M3.7,-16.5L10.5,-6H9L3.7,-14Z",
  work:    "M-11,-4H7.5L11.5,-7.5L9.5,0H-9.5Z M-1.5,-4V-12.5H5.5V-4Z M-7.5,-4V-9H-4.5V-4Z",
  ferries: "M-12.5,-4H12.5L10.5,0H-10.5Z M-10,-4V-8H10.5V-4Z M-7,-8V-11.5H7V-8Z M-2,-11.5V-15H1.5V-11.5Z",
  cargo:   "M-12.5,-4H13L11,0H-11Z M-11.5,-4V-12H-8V-4Z M-7,-4V-8.5H-2.3V-4Z"
         + "M-1.8,-4V-9.8H2.9V-4Z M3.4,-4V-8.5H8.1V-4Z",
};
const boat = (g, kind, x, y, s, fill, rot) => g.append("path").attr("d", GLYPH[kind])
  .attr("transform", `translate(${x.toFixed(1)},${y.toFixed(1)})`
        + (rot ? ` rotate(${rot.toFixed(1)})` : "") + ` scale(${s.toFixed(3)})`)
  .attr("fill", fill);
/* Python's round(), half to even, so a count of glyphs agrees with the number
 * the build printed into the prose: 2.5 cargo ships in a hundred is 2 there. */
const round = v => { const f = Math.floor(v); return v - f === 0.5 ? f + (f % 2) : Math.round(v); };
/* The same scatter on every redraw. */
const rng = seed => () => (seed = seed * 16807 % 2147483647) / 2147483647;
const serif = (w, px, it) => `${it ? "italic " : ""}${w} ${px}px "Source Serif 4", Georgia, serif`;
const mono = (px, w) => `${w || 500} ${px}px "IBM Plex Mono", ui-monospace, monospace`;
const text = (g, x, y, s, font, fill, anchor) => g.append("text").attr("x", x).attr("y", y)
  .attr("text-anchor", anchor || "start").attr("fill", fill).style("font", font).text(s);


/* ====================== I2 — the fleet and the control ================== */
/* Two stacks a year, a mark per thousand: small boats pile up, big ships stay
 * the same height. The last mark of a stack is cut to its fraction, from the
 * waterline up, so a stack is exactly as tall as its count. */
function fleet() {
  const F = D.fleet, UNIT = 1000;
  const top = Math.ceil(d3.max(F.small_boats) / UNIT) + 1.4;
  kit.figure(document.getElementById("c-i2"),
    { ratio: 0.95, ratioNarrow: 1.45, margin: { top: 8, right: 6, bottom: 30, left: 6 } },
    (g, w, h, narrow) => {
      const x = d3.scaleBand(F.years.map(String), [0, w]).paddingInner(0.2).paddingOuter(0.04);
      const step = h / top, col = x.bandwidth() / 2;
      const sS = Math.min(step * 0.86 / 21.5, col * 0.95 / 21);
      const sC = Math.min(step * 0.66 / 12, col * 0.95 / 25.5);
      const Y = v => h - v / UNIT * step;
      const clip = (id, y0, y1) => g.append("clipPath").attr("id", id).append("rect")
        .attr("x", -9999).attr("width", 99999).attr("y", y0).attr("height", y1 - y0);
      function stack(kind, cx, v, s, fill, id) {
        const n = v / UNIT, full = Math.floor(n);
        for (let k = 0; k < full; k++) boat(g, kind, cx, h - k * step, s, fill);
        if (n - full > 0.02) {
          clip(id, h - (full + (n - full)) * step, h - full * step);
          boat(g, kind, cx, h - full * step, s, fill).attr("clip-path", `url(#${id})`);
        }
      }

      F.years.forEach((yr, i) => {
        const x0 = x(String(yr));
        stack("sail", x0 + col / 2, F.small_boats[i], sS, ink("accent"), `i2-s${i}`);
        stack("cargo", x0 + col * 1.5, F.big_ships[i], sC, ink("working"), `i2-c${i}`);
        text(g, x0 + col, h + 20, yr, mono(12), ink("label"), "middle");
      });
      g.append("line").attr("x1", 0).attr("x2", w).attr("y1", h + 0.5).attr("y2", h + 0.5)
        .attr("stroke", ink("ink")).attr("stroke-width", 1.2);

      [0, F.years.length - 1].forEach(i => kit.halo(text(g, x(String(F.years[i])) + col / 2,
        Y(F.small_boats[i]) - step * 1.05, sp(F.small_boats[i]), mono(narrow ? 11 : 12.5, 600),
        ink("accent-tx"), "middle")));

      // the key, in the empty water above the first two years
      const kx = 4, ky = step * 1.4, fs = narrow ? 12.5 : 14, tx = kx + 30 * Math.max(sS, sC);
      boat(g, "sail", kx + 11 * sS, ky, sS, ink("accent"));
      text(g, tx, ky - 3, "small boats", serif(600, fs), ink("accent-tx"));
      boat(g, "cargo", kx + 13 * sC, ky + step * 1.25, sC, ink("working"));
      text(g, tx, ky + step * 1.25 - 3, "big ships", serif(600, fs), ink("working"));
      text(g, kx, ky + step * 2.35, narrow ? "each mark: a thousand" : "each mark: a thousand heard, March to August",
           serif(400, narrow ? 11.5 : 13, true), ink("label"));

      // the one note: how far the small boats climbed
      const last = F.years.length - 1;
      kit.halo(narrow
        ? text(g, kx, ky + step * 4.2, `${D.n.boats_growth} × as many`, serif(600, 16, true), ink("accent-tx"))
        : text(g, x(String(F.years[last])) - col * 0.2, Y(F.small_boats[last]) - step * 0.35,
               `${D.n.boats_growth} × as many`, serif(600, 19, true), ink("accent-tx"), "end"));

      kit.hover(g, w, h, px => {
        const i = Math.floor(px / x.step());
        return F.years[i] === undefined ? null : {
          x: x(String(F.years[i])) + col / 2, y: Y(F.small_boats[i]), color: ink("accent"),
          text: `${F.years[i]}\n${sp(F.small_boats[i])} small boats\n${sp(F.big_ships[i])} big ships` };
      });
    });

  kit.table(document.getElementById("t-i2"), ["year", "small boats", "big ships"],
    F.years.map((yr, i) => [yr, sp(F.small_boats[i]), sp(F.big_ships[i])]));
}


/* ============================= I3 — the flags =========================== */
/* A harbour of a hundred small boats, shared out the way the flags were in
 * the last year: one pontoon per country off one quay, so the German pontoon
 * is simply the longest. A dotted mark on each pontoon is where it ended in
 * the first year. The flags' own colours are the only literals on this page:
 * a flag is not a palette choice. */
const FLAG = { red: "#bf2b2d", white: "#fbf7ec", gold: "#e2ab2a", black: "#23211d",
               swe: "#2a64a0", nor: "#1f3a70", ned: "#2b4f93" };
function flag(g, who, x, y, fw) {
  const fh = fw * 0.66, f = g.append("g").attr("transform", `translate(${x},${y})`);
  const r = (a, b, c, d, col) => f.append("rect").attr("x", a * fw).attr("y", b * fh)
    .attr("width", c * fw).attr("height", d * fh).attr("fill", col);
  g.append("line").attr("x1", x).attr("x2", x).attr("y1", y - 2).attr("y2", y + fw * 1.35)
    .attr("stroke", ink("ink")).attr("stroke-width", 1.3);
  if (who === "German") { r(0, 0, 1, 1 / 3, FLAG.black); r(0, 1 / 3, 1, 1 / 3, FLAG.red); r(0, 2 / 3, 1, 1 / 3, FLAG.gold); }
  else if (who === "Dutch") { r(0, 0, 1, 1 / 3, FLAG.red); r(0, 1 / 3, 1, 1 / 3, FLAG.white); r(0, 2 / 3, 1, 1 / 3, FLAG.ned); }
  else if (who === "Danish") { r(0, 0, 1, 1, FLAG.red); r(12 / 37, 0, 4 / 37, 1, FLAG.white); r(0, 12 / 28, 1, 4 / 28, FLAG.white); }
  else if (who === "Swedish") { r(0, 0, 1, 1, FLAG.swe); r(5 / 16, 0, 2 / 16, 1, FLAG.gold); r(0, 4 / 10, 1, 2 / 10, FLAG.gold); }
  else if (who === "Norwegian") { r(0, 0, 1, 1, FLAG.red); r(6 / 22, 0, 4 / 22, 1, FLAG.white); r(0, 6 / 16, 1, 4 / 16, FLAG.white);
    r(7 / 22, 0, 2 / 22, 1, FLAG.nor); r(0, 7 / 16, 1, 2 / 16, FLAG.nor); }
  else {   // everyone else: a plain burgee
    f.append("path").attr("d", `M0,0L${fw},${fh / 2}L0,${fh}Z`).attr("fill", ink("surface"))
      .attr("stroke", ink("ink")).attr("stroke-width", 0.8);
    return;
  }
  f.append("rect").attr("width", fw).attr("height", fh).attr("fill", "none")
    .attr("stroke", ink("ink")).attr("stroke-width", 0.6);
}

function flags() {
  const F = D.flags, last = F.years.length - 1;
  const rows = F.order.map(k => ({ k, n: round(F.shares[k][last]), was: F.shares[k][0] }));
  const lines = per => d3.sum(rows, r => Math.ceil(r.n / per));
  kit.figure(document.getElementById("c-i3"),
    { ratio: 0.4, ratioNarrow: 1.42, margin: { top: 4, right: 4, bottom: 4, left: 0 } },
    (g, w, h, narrow) => {
      const per = narrow ? 14 : 36;
      const quay = narrow ? 0 : Math.min(176, w * 0.2);
      const endRoom = narrow ? 6 : 64;
      // one boat's berth, and the height of a pontoon's line of boats. On a
      // phone each country gets a heading row and its boats wrap.
      let step = (w - quay - endRoom) / (per + 0.6);
      const need = narrow ? lines(per) * 1.25 + rows.length * 2.1 : rows.length * 2.1;
      if (!narrow) step = Math.min(step, h / need);
      else step = Math.min(step, h / need);
      const s = step * 0.92 / 21;
      const lineH = step * 1.25, headH = narrow ? step * 1.6 : 0;
      const rowH = narrow ? null : h / rows.length;

      // water, and the quay the pontoons run off
      g.append("rect").attr("x", quay).attr("width", w - quay).attr("height", h)
        .attr("fill", ink("shoal")).attr("opacity", 0.55);
      if (!narrow) {
        g.append("rect").attr("width", quay).attr("height", h).attr("fill", ink("land"));
        g.append("line").attr("x1", quay).attr("x2", quay).attr("y1", 0).attr("y2", h)
          .attr("stroke", ink("ink")).attr("stroke-width", 1.4);
      }

      let y = 0;
      rows.forEach((r, i) => {
        const own = i === 0;
        const colour = own ? ink("accent") : ink("sea-ink");
        const fw = narrow ? 20 : Math.min(30, rowH * 0.34);
        const nl = narrow ? Math.ceil(r.n / per) : 1;
        const top = narrow ? y + headH : i * rowH + rowH * 0.2;
        const lh = narrow ? lineH : rowH * 0.62;
        // the country: its flag on the quay (or over its pontoons on a phone)
        const fx = narrow ? 2 : 18, fy = narrow ? y + headH * 0.2 : top + lh * 0.88 - fw * 1.35;
        flag(g, r.k, fx, fy, fw);
        const name = r.k === "everyone else" ? "Everyone else" : r.k;
        const nx = fx + fw + 9, ny = fy + fw * 0.52;
        text(g, nx, ny, name, serif(600, narrow ? 14.5 : 16.5), ink("ink"));
        if (narrow) kit.halo(text(g, w - 2, ny, `${r.n}`, serif(600, 19, true),
                                  own ? ink("accent-tx") : ink("ink"), "end"));

        for (let l = 0; l < nl; l++) {
          const n = Math.min(per, r.n - l * per), py = top + (l + 1) * lh - lh * 0.12;
          const px0 = quay + (narrow ? 0 : 0);
          // the pontoon: a strip of jetty, drawn the way a chart draws one
          g.append("rect").attr("x", px0).attr("y", py).attr("width", (n + 0.6) * step)
            .attr("height", Math.max(3, step * 0.16)).attr("fill", ink("surface"))
            .attr("stroke", ink("ink")).attr("stroke-width", 0.9);
          for (let k = 0; k < n; k++) boat(g, "sail", px0 + step * (k + 0.8), py - 0.5, s, colour);
          if (!narrow) {
            // clear of the dotted mark when that falls just past the pontoon's end
            const end = px0 + (n + 0.6) * step, xt = quay + step * (r.was + 0.3);
            kit.halo(text(g, xt > end - 6 && xt < end + 34 ? xt + 10 : end + 12, py + 2, `${r.n}`,
              serif(600, Math.min(30, rowH * 0.42), true), own ? ink("accent-tx") : ink("ink")));
          }
        }
        // where this pontoon ended in the first year
        if (!narrow) {
          const xt = quay + step * (r.was + 0.3), py = top + lh - lh * 0.12;
          g.append("line").attr("x1", xt).attr("x2", xt).attr("y1", py - lh * 0.95).attr("y2", py + 10)
            .attr("stroke", ink("ink")).attr("stroke-width", 1.2).attr("stroke-dasharray", "2 2");
          kit.halo(text(g, xt, py + 21, F.years[0], mono(10.5), ink("label"), "middle"));
        } else {
          kit.halo(text(g, w - 30, ny, `${F.years[0]}: ${Math.round(r.was)}`, mono(10.5), ink("label"), "end"));
        }
        y = top + nl * lh + step * 0.5;
      });

      // the key, in the open water under the short pontoons
      const kf = narrow ? 11.5 : 13.5;
      if (!narrow) {
        text(g, w - 8, h - 30, `one boat: one in a hundred heard in ${F.years[last]}`,
             serif(400, kf, true), ink("label"), "end");
        text(g, w - 8, h - 12, `dotted mark: where the pontoon ended in ${F.years[0]}`,
             serif(400, kf, true), ink("label"), "end");
      }
    });

  kit.table(document.getElementById("t-i3"), ["year", ...F.order],
    F.years.map((yr, i) => [yr, ...F.order.map(f => F.shares[f][i] + " %")]));
}


/* ========================= I4 — every storm at once ====================== */
/* No selector (round 2). Two fleets in their chart colours: the mean of every
 * storm with a whole window as a thick line with a boat riding each day, and
 * every storm on its own as a hairline behind it. The storm's day is hatched
 * the way a chart hatches an area to keep out of. */
const I4 = [["fishing", "fishing boats", "fishing"], ["cargo", "cargo ships", "cargo"]];

function storms() {
  const S = D.storms;
  const OFF = S.offsets;
  const off = o => (o > 0 ? "+" : o < 0 ? "−" : "") + Math.abs(o);
  const line = d3.line().x(d => x(d[0])).y(d => y(d[1])).curve(d3.curveMonotoneX);
  let x, y;

  kit.figure(document.getElementById("c-i4"),
    { ratio: 0.5, ratioNarrow: 1.05,
      margin: { top: 40, right: 112, bottom: 40, left: 46 },
      marginNarrow: { top: 40, right: 16, left: 38 } },
    (g, w, h, narrow) => {
      x = d3.scaleLinear(d3.extent(OFF), [0, w]);
      y = d3.scaleLinear([0, 100], [h, 0]);
      const dx = x(1) - x(0);

      // the storm's day: hatched, with its name tag hung above the frame
      const pat = g.append("defs").append("pattern").attr("id", "i4-hatch")
        .attr("patternUnits", "userSpaceOnUse").attr("width", 7).attr("height", 7)
        .attr("patternTransform", "rotate(45)");
      pat.append("line").attr("y2", 7).attr("stroke", ink("sea-ink"))
        .attr("stroke-width", 1.2).attr("opacity", 0.4);
      g.append("rect").attr("x", x(0) - dx / 2).attr("width", dx).attr("y", -10)
        .attr("height", h + 10).attr("fill", ink("sea-ink")).attr("opacity", 0.06);
      g.append("rect").attr("x", x(0) - dx / 2).attr("width", dx).attr("y", -10)
        .attr("height", h + 10).attr("fill", "url(#i4-hatch)");
      [x(0) - dx / 2, x(0) + dx / 2].forEach(v => g.append("line").attr("x1", v).attr("x2", v)
        .attr("y1", -10).attr("y2", h).attr("stroke", ink("sea-ink")).attr("stroke-width", 0.8)
        .attr("opacity", 0.6));
      const tag = narrow ? "STORM" : "THE STORM";
      const tw = tag.length * (narrow ? 7.6 : 8.4) + 16;
      g.append("rect").attr("x", x(0) - tw / 2).attr("y", -34).attr("width", tw).attr("height", 22)
        .attr("fill", ink("ink"));
      text(g, x(0), -18.5, tag, mono(narrow ? 11 : 12), ink("surface"), "middle")
        .attr("letter-spacing", "0.18em");

      // dotted graticule and the scale, in chart furniture
      [0, 25, 50, 75, 100].forEach(v => {
        g.append("line").attr("x1", 0).attr("x2", w).attr("y1", y(v)).attr("y2", y(v))
          .attr("stroke", ink(v ? "hairline" : "ink")).attr("stroke-width", v ? 1 : 1.2)
          .attr("stroke-dasharray", v ? "1 4" : null).attr("stroke-linecap", "round");
        text(g, -8, y(v) + 4, v + (narrow ? "" : " %"), mono(11.5, 400), ink("label"), "end");
      });
      text(g, -8 - (narrow ? 0 : 0), -18, narrow ? "% out" : "of 100 heard, how many went out",
           serif(400, 13.5, true), ink("label"), narrow ? "end" : "start")
        .attr("x", narrow ? -2 : -40);
      OFF.forEach(o => text(g, x(o), h + 24, o === 0 ? (narrow ? "storm" : "storm day") : off(o) + (narrow ? "" : " d"),
        mono(narrow ? 11 : 12, o === 0 ? 600 : 400), ink(o === 0 ? "ink" : "label"), "middle"));

      // every storm on its own, faint
      I4.forEach(([key, , tok]) => S[key].each.forEach(pts => g.append("path")
        .attr("d", line(pts)).attr("fill", "none").attr("stroke", ink(tok))
        .attr("stroke-width", 1).attr("opacity", 0.2)));

      // the fishing fleet's water drains away: a wash under its mean
      g.append("path").attr("fill", ink("fishing")).attr("opacity", 0.09)
        .attr("d", d3.area().x(d => x(d[0])).y0(h).y1(d => y(d[1]))
          .curve(d3.curveMonotoneX)(S.fishing.mean));

      const s = narrow ? 0.72 : 1.35;
      const ends = [];
      I4.forEach(([key, label, tok]) => {
        g.append("path").attr("d", line(S[key].mean)).attr("fill", "none")
          .attr("stroke", ink(tok)).attr("stroke-width", narrow ? 2.6 : 3.4)
          .attr("stroke-linecap", "round");
        S[key].mean.forEach(d => boat(g, tok, x(d[0]), y(d[1]) + 2.5 * s, s, ink(tok))
          .attr("stroke", ink("surface")).attr("stroke-width", 2.2 / s)
          .attr("paint-order", "stroke").attr("stroke-linejoin", "round"));
        ends.push({ y: y(S[key].mean.at(-1)[1]) - 4, color: ink(tok), weight: 600,
                    text: label });
      });
      if (!narrow) kit.endLabels(g, w + 14, ends, 18);
      else ends.forEach(e => kit.halo(text(g, w, e.y - 16, e.text, serif(600, 13), e.color, "end")));

      // the one note, under the fishing mean on the storm's own day
      const low = S.fishing.mean.find(d => d[0] === 0)[1];
      const n = D.n.storm_fishing_day;
      kit.note(g, narrow
        ? { x: x(0), y: y(low) - 10, dy: y(64) - y(low) + 10, anchor: "middle", size: 11.5,
            color: ink("fishing"), leader: true,
            text: [`${n} of every 100`, "fishing boats", "went out"] }
        : { x: x(0), y: y(low), dy: 40, anchor: "middle", color: ink("fishing"),
            text: [`on the storm day ${n} of every 100`, "fishing boats went out"] });

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
/* A hundred boats of each fleet that would go out on a usual day. Those that
 * stay in on a storm day are tied up in rows inside a harbour mole, grey (a
 * sailing boat with its sails down); the rest are out at sea in their fleet's
 * colour, bobbing. The harbour's size is the number. */
const FLEET = { sailing: ["sail", "accent", "accent-tx"], fishing: ["fishing", "fishing", "fishing"],
                work: ["work", "working", "working"], ferries: ["ferries", "ferry", "ferry"],
                cargo: ["cargo", "cargo", "cargo"] };

function stayedIn() {
  const rows = D.stayed.map(r => ({ ...r, s: round(r.value) }));
  const pooled = d3.max(rows, r => r.storms);
  kit.figure(document.getElementById("c-i5"),
    { ratio: 0.6, ratioNarrow: 2.05, margin: { top: 22, right: 4, bottom: 4, left: 0 } },
    (g, w, h, narrow) => {
      const R = narrow ? 5 : 4, lab = narrow ? 0 : Math.min(210, w * 0.21);
      const head = narrow ? 34 : 0, gw = w - lab;
      const cols = r => Math.max(1, Math.ceil(r.s / R));
      // the widest row decides the berth, so every row is on one scale
      const span = d3.max(rows, r => cols(r) + 1.25 + Math.ceil((100 - r.s) / R));
      const blockH = h / rows.length;
      const cell = Math.min(gw / (span + 0.3), (blockH - head - 18) / (R * 0.8 + 0.7));
      const ch = cell * 0.8, t = cell * 0.26, s = cell * 0.78 / 24;

      rows.forEach((r, i) => {
        const [kind, tok, tx] = FLEET[r.fleet];
        const gx = lab + t, gy = i * blockH + head + t + 4, GH = R * ch;
        const HW = cols(r) * cell + cell * 0.15;
        const rnd = rng(97 + i * 131);

        // the label: the fleet, and the number that is the harbour's size
        if (narrow) {
          text(g, 0, gy - t - 12, r.label, serif(600, 15), ink("ink"));
          kit.halo(text(g, w - 2, gy - t - 12, `${r.s} stay in`, serif(600, 15, true), ink(tx), "end"));
        } else {
          text(g, 0, gy + 8, r.label, serif(600, 17), ink("ink"));
          text(g, 0, gy + GH * 0.5 + 24, r.s, serif(600, Math.min(44, blockH * 0.4), true), ink(tx));
          text(g, 0, gy + GH * 0.5 + 44, "of 100 stay in", mono(11), ink("label"));
        }
        if (r.storms !== pooled) text(g, narrow ? 0 : 0, narrow ? gy + GH + t + 14 : gy + 26,
          `${r.storms} storms with enough boats out`, serif(400, 12, true), ink("label"));

        const sx = gx + HW + t;
        // the harbour: calm shallow water inside a mole open to the east
        g.append("rect").attr("x", gx).attr("y", gy).attr("width", HW).attr("height", GH)
          .attr("fill", ink("shoal"));
        const L = gx - t, Ri = gx + HW, Ro = Ri + t, T = gy - t, B = gy + GH + t;
        const e1 = gy + GH * 0.3, e2 = gy + GH * 0.7;
        g.append("path").attr("fill", ink("land")).attr("stroke", ink("ink")).attr("stroke-width", 1)
          .attr("d", `M${L},${T}H${Ro}V${e1}H${Ri}V${gy}H${gx}V${gy + GH}H${Ri}V${e2}H${Ro}V${B}H${L}Z`);

        for (let k = 0; k < r.s; k++)
          boat(g, kind === "sail" ? "moored" : kind, gx + cell * (Math.floor(k / R) + 0.58),
               gy + ch * (k % R + 0.9), s, ink("working")).attr("opacity", 0.55);
        for (let k = 0; k < 100 - r.s; k++)
          boat(g, kind, sx + cell * (Math.floor(k / R) + 0.95) + (rnd() - 0.5) * cell * 0.16,
               gy + ch * (k % R + 0.9) + (rnd() - 0.5) * ch * 0.2, s, ink(tok), (rnd() - 0.5) * 10);
      });
      if (!narrow) {
        const gx0 = lab + 3;
        text(g, gx0, -8, "in harbour", serif(400, 13.5, true), ink("label"));
        text(g, lab + (cols(rows[0]) + 1) * cell + 10, -8, "out at sea", serif(400, 13.5, true), ink("label"));
      }
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
  if (!window.SeafolkStorm || !window.chart) {
    host.textContent = "The animation could not be loaded — open "
      + `site/media/storm-${key}.mp4`;
    return;
  }
  // load() also pulls in media/charts/storms.js, the sheets both the player
  // and the triptych under it are drawn on (site/js/storm-player.js)
  SeafolkStorm.load([key], got => {
    if (!got.length) return fail();
    try { SeafolkStorm.mount(host, key); } catch (e) { fail(); }
    SeafolkStorm.triptych(document.getElementById("c-i6-triptych"), key);
  });
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

  /* The picture, to scale. One strip is one day of a big ship's radio sending
   * as fast as it may, drawn like a chart's border: ink and paper by the hour.
   * Above, alone, the one strip a radio can fill: the ceiling. Below, the
   * archive's worst day for one ship, strip after strip of it. */
  kit.figure(document.getElementById("c-i7"),
    { ratio: 0.42, ratioNarrow: 1.3,
      margin: { top: 24, right: 8, bottom: 6, left: 0 }, marginNarrow: { bottom: 40 } },
    (g, w, h, narrow) => {
      const days = I.worst.msgs / I.cap, n = Math.ceil(days), H = 24;
      const lab = narrow ? 0 : Math.min(260, w * 0.27);
      const head = narrow ? 58 : 0, mid = narrow ? 64 : 34;
      const tw = w - lab - (narrow ? 0 : 60);
      const gap = narrow ? 5 : 7;
      const sh = (h - head - mid - gap * (n - 1)) / (n + 1);
      const x0 = lab;
      const strip = (y, frac, colour) => {
        const len = tw * frac;
        g.append("rect").attr("x", x0).attr("y", y).attr("width", len).attr("height", sh)
          .attr("fill", ink("surface")).attr("stroke", colour).attr("stroke-width", 1);
        for (let k = 0; k < H * frac; k += 2) g.append("rect")
          .attr("x", x0 + tw * k / H).attr("y", y)
          .attr("width", Math.min(tw / H, len - tw * k / H)).attr("height", sh).attr("fill", colour);
      };
      const hours = y => [0, 6, 12, 18, 24].forEach(hh => text(g, x0 + tw * hh / H, y,
        (hh < 10 ? "0" : "") + hh + ":00", mono(narrow ? 10 : 11, 400), ink("label"),
        hh === 0 ? "start" : hh === 24 ? "end" : "middle"));

      // the ceiling: one radio, one day, flat out
      hours(head - 7);
      strip(head, 1, ink("ink"));
      // the archive's worst ship-day
      const y1 = head + sh + mid;
      let yl = y1;
      for (let k = 0; k < n; k++) { yl = y1 + k * (sh + gap); strip(yl, Math.min(1, days - k), ink("ferry")); }
      const xr = x0 + tw * (days - (n - 1)) + (narrow ? 10 : 16);

      const one = [`one radio, a message every ${D.n.cap_seconds} seconds`, "for 24 hours: the ceiling"];
      const arch = ["what the archive holds", "for one ship", "on its worst day"];
      const lines = (x, y, arr, font, fill, anchor) => {
        const t = text(g, x, y, "", font, fill, anchor);
        arr.forEach((s, i) => t.append("tspan").attr("x", x).attr("dy", i ? "1.25em" : 0).text(s));
        return kit.halo(t);
      };
      if (narrow) {
        lines(0, 14, one, serif(600, 13.5), ink("ink"));
        text(g, w, head + sh + 18, `${sp(I.cap)} messages`, mono(11.5, 600), ink("ink"), "end");
        lines(0, y1 - 30, ["what the archive holds for one ship", "on its worst day"], serif(600, 13.5), ink("ferry"));
        text(g, 0, yl + sh + 26, sp(I.worst.msgs), serif(600, 24, true), ink("ferry"));
        text(g, w, yl + sh + 24, `× ${D.n.worst_times} the ceiling`, serif(600, 15, true), ink("ferry"), "end");
      } else {
        lines(0, head + sh / 2 - 6, one, serif(600, 14.5), ink("ink"));
        text(g, x0 + tw + 10, head + sh / 2 + 4, sp(I.cap), mono(12, 600), ink("ink"));
        const ym = y1 + (n * (sh + gap)) / 2;
        lines(0, ym - 44, arch, serif(600, 16), ink("ferry"));
        text(g, 0, ym + 36, sp(I.worst.msgs), serif(600, 34, true), ink("ferry"));
        text(g, 0, ym + 58, "messages", mono(11.5), ink("ferry"));
        kit.halo(text(g, xr, yl + sh / 2 + 9, `× ${D.n.worst_times}`, serif(600, 28, true), ink("ferry")));
        kit.halo(text(g, xr + 78, yl + sh / 2 + 6, "days of radio, filed as one", serif(400, 15, true), ink("ferry")));
      }
    });

  /* …and under it, quietly, when it started. */
  const TOP = 1.2;
  kit.figure(document.getElementById("c-i7b"),
    { ratio: 0.17, ratioNarrow: 0.34,
      margin: { top: 22, right: 16, bottom: 30, left: 44 },
      marginNarrow: { left: 40 } },
    (g, w, h, narrow) => {
      const x = d3.scaleUtc([new Date(Date.UTC(2014, 11, 1)), new Date(Date.UTC(2026, 9, 1))], [0, w]);
      const y = d3.scaleLinear([0, TOP], [h, 0]);
      const bw = Math.max(2, w / 150);
      [0, 1].forEach(v => {
        g.append("line").attr("x1", 0).attr("x2", w).attr("y1", y(v)).attr("y2", y(v))
          .attr("stroke", ink(v ? "hairline" : "ink")).attr("stroke-dasharray", v ? "1 4" : null)
          .attr("stroke-linecap", "round");
        text(g, -8, y(v) + 4, v + " %", mono(11.5, 400), ink("label"), "end");
      });
      [2015, 2018, 2021, 2024].forEach(k => text(g, x(new Date(Date.UTC(k, 0, 1))), h + 20, k,
        mono(12, 400), ink("label"), "middle"));
      text(g, -36, -10, "share of ships' days over the ceiling, month by month",
           serif(400, narrow ? 12 : 13.5, true), ink("label"));
      g.selectAll(null).data(months).join("rect")
        .attr("x", d => x(d[0]) - bw / 2).attr("width", bw)
        .attr("y", d => y(Math.min(d[1], TOP)))
        .attr("height", d => h - y(Math.min(d[1], TOP)))
        .attr("fill", d => d[3] >= I.step ? ink("ferry") : ink("working"));
      // the one bar that runs off the top keeps its value rather than a taller
      // axis, which would flatten the wall this strip is about.
      months.filter(d => d[1] > TOP).forEach(d => kit.halo(g.append("text")
        .attr("x", x(d[0]) + 7).attr("y", 8).attr("fill", ink("label"))
        .style("font", mono(11, 400))
        .text(`${d[1].toFixed(1)} %`)));
      kit.halo(g.append("text").attr("x", x(new Date(Date.UTC(2023, 11, 1))) + 6)
        .attr("y", 11).attr("fill", ink("ferry"))
        .style("font", serif(600, 12.5, true))
        .text(narrow ? "from 2024 on" : "every month from December 2023 on"));

      kit.hover(g, w, h, px => {
        const d = d3.least(months, m => Math.abs(x(m[0]) - px));
        return Math.abs(x(d[0]) - px) > 12 ? null : {
          x: x(d[0]), y: y(Math.min(d[1], TOP)), color: ink("ferry"),
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
seaEmpties();          // …and the triptych under it, the same storm as three still sheets
impossible();
})();
