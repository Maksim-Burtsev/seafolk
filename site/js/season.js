/* Seafolk — chapter one, "A year under sail", drawn as a nautical chart.
 *
 *   S1       each year's season as a coast seen from the sea, a light on its summit
 *   S1 maps  July against January, 2015 against 2025: chart sheets with stipple
 *   S2       the week as a fleet of sails, one sail to a hundred boats
 *   S3       a hundred days of a switched-on radio as a harbour plan
 *   S4       the archipelago on race day and on a usual day, and a row of years
 *
 * Same contract as site/js/index.js: one function per figure, the responsive
 * frame from site/js/kit.js, colours only from site.css variables, numbers only
 * from this page's <script type="application/json" id="data"> block (written by
 * scripts/site_data/season.py) and the sheet manifest site/media/charts/season.js
 * (written by scripts/charts_season.py). Nothing is fetched.
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
const SERIF = '"Source Serif 4", Georgia, serif';
const MONO = '"IBM Plex Mono", ui-monospace, monospace';
const short = label => label.replace(/(\d+) (\w{3})\w*/, "$1 $2");   // "7 August" -> "7 Aug"


/* ================= S1 — the season as a coast, the top as a light ============ */
/* Each year is a coastal view, the kind a chart prints of a landfall: the land
 * rises with the boats out, as a share of that year's own busiest week, and the
 * shore is a quarter of it — so the land is the season (sql/20's start_25 to
 * end_25, asserted by the build) and the light on the summit is the busiest
 * week. The lights walk left down the page; that walk is the chart. */
function season() {
  const R = D.season.rows, P = D.season.profile;
  const shift = R[0].peak - R.at(-1).peak;
  const SHORE = 25;
  // a chart's light: a teardrop flare off the dot, one unit long
  const FLARE = "M0,0 C-0.3,-0.35 -0.26,-0.92 0,-1 C0.26,-0.92 0.3,-0.35 0,0 Z";

  kit.figure(document.getElementById("c-s1"),
    { ratio: 0.7, ratioNarrow: 1.25,
      margin: { top: 30, right: 16, bottom: 58, left: 50 },
      marginNarrow: { left: 40, right: 8, top: 26, bottom: 58 } },
    (g, w, h, narrow) => {
      const x = d3.scaleLinear([91, 304], [0, w]);
      const row = h / R.length, amp = row * 0.8;
      const base = i => (i + 1) * row;                       // the shore line of row i
      const y = (i, pct) => base(i) - (pct - SHORE) / (100 - SHORE) * amp;
      const id = "s1-" + Math.round(w);

      // the graticule: a dotted meridian at every first of the month
      const months = MONTH_DOY.filter(d => d > 91 && d < 304);
      g.selectAll(null).data(months).join("line")
        .attr("x1", x).attr("x2", x).attr("y1", -6).attr("y2", h + 6)
        .attr("stroke", ink("hairline")).attr("stroke-dasharray", "1 4");
      g.selectAll(null).data(months).join("text")
        .attr("x", d => x(d) + 4).attr("y", h + 22).attr("fill", ink("label"))
        .style("font", `400 ${narrow ? 10.5 : 12}px ${MONO}`)
        .text(d => MONTH[MONTH_DOY.indexOf(d)]);

      const defs = g.append("defs");
      // hachures, the way a coastal view shades its land
      defs.append("pattern").attr("id", id + "-hatch").attr("patternUnits", "userSpaceOnUse")
        .attr("width", 4).attr("height", 4)
        .append("path").attr("d", "M0,4 L4,0").attr("stroke", ink("ink"))
        .attr("stroke-width", .5).attr("opacity", .28);

      R.forEach((r, i) => {
        const pts = P[String(r.year)];
        const last = i === R.length - 1;
        const clip = `${id}-c${i}`;
        defs.append("clipPath").attr("id", clip).append("rect")
          .attr("x", -2).attr("width", w + 4).attr("y", base(i) - amp - 20).attr("height", amp + 20);
        const line = d3.line().x(d => x(d[0])).y(d => y(i, d[1])).curve(d3.curveMonotoneX);
        const area = d3.area().x(d => x(d[0])).y0(base(i)).y1(d => y(i, d[1])).curve(d3.curveMonotoneX);

        // under water: the rest of the year, as a dotted depth line
        g.append("path").attr("d", line(pts)).attr("fill", "none")
          .attr("stroke", ink("sea-ink")).attr("stroke-width", .8)
          .attr("stroke-dasharray", "1.5 3").attr("opacity", .7);
        // the sea surface
        g.append("line").attr("x1", 0).attr("x2", w).attr("y1", base(i)).attr("y2", base(i))
          .attr("stroke", ink("sea-ink")).attr("stroke-width", .8).attr("opacity", .55);
        // above water: the season, as land
        const land = g.append("g").attr("clip-path", `url(#${clip})`);
        land.append("path").attr("d", area(pts)).attr("fill", ink("land"));
        land.append("path").attr("d", area(pts)).attr("fill", `url(#${id}-hatch)`);
        land.append("path").attr("d", line(pts)).attr("fill", "none")
          .attr("stroke", ink("ink")).attr("stroke-width", last ? 1.6 : 1.2)
          .attr("stroke-linejoin", "round");

        // where the archive stops, the coast is cut, not ended
        if (r.cut_end) {
          const end = pts.at(-1);
          g.append("line").attr("x1", x(end[0])).attr("x2", x(end[0]))
            .attr("y1", base(i)).attr("y2", y(i, end[1]))
            .attr("stroke", ink("ink")).attr("stroke-width", 1.2);
          kit.halo(g.append("text").attr("x", x(end[0]) + 6).attr("y", base(i) - 5)
            .attr("fill", ink("label"))
            .style("font", `italic 400 ${narrow ? 10.5 : 12.5}px ${SERIF}`)
            .text(narrow ? "archive ends" : "the archive ends here"));
        }

        // the year, lettered at the shore
        g.append("text").attr("x", -10).attr("y", base(i)).attr("dy", "-0.2em")
          .attr("text-anchor", "end").attr("fill", last ? ink("accent-tx") : ink("ink"))
          .style("font", `${last || i === 0 ? 600 : 500} ${narrow ? 11 : 13}px ${MONO}`)
          .text(r.year);
      });

      // where the light stood in the first year, carried down the rows
      const gx = x(D.season.guide);
      g.append("line").attr("x1", gx).attr("x2", gx).attr("y1", y(0, 100) - 4).attr("y2", h + 4)
        .attr("stroke", ink("ink")).attr("stroke-width", 1).attr("stroke-dasharray", "5 4")
        .attr("opacity", .55);

      // the lights: a chart's light symbol, an ink dot with a flare, on each summit
      R.forEach((r, i) => {
        const last = i === R.length - 1;
        const px = x(r.peak), py = y(i, 100);
        const L = Math.min(row * 0.5, narrow ? 18 : 26);
        g.append("path").attr("d", FLARE)
          .attr("transform", `translate(${px},${py - 1}) rotate(28) scale(${L})`)
          .attr("fill", ink("accent")).attr("opacity", last ? 1 : .88)
          .attr("stroke", ink("accent-tx")).attr("stroke-width", .6 / L);
        g.append("circle").attr("cx", px).attr("cy", py).attr("r", last ? 3.6 : 3)
          .attr("fill", ink("ink")).attr("stroke", ink("surface")).attr("stroke-width", 1);
        kit.halo(g.append("text").attr("x", px - 8).attr("y", py + (narrow ? -3 : -6))
          .attr("text-anchor", "end").attr("fill", last ? ink("accent-tx") : ink("label"))
          .style("font", `italic ${last ? 600 : 400} ${narrow ? 11 : 13.5}px ${SERIF}`)
          .text(short(r.peak_label)));
        if (!i && !narrow) kit.halo(g.append("text").attr("x", px + 22).attr("y", py - 6)
          .attr("fill", ink("label")).style("font", `italic 400 13.5px ${SERIF}`)
          .text("the light: that year's busiest week"));
      });

      // the one note: how far the light walked, under the last coast
      const ay = h + 40, a0 = x(R.at(-1).peak), a1 = gx;
      g.append("line").attr("x1", a1).attr("x2", a0 + 6).attr("y1", ay).attr("y2", ay)
        .attr("stroke", ink("accent-tx")).attr("stroke-width", 1.4);
      g.append("path").attr("d", `M${a0},${ay} l8,-4.5 l0,9 z`).attr("fill", ink("accent-tx"));
      g.append("line").attr("x1", a1).attr("x2", a1).attr("y1", ay - 5).attr("y2", ay + 5)
        .attr("stroke", ink("accent-tx")).attr("stroke-width", 1.4);
      kit.halo(g.append("text").attr("x", a1 + 10).attr("y", ay).attr("dy", "0.34em")
        .attr("fill", ink("accent-tx"))
        .style("font", `italic 600 ${narrow ? 13 : 15.5}px ${SERIF}`)
        .text(narrow ? `${shift} days earlier` : `${shift} days earlier than in 2015`));

      kit.hover(g, w, h, (px, py) => {
        const i = Math.max(0, Math.min(R.length - 1, Math.floor(py / row)));
        const r = R[i];
        return { x: x(r.peak), y: y(i, 100), color: ink("accent"),
          text: `${r.year}\nbusiest week: ${r.peak_label}\n${sp(r.small_boats_peak)} boats out a day\nseason: ${r.start_label} to ${r.end_label}` };
      });
    });

  kit.table(document.getElementById("t-s1"),
    ["year", "season", "days", "busiest week", "boats out that week"],
    R.map(r => [r.year, `${r.start_label} – ${r.end_label}`, r.len,
                r.peak_label, sp(r.small_boats_peak)]));
}


/* ======================== S1 maps — the season as water ====================== */
function sheets(id, list, names, key) {
  const el = document.getElementById(id);
  const row = el.appendChild(document.createElement("div"));
  row.className = list.length > 1 ? "sheets" : "";
  const out = list.map(([cid, tag, o]) => chart.sheet(row, cid, Object.assign({ names, tag }, o)));
  const k = el.appendChild(document.createElement("ul"));
  k.className = "key";
  k.innerHTML = key.map(([cls, colour, text]) =>
    `<li style="color:var(--${colour})"><i class="${cls}"></i><span style="color:var(--label)">${text}</span></li>`).join("");
  return out;
}

const INNER_NAMES = ["Kattegat", "Storebælt", "Lillebælt", "Femern Bælt",
  "Aarhus", "Odense", "Samsø", "Ærø",
  // this sheet ends a few miles east of the city, so its label goes left of the dot
  { name: "København", lon: 12.57, lat: 55.68, kind: "place", left: 1 }];

function seasonMaps() {
  const per = (window.SEAFOLK_CHARTS || {})["season-jul"];
  const key = [["dots", "accent", `one dot: ${per ? per.per_dot : "?"} days of small boats out, placed at random inside their patch of sea`]];
  sheets("c-s1-season", [["season-jul", "July 2025", { scaleNm: 20, ticks: false }],
                         ["season-jan", "January 2025", { scaleNm: 20, ticks: false }]], INNER_NAMES, key);
  sheets("c-s1-decade", [["season-2015", "July 2015", { scaleNm: 20, ticks: false }],
                         ["season-jul", "July 2025", { scaleNm: 20, ticks: false }]], INNER_NAMES, key);
}


/* ===================== S2 — the week, as a fleet of sails ==================== */
/* One sail to a hundred boats. Weekdays in ink, the weekend in sail orange, and
 * the dashed line is the average Monday to Friday: every orange sail past it
 * is the weekend's extra. */
const SAIL = "M0.47,0 L0.47,0.86 L0.04,0.86 Z M0.55,0.14 L0.55,0.86 L0.93,0.86 Z";
const HULL = "M0,0.92 L1,0.92 L0.84,1.08 L0.12,1.08 Z";

function week() {
  const W = D.week;
  const weekend = d => d.ratio >= 1.2;
  const SAILS = 25;

  kit.figure(document.getElementById("c-s2"),
    { ratio: 0.5, ratioNarrow: 0.9,
      margin: { top: 34, right: 150, bottom: 12, left: 46 },
      marginNarrow: { top: 46, right: 44, left: 34 } },
    (g, w, h, narrow) => {
      const step = w / SAILS, rowH = h / W.days.length;
      const s = Math.min(step * 0.86, rowH * 0.66);          // one sail's width
      const x = n => n * step;

      // the average weekday, the line the week is read against
      const avg = W.weekday / 100;
      g.append("line").attr("x1", x(avg)).attr("x2", x(avg)).attr("y1", -8).attr("y2", h)
        .attr("stroke", ink("ink")).attr("stroke-dasharray", "5 4");
      kit.halo(g.append("text").attr("x", x(avg)).attr("y", -14).attr("text-anchor", "middle")
        .attr("fill", ink("ink"))
        .style("font", `italic 400 ${narrow ? 11.5 : 13.5}px ${SERIF}`)
        .text(narrow ? "a weekday" : "an ordinary weekday"));

      W.days.forEach((d, i) => {
        const cy = i * rowH + rowH / 2, on = weekend(d);
        const n = Math.round(d.small_boats / 100);
        const colour = on ? ink("accent") : ink("working");
        // a hairline of sea under the row's own sails
        g.append("line").attr("x1", 0).attr("x2", x(n)).attr("y1", cy + s * 0.62).attr("y2", cy + s * 0.62)
          .attr("stroke", ink("hairline"));
        d3.range(n).forEach(k => {
          const t = `translate(${x(k) + (step - s) / 2},${cy - s * 0.52}) scale(${s})`;
          g.append("path").attr("d", SAIL).attr("transform", t).attr("fill", colour);
          g.append("path").attr("d", HULL).attr("transform", t).attr("fill", ink("ink"));
        });
        g.append("text").attr("x", -8).attr("y", cy).attr("dy", "0.34em").attr("text-anchor", "end")
          .attr("fill", on ? ink("accent-tx") : ink("label"))
          .style("font", `${on ? 600 : 500} ${narrow ? 10.5 : 12}px ${MONO}`)
          .text(narrow ? d.short[0] + d.short[1] : d.short.toUpperCase());
        // a number that would sit on the dashed line steps past it
        let tx = x(n) + 6;
        if (tx < x(avg) + 4 && tx + (narrow ? 34 : 46) > x(avg)) tx = x(avg) + 6;
        kit.halo(g.append("text").attr("x", tx).attr("y", cy).attr("dy", "0.34em")
          .attr("fill", on ? ink("accent-tx") : ink("label"))
          .style("font", `${on ? 600 : 400} ${narrow ? 10 : 12}px ${MONO}`)
          .text(sp(d.small_boats)));
      });

      // the one note: a bracket round the weekend and the number the headline says
      const ends = W.days.map((d, i) => [d, i]).filter(([d]) => weekend(d));
      const top = ends[0][1] * rowH + rowH * 0.15, bot = ends.at(-1)[1] * rowH + rowH * 0.85;
      if (!narrow) {
        const bx = x(Math.round(d3.max(W.days, d => d.small_boats) / 100)) + 74;
        g.append("path").attr("d", `M${bx - 6},${top} h6 v${bot - top} h-6`)
          .attr("fill", "none").attr("stroke", ink("accent-tx")).attr("stroke-width", 1.4);
        kit.halo(g.append("text").attr("x", bx + 8).attr("y", (top + bot) / 2).attr("dy", "0.34em")
          .attr("fill", ink("accent-tx"))
          .style("font", `italic 600 26px ${SERIF}`).text(`+${W.more} %`));
      } else {
        kit.halo(g.append("text").attr("x", w + 40).attr("y", -30).attr("text-anchor", "end")
          .attr("fill", ink("accent-tx"))
          .style("font", `italic 600 17px ${SERIF}`).text(`the weekend: +${W.more} %`));
      }

      kit.hover(g, w, h, (px, py) => {
        const i = Math.max(0, Math.min(6, Math.floor(py / rowH)));
        const d = W.days[i];
        return { x: x(Math.round(d.small_boats / 100)), y: i * rowH + rowH / 2, color: ink("accent"),
                 text: `${d.name}\n${sp(d.small_boats)} boats out\n${d.ratio.toFixed(2)} × a weekday` };
      });
    });

  kit.table(document.getElementById("t-s2"),
    ["day", "boats out, average", "against a weekday", "days counted"],
    W.days.map(d => [d.name, sp(d.small_boats), d.ratio.toFixed(2) + " ×", d.days]));
}


/* =================== S3 — a hundred days, as a harbour plan ================== */
/* A marina of a hundred berths: the days the boat never moved are boats still
 * in their berths, in sail orange; the rest are at sea, in three bands tinted the
 * way a chart tints its depths, by how far the boat went that day. The bands
 * are not to scale and the caption says so.
 *
 * Drawn once in harbour coordinates — u runs from the quay out through the
 * mouth to sea, v runs across — and turned by `at`: left to right on a wide
 * screen, bottom to top on a phone. */
const BOAT = "M0,-0.5 C0.3,-0.3 0.3,0.25 0.2,0.5 L-0.2,0.5 C-0.3,0.25 -0.3,-0.3 0,-0.5 Z";

function hundred() {
  const G = D.hundred.groups;
  const byKey = Object.fromEntries(G.map(g => [g.key, g]));
  const sea = G.filter(g => g.key !== "stayed");

  kit.figure(document.getElementById("c-s3"),
    { ratio: 0.46, ratioNarrow: 1.72,
      margin: { top: 64, right: 10, bottom: 10, left: 10 },
      marginNarrow: { top: 10, bottom: 70, left: 6, right: 6 } },
    (g, w, h, narrow) => {
      const U = narrow ? h : w, V = narrow ? w : h;
      const HU = narrow ? U * 0.4 : Math.min(U * 0.34, 380);
      const B = (U - HU) / 3;
      const at = narrow ? (u, v) => [v, U - u] : (u, v) => [u, v];
      const box = (u0, v0, u1, v1) => {
        const [a, b] = at(u0, v0), [c, d] = at(u1, v1);
        return { x: Math.min(a, c), y: Math.min(b, d), width: Math.abs(c - a), height: Math.abs(d - b) };
      };
      const rect = (u0, v0, u1, v1, fill, o) => {
        const r = g.append("rect").attr("fill", fill).attr("opacity", o == null ? 1 : o);
        Object.entries(box(u0, v0, u1, v1)).forEach(([k, v]) => r.attr(k, v));
        return r;
      };
      const seg = (u0, v0, u1, v1, stroke, sw) => {
        const [a, b] = at(u0, v0), [c, d] = at(u1, v1);
        return g.append("line").attr("x1", a).attr("y1", b).attr("x2", c).attr("y2", d)
          .attr("stroke", stroke).attr("stroke-width", sw).attr("stroke-linecap", "square");
      };
      // a hull at (u, v), bow pointing along angle `ang` in harbour coordinates
      // the hull's bow points up the page; (u, v) turns by 90° between the two layouts
      const deg = ang => ang * 180 / Math.PI + (narrow ? 0 : 90);
      const boat = (u, v, ang, len, fill) => {
        const [px, py] = at(u, v);
        g.append("path").attr("d", BOAT)
          .attr("transform", `translate(${px},${py}) rotate(${deg(ang)}) scale(${len * .55},${len})`)
          .attr("fill", fill).attr("stroke", ink("surface")).attr("stroke-width", .08);
      };

      // ---- the sea: three depth bands, the nearest tinted as a shoal
      const tints = [[ink("shoal"), 1], [ink("shoal"), .45], [ink("surface"), 1]];
      sea.forEach((grp, k) => {
        rect(HU + k * B, 0, HU + (k + 1) * B, V, tints[k][0], tints[k][1]);
        if (k) seg(HU + k * B, 0, HU + k * B, V, ink("sea-ink"), .8).attr("stroke-dasharray", "2 4");
      });
      // boats at sea, scattered over their band, heading out
      const rnd = d3.randomLcg(7);
      sea.forEach((grp, k) => {
        // on a phone each band's label sits at its far edge, so the boats keep off it
        const n = grp.share, pad = Math.min(B, V) * 0.1, far = narrow ? 38 : pad;
        const cols = Math.max(1, Math.round(Math.sqrt(n * (B - pad - far) / (V - 2 * pad))));
        const rows = Math.ceil(n / cols);
        const cells = d3.shuffler(rnd)(d3.range(cols * rows)).slice(0, n);
        const cu = (B - pad - far) / cols, cv = (V - 2 * pad) / rows;
        cells.forEach(c => {
          const u = HU + k * B + pad + (c % cols + .2 + rnd() * .6) * cu;
          const v = pad + (Math.floor(c / cols) + .2 + rnd() * .6) * cv;
          const ang = (rnd() - .5) * 0.9;
          const len = narrow ? 13 : 19;
          // a short wake behind her
          seg(u - Math.cos(ang) * len * 1.1, v - Math.sin(ang) * len * 1.1,
              u - Math.cos(ang) * len * .5, v - Math.sin(ang) * len * .5, ink("sea-ink"), 1)
            .attr("opacity", .5);
          boat(u, v, ang, len, ink("ink"));
        });
      });

      // ---- the harbour: land, the basin, a breakwater with its mouth
      const m = V * 0.06, mouth = V * 0.09;
      rect(0, 0, HU, V, ink("land"));
      rect(m * 0.6, m, HU, V - m, ink("shoal"));
      seg(HU, m - 3, HU, V / 2 - mouth, ink("ink"), 5);
      seg(HU, V / 2 + mouth, HU, V - m + 3, ink("ink"), 5);
      seg(m * 0.6, m, HU, m, ink("ink"), 1);
      seg(m * 0.6, V - m, HU, V - m, ink("ink"), 1);
      seg(m * 0.6, m, m * 0.6, V - m, ink("ink"), 2.5);                // the quay

      // five pontoons out from the quay, ten berths on each side of each
      const P = 5, PER = 10, u0 = m * 0.6, u1 = HU - V * 0.12;
      const gap = (V - 2 * m) / P, fin = gap * 0.36, bw = (u1 - u0 - 4) / PER;
      const rndB = d3.randomLcg(3);
      const full = new Set(d3.shuffler(rndB)(d3.range(P * PER * 2)).slice(0, byKey.stayed.share));
      let berth = 0;
      d3.range(P).forEach(p => {
        const v = m + gap * (p + .5);
        seg(u0, v, u1, v, ink("ink"), 2);
        [-1, 1].forEach(side => d3.range(PER).forEach(b => {
          const u = u0 + 4 + b * bw;
          seg(u + bw, v, u + bw, v + side * fin, ink("ink"), .8).attr("opacity", .7);
          if (full.has(berth++))
            boat(u + bw / 2, v + side * fin * 0.52, side > 0 ? Math.PI / 2 : -Math.PI / 2,
                 fin * 0.9, ink("accent"));
        }));
      });

      // ---- the lettering: one label to each part of the water
      const big = narrow ? 24 : 34, small = narrow ? 12.5 : 14;
      const label = (px, py, anchor, n, text, accent) => {
        const t = g.append("text").attr("x", px).attr("y", py).attr("text-anchor", anchor)
          .attr("fill", accent ? ink("accent-tx") : ink("ink"));
        t.append("tspan").style("font", `italic 600 ${big}px ${SERIF}`).text(n);
        t.append("tspan").attr("dx", 7).style("font", `italic 400 ${small}px ${SERIF}`)
          .attr("fill", accent ? ink("accent-tx") : ink("label")).text(text);
        return kit.halo(t);
      };
      const name = { short: "under five miles", mid: "five to thirty miles", long: "past thirty miles" };
      if (!narrow) {
        label(0, -18, "start", byKey.stayed.share, "never left the berth", true);
        sea.forEach((grp, k) => label(HU + k * B + 14, -18, "start", grp.share, name[grp.key]));
        g.append("text").attr("x", HU + 14).attr("y", -54).attr("fill", ink("label"))
          .style("font", `500 11px ${MONO}`).style("letter-spacing", ".18em")
          .text("WENT OUT, AND HOW FAR");
      } else {
        sea.forEach((grp, k) => {
          const [, py] = at(HU + (k + 1) * B, 0);
          label(8, py + 26, "start", grp.share, name[grp.key]);
        });
        label(0, h + 36, "start", byKey.stayed.share, "never left the berth", true);
      }
    });

  kit.table(document.getElementById("t-s3"),
    ["out of a hundred days with the radio on", "days"],
    G.map(grp => [grp.label, grp.share]));
}


/* ================ S4 — race day in the archipelago, and the years ============= */
const FUNEN = [
  { name: "Svendborg", lon: 10.607, lat: 55.06, kind: "place" },
  { name: "Faaborg", lon: 10.242, lat: 55.095, kind: "place" },
  { name: "Rudkøbing", lon: 10.71, lat: 54.936, kind: "place" },
  { name: "Marstal", lon: 10.518, lat: 54.853, kind: "place" },
  { name: "Det Sydfynske Øhav", lon: 10.3, lat: 54.975, kind: "water" },
];
const FUNEN_LAND = [["Fyn", 10.42, 55.17], ["Tåsinge", 10.6, 55.005], ["Langeland", 10.83, 54.82],
                    ["Ærø", 10.36, 54.885]];

function race() {
  const M = window.SEAFOLK_CHARTS || {};
  const day = M["season-race"] ? d3.utcFormat("%-d %B %Y")(new Date(M["season-race"].day)) : "";
  const made = sheets("c-s4", [["season-usual", "A usual Friday · Sept 2025", { scaleNm: 5, ticks: false }],
                               ["season-race", "Race day · " + day, { scaleNm: 5, ticks: false }]],
    FUNEN, [["dots", "accent", "one dot: one small boat heard that day in its patch of sea, placed at random inside it"]]);
  made.forEach((s, i) => {
    if (!s) return;
    FUNEN_LAND.forEach(([n, lon, lat]) => {
      const e = s.box.appendChild(document.createElement("span"));
      e.className = "lbl landname";
      e.textContent = n;
      Object.assign(e.style, s.at(lon, lat));
    });
    if (i === 1) s.box.querySelectorAll(".place").forEach(p => {
      if (p.textContent === "Svendborg") p.classList.add("race");
    });
  });

  // the years, set like a tide table: race day against a usual day, every year
  const R = D.race.rows;
  const best = d3.max(R, r => r.times);
  kit.figure(document.getElementById("c-s4-years"),
    { ratio: 0.13, ratioNarrow: 0.36,
      margin: { top: 30, right: 8, bottom: 8, left: 8 },
      marginNarrow: { top: 26, left: 2, right: 2 } },
    (g, w, h, narrow) => {
      const x = d3.scaleBand(R.map(r => r.year), [0, w]).padding(0.08);
      g.append("text").attr("x", 0).attr("y", -12).attr("fill", ink("label"))
        .style("font", `500 ${narrow ? 10 : 11}px ${MONO}`).style("letter-spacing", ".16em")
        .text(narrow ? "SVENDBORG, RACE DAY" : "SVENDBORG HARBOUR AREA · RACE DAY AGAINST A USUAL DAY");
      g.append("line").attr("x1", 0).attr("x2", w).attr("y1", -4).attr("y2", -4)
        .attr("stroke", ink("ink"));
      R.forEach(r => {
        const cx = x(r.year) + x.bandwidth() / 2, top = r.times === best || r.year === R.at(-1).year;
        const accent = r.year === R.at(-1).year;
        g.append("text").attr("x", cx).attr("y", 16).attr("text-anchor", "middle")
          .attr("fill", accent ? ink("accent-tx") : ink("label"))
          .style("font", `${accent ? 600 : 500} ${narrow ? 10.5 : 12}px ${MONO}`).text(r.year);
        g.append("text").attr("x", cx).attr("y", narrow ? 48 : 54).attr("text-anchor", "middle")
          .attr("fill", accent ? ink("accent-tx") : ink("ink"))
          .style("font", `italic ${top ? 600 : 400} ${narrow ? 24 : 34}px ${SERIF}`)
          .text("×" + r.times.toFixed(1));
        if (!narrow) g.append("text").attr("x", cx).attr("y", 78).attr("text-anchor", "middle")
          .attr("fill", ink("label")).style("font", `italic 400 13.5px ${SERIF}`)
          .text(`${sp(r.small_boats_race)} boats against ${sp(r.small_boats_usual)}`);
      });
      d3.range(1, R.length).forEach(k => {
        const xx = x(R[k].year) - x.step() * x.paddingInner() / 2;
        g.append("line").attr("x1", xx).attr("x2", xx).attr("y1", 4).attr("y2", h - 2)
          .attr("stroke", ink("hairline"));
      });
    });

  kit.table(document.getElementById("t-s4"),
    ["race day", "boats that day", "a usual day", "times"],
    R.map(r => [`${r.date} ${r.year}`, sp(r.small_boats_race),
                sp(r.small_boats_usual), "×" + r.times.toFixed(1)]));
}


season();
seasonMaps();
week();
hundred();
race();
})();
