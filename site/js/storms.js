/* Seafolk — the figures on site/storms.html (chapter four), drawn as a chart.
 *
 *   T4   the storm, hour by hour, on the chart (site/js/storm-player.js), and
 *        the same three storms as still sheets (triptychs)
 *   T2   who goes out: a hundred boats per fleet on a usual day and on a storm
 *        day, then every storm as an arrow from one to the other
 *   T2f  where the fishing is: a chart sheet of green stipple
 *   T1   one storm, hour by hour: a barograph, the fleets as pen lines
 *   T3   the anchorages: an anchor on the chart for each, and every storm's
 *        fill beside it
 *
 * T2 is the exact head count — a boat either covered a mile that day or it did
 * not — and every fleet number in the prose comes from it; T1 is the hourly
 * message ratio under it, good for shape and useless as a ruler.
 *
 * No colour literal: every hue is a CSS variable from site/css/site.css, read
 * at draw time. The data is the page's own <script id="data"> block, written by
 * scripts/site_data/storms.py; the map images are scripts/charts_storms.py's.
 */
(function () {
"use strict";

const D = JSON.parse(document.getElementById("data").textContent);
const ink = kit.ink;
const Q = new URLSearchParams(location.search);
const pc = v => Math.round(100 * v) + " %";
const SERIF = '"Source Serif 4", Georgia, serif', MONO = '"IBM Plex Mono", ui-monospace, monospace';

const runs = (pts, gap) => pts.reduce((acc, p, i) => {
  if (i && p[0] - pts[i - 1][0] <= gap) acc[acc.length - 1].push(p);
  else acc.push([p]);
  return acc;
}, []);

function when(start, days) {
  const from = d3.utcParse("%Y-%m-%d")(start);
  const to = d3.utcDay.offset(from, days - 1);
  return days > 1 ? d3.utcFormat("%-d")(from) + "–" + d3.utcFormat("%-d %B %Y")(to)
                  : d3.utcFormat("%-d %B %Y")(from);
}
const year = start => start.slice(0, 4);

// A fishing boat and a cargo ship from the side, one unit long, bow to the right.
const GLYPH = {
  fishing: "M-.55 0 L.6 0 L.38 .3 L-.45 .3 Z M-.3 0 L-.3 -.34 L.02 -.34 L.02 0 Z M.24 0 L.3 -.5 L.36 0 Z",
  cargo: "M-.6 0 L.62 0 L.5 .24 L-.55 .24 Z M-.52 0 L-.52 -.34 L-.3 -.34 L-.3 0 Z M-.24 0 L-.24 -.15 L.46 -.15 L.46 0 Z",
};

function key(el, items) {
  const k = el.appendChild(document.createElement("ul"));
  k.className = "key";
  k.innerHTML = items.map(([cls, colour, text]) =>
    `<li style="color:var(--${colour})"><i class="${cls}"></i><span style="color:var(--label)">${text}</span></li>`).join("");
}


/* ================= T4 — the storm on the chart, and its triptychs ========= */
function sea() {
  const host = document.getElementById("c-t4");
  const clips = D.t4.clips, names = D.t4.names;
  const asked = (Q.get("clip") || Q.get("storm") || "").toLowerCase();
  let current = clips.includes(asked) ? asked : D.t4.default, player = null;
  if (!window.SeafolkStorm || !window.chart) {
    host.textContent = `The animation could not be loaded — open site/media/storm-${current}.mp4`;
    return;
  }
  const keys = d3.select("#k-t4").selectAll("button").data(clips).join("button")
    .attr("type", "button").text(k => names[k])
    .attr("aria-pressed", k => String(k === current))
    .on("click", (e, k) => { current = k; keys.attr("aria-pressed", j => String(j === k)); show(); });
  // only the storm on screen is loaded: each is a megabyte and a half of hours
  function show() {
    const k = current;
    SeafolkStorm.load([k], got => {
      if (k !== current) return;
      if (player) { player.destroy(); player = null; }
      if (!got.length) return SeafolkStorm.unavailable(host, k);
      player = SeafolkStorm.mount(host, k);
    });
  }
  show();
  ["amy", "malik", "pia"].forEach(k => SeafolkStorm.triptych(document.getElementById("c-t4-" + k), k));
}


/* ================== T2 — a hundred boats, then every storm ================ */
function hundred() {
  const P = D.t2.pooled;
  const ROWS = [["fishing", "fishing boats"], ["cargo", "cargo ships"]];
  kit.figure(document.getElementById("c-t2"),
    { ratio: 0.46, ratioNarrow: 1.25, margin: { top: 30, right: 4, bottom: 8, left: 4 } },
    (g, w, h, narrow) => {
      const lab = narrow ? 0 : 104, col = (w - lab) / 2, rowH = h / 2;
      ["a usual day", "a storm day"].forEach((t, j) => g.append("text")
        .attr("x", lab + j * col).attr("y", -12)
        .attr("fill", ink(j ? "ferry" : "label"))
        .style("font", `500 ${narrow ? 10.5 : 11.5}px ${MONO}`).style("letter-spacing", ".16em")
        .text(t.toUpperCase()));
      ROWS.forEach(([k, label], r) => {
        const y0 = r * rowH + (narrow ? 22 : 4);
        g.append("text").attr("x", 0).attr("y", narrow ? y0 - 8 : y0 + 16)
          .attr("fill", ink(k)).style("font", `italic 600 ${narrow ? 14 : 16}px ${SERIF}`)
          .call(t => (narrow ? [label] : label.split(" ")).forEach((s, i) =>
            t.append("tspan").attr("x", 0).attr("dy", i ? "1.15em" : 0).text(s)));
        P[k].forEach((v, j) => {
          const gx = lab + j * col;
          // boats are long and low: a row is two thirds as tall as a boat is long
          const side = Math.min(narrow ? col - 10 : col * 0.58, (rowH - (narrow ? 70 : 28)) / 0.66);
          const c = side / 10, rc = c * 0.66;
          const gg = g.append("g");
          d3.range(100).forEach(n => {
            const on = n < v;
            gg.append("path").attr("d", GLYPH[k])
              .attr("transform", `translate(${gx + c * (n % 10 + .5)},${y0 + rc * (Math.floor(n / 10) + .6)}) scale(${c * .76})`)
              .attr("fill", on ? ink(k) : "none")
              .attr("stroke", on ? "none" : ink("ref")).attr("stroke-width", 0.8)
              .attr("vector-effect", "non-scaling-stroke");
          });
          const nx = narrow ? gx : gx + side + 14, ny = narrow ? y0 + rc * 10 + 34 : y0 + rc * 10 * 0.45;
          g.append("text").attr("x", nx).attr("y", ny).attr("fill", ink(k))
            .style("font", `italic 600 ${narrow ? 30 : 46}px ${SERIF}`).text(v);
          g.append("text").attr("x", nx).attr("y", ny + (narrow ? 16 : 22)).attr("fill", ink("label"))
            .style("font", `italic 400 ${narrow ? 12 : 14}px ${SERIF}`)
            .text(narrow ? "went out" : "of a hundred");
          if (!narrow) g.append("text").attr("x", nx).attr("y", ny + 40).attr("fill", ink("label"))
            .style("font", `italic 400 14px ${SERIF}`).text("went out");
        });
      });
    });
}

const T2_ROWS = [
  ["fishing", "fishing boats", "fishing", 2.6, 0],
  ["cargo",   "cargo ships",   "cargo",   2.0, 0],
  ["sailing", "sailing boats", "accent",  1.5, 8],
];
const T2_TABLE = [["fishing", "fishing"], ["work", "work boats"], ["ferries", "ferries"],
                  ["cargo", "cargo"], ["sailing", "sailing"]];

function arrows() {
  const rows = D.t2.rows;
  kit.figure(document.getElementById("c-t2b"),
    { ratio: 0.66, ratioNarrow: 1.45,
      margin: { top: 52, right: 16, bottom: 44, left: 104 },
      marginNarrow: { left: 86, right: 10, top: 48, bottom: 40 } },
    (g, w, h, narrow) => {
      const x = d3.scaleLinear([0, 100], [0, w]);
      const y = d3.scalePoint(rows.map(r => r.storm), [0, h]).padding(0.5);
      const defs = g.append("defs");
      T2_ROWS.forEach(([k, , tk]) => defs.append("marker").attr("id", "ah-" + k)
        .attr("viewBox", "0 0 10 10").attr("refX", 7).attr("refY", 5)
        .attr("markerWidth", 9).attr("markerHeight", 9).attr("markerUnits", "userSpaceOnUse")
        .attr("orient", "auto-start-reverse")
        .append("path").attr("d", "M0,0 L10,5 L0,10 L3,5 z").attr("fill", ink(tk)));

      // the chart's own graticule: dotted meridians at every quarter
      [0, 25, 50, 75, 100].forEach(v => g.append("line").attr("x1", x(v)).attr("x2", x(v))
        .attr("y1", -8).attr("y2", h).attr("stroke", ink("hairline")).attr("stroke-dasharray", "1 3"));
      kit.axis(g, x, { side: "bottom", at: h, values: [0, 25, 50, 75, 100],
                       fmt: d => d + (narrow ? "" : " %"),
                       title: narrow ? null : "covered a mile that day, out of every hundred heard" });

      rows.forEach(r => {
        g.append("text").attr("x", -12).attr("y", y(r.storm)).attr("dy", "0.34em")
          .attr("text-anchor", "end").attr("fill", ink("sea-ink"))
          .style("font", `italic 500 ${narrow ? 12.5 : 14}px ${SERIF}`)
          .text(r.storm)
          .append("tspan").attr("fill", ink("label")).attr("dx", 5)
          .style("font", `400 ${narrow ? 0 : 10.5}px ${MONO}`).text(narrow ? "" : year(r.start));
        T2_ROWS.forEach(([k, , tk, wd, dy]) => {
          const v = r[k];
          if (!v) return;
          const yy = y(r.storm) + dy, a = x(100 * v[0]), b = x(100 * v[1]);
          g.append("line").attr("x1", a).attr("x2", Math.abs(b - a) > 6 ? b : a + (b >= a ? 6 : -6))
            .attr("y1", yy).attr("y2", yy)
            .attr("stroke", ink(tk)).attr("stroke-width", wd)
            .attr("stroke-dasharray", k === "sailing" ? "3 3" : null)
            .attr("marker-end", `url(#ah-${k})`);
          g.append("circle").attr("cx", a).attr("cy", yy).attr("r", wd + 1.2)
            .attr("fill", ink("surface")).attr("stroke", ink(tk)).attr("stroke-width", 1.4);
        });
      });

      const top = rows[0];
      [["fishing", "fishing boats"], ["cargo", "cargo ships"]].forEach(([k, label]) =>
        kit.halo(g.append("text").attr("x", x(50 * (top[k][0] + top[k][1]))).attr("y", -34)
          .attr("text-anchor", "middle").attr("fill", ink(k))
          .style("font", `italic 600 ${narrow ? 12.5 : 15}px ${SERIF}`)
          .text(narrow ? label.split(" ")[0] : label)));
      kit.note(g, { x: narrow ? w : x(50 * (top.cargo[0] + top.cargo[1])), y: -16,
        anchor: narrow ? "end" : "middle", color: ink("label"),
        text: narrow ? ["four in five moved anyway"] : ["about four in five moved anyway, in every storm"] });
      const sail = rows.find(r => r.sailing);
      if (sail && !narrow) kit.halo(g.append("text")
        .attr("x", x(100 * Math.max(...sail.sailing)) + 12).attr("y", y(sail.storm) + 8)
        .attr("dy", "0.34em").attr("fill", ink("accent-tx"))
        .style("font", `italic 500 12.5px ${SERIF}`).text("sailing boats"));

      kit.hover(g, w, h, (px, py) => {
        let best = null;
        rows.forEach(r => T2_ROWS.forEach(([k, label, tk, , dy]) => {
          const v = r[k];
          if (!v) return;
          [0, 1].forEach(i => {
            const d = (x(100 * v[i]) - px) ** 2 + (y(r.storm) + dy - py) ** 2;
            if (!best || d < best.d) best = { d, x: x(100 * v[i]), y: y(r.storm) + dy, color: ink(tk),
              text: `${r.storm} · ${label}\n${pc(v[i])} covered a mile\n${i ? "on the storm's dates" : "a fortnight earlier"}` };
          });
        }));
        return best && best.d < 900 ? best : null;
      });
    });

  kit.table(document.getElementById("t-t2"),
    ["storm", ...T2_TABLE.flatMap(([, label]) => [`${label}, usual`, `${label}, storm`])],
    rows.map(r => [`${r.storm} · ${year(r.start)}`,
      ...T2_TABLE.flatMap(([k]) => r[k] ? [pc(r[k][0]), pc(r[k][1])] : ["—", "—"])]));
}


/* =================== T2-fishing — where the fishing is ==================== */
function fishingSheet() {
  const el = document.getElementById("c-t2-fishing");
  chart.sheet(el, "storms-fishing", { tag: "2025",
    // no harbours on the west coast: at this size their names run into the degree labels
    names: ["Skagerrak", "Nordsøen", "Kattegat", "Østersøen", "Skagen", "Esbjerg"],
    alt: "Green stipple over the Skagerrak, the North Sea coast of Jutland and the Kattegat; almost none in the Baltic" });
  key(el, [["dots", "fishing", "fishing boats under way; the denser the stipple, the more hours of fishing"]]);
}


/* ===================== T1 — the barograph of one storm ==================== */
/* Four public fleets as pen lines on ruled drum paper. No sailing line: hour by
 * hour that fleet is a ratio over a few dozen boats and swings from 5 % to
 * 418 % inside one storm; T2 counts it by the boat instead. */
const LINES = [
  ["fishing", "fishing boats", "fishing", "fishing", 2.8],
  ["cargo",   "cargo ships",   "cargo",   "cargo",   2.1],
  ["ferries", "ferries",       "ferries", "ferry",   1.4],
  ["work",    "work boats",    "work",    "working", 1.4],
];
const CEILING = 150;

function barograph() {
  const S = D.t1;
  const names = Object.keys(S.panels).sort((a, b) => d3.ascending(S.panels[a].start, S.panels[b].start));
  const asked = (Q.get("storm") || "").toLowerCase();
  let current = names.find(n => n.toLowerCase() === asked) || S.default;
  // the pens draw once the chart is on screen, and again on every new storm;
  // a screenshot (?only=) gets the finished trace
  let seen = Q.has("only");

  const keys = d3.select("#k-t1").selectAll("button").data(names).join("button")
    .attr("type", "button").text(d => d)
    .attr("aria-pressed", d => String(d === current))
    .on("click", (e, d) => {
      current = d;
      keys.attr("aria-pressed", k => String(k === d));
      redraw(); after();
    });

  let redraw = () => {};
  const host = document.getElementById("c-t1");
  kit.figure(host,
    { ratio: 0.56, ratioNarrow: 1.0,
      margin: { top: 30, right: 96, bottom: 46, left: 44 },
      marginNarrow: { right: 58, left: 40 } },
    (g, w, h, narrow) => { redraw = () => draw(g, w, h, narrow); redraw(); });
  new IntersectionObserver(([en], io) => {
    if (!en.isIntersecting || seen) return;
    seen = true; io.disconnect(); pens(host);
  }, { threshold: 0.4 }).observe(host);

  function pens(root) {
    root.querySelectorAll("path.pen").forEach(p => {
      const L = p.getTotalLength();
      p.style.transition = "none";
      p.style.strokeDasharray = L; p.style.strokeDashoffset = L;
      p.getBoundingClientRect();
      p.style.transition = "";
      p.style.strokeDashoffset = 0;
    });
  }

  function draw(g, w, h, narrow) {
    g.selectAll("*").remove();
    const P = S.panels[current];
    const hi = 24 * P.days + 71;
    const x = d3.scaleLinear([-72, hi], [0, w]);
    const y = d3.scaleLinear([0, CEILING], [h, 0]);

    // drum paper: a rule every quarter, a faint one every six hours, a firm one at midnight
    for (let t = -72; t <= hi; t += 6) g.append("line").attr("x1", x(t)).attr("x2", x(t))
      .attr("y1", 0).attr("y2", h).attr("stroke", ink(t % 24 ? "hairline" : "ref"))
      .attr("stroke-width", t % 24 ? 0.6 : 1).attr("stroke-dasharray", t % 24 ? "1 3" : null);
    const pat = g.append("defs").append("pattern").attr("id", "t1-hatch")
      .attr("width", 7).attr("height", 7).attr("patternUnits", "userSpaceOnUse")
      .attr("patternTransform", "rotate(45)");
    pat.append("line").attr("x1", 0).attr("x2", 0).attr("y1", 0).attr("y2", 7)
      .attr("stroke", ink("ferry")).attr("stroke-width", 1.1).attr("opacity", 0.32);
    g.append("rect").attr("x", x(0)).attr("width", x(24 * P.days) - x(0))
      .attr("y", 0).attr("height", h).attr("fill", "url(#t1-hatch)");
    kit.halo(g.append("text").attr("x", x(12 * P.days)).attr("y", 14)
      .attr("text-anchor", "middle").attr("fill", ink("ferry"))
      .style("font", `600 ${narrow ? 11 : 12}px ${MONO}`).style("letter-spacing", ".08em")
      .call(t => (narrow ? [current.toUpperCase(), when(P.start, P.days)]
                         : [`${current.toUpperCase()} · ${when(P.start, P.days)}`])
        .forEach((line, i) => t.append("tspan").attr("x", x(12 * P.days)).attr("dy", i ? "1.3em" : 0).text(line))));

    kit.axis(g, y, { side: "left", values: [0, 50, 100, 150], fmt: d => d + " %", grid: w,
                     title: narrow ? "% of a normal day" : "movement, against a normal day" });
    kit.axis(g, x, { side: "bottom", at: h, values: d3.range(-48, hi, 48),
                     fmt: d => d === 0 ? (narrow ? "storm" : "the storm")
                       : (d > 0 ? "+" : "−") + Math.abs(d / 24) + (narrow ? " d" : Math.abs(d) === 24 ? " day" : " days"),
                     title: narrow ? null : "days from the start of the storm" });
    g.append("line").attr("x1", 0).attr("x2", w).attr("y1", y(100)).attr("y2", y(100))
      .attr("stroke", ink("ink")).attr("stroke-opacity", 0.5).attr("stroke-dasharray", "5 4");

    const line = d3.line().x(d => x(d[0])).y(d => y(Math.min(d[1], CEILING))).curve(d3.curveMonotoneX);
    const ends = [];
    // drawn back to front, so the fishing pen is on top
    LINES.slice().reverse().forEach(([k, label, short, colour, width]) => {
      const pts = P.lines[k];
      if (!pts) return;
      runs(pts, 1).forEach(run => g.append("path").attr("class", "pen").attr("d", line(run))
        .attr("fill", "none").attr("stroke", ink(colour)).attr("stroke-width", width)
        .attr("stroke-linecap", "round").attr("stroke-linejoin", "round")
        .attr("opacity", k === "fishing" || k === "cargo" ? 1 : 0.8));
      const over = pts.filter((d, i) => d[1] > CEILING
        && !(i && pts[i - 1][1] > CEILING && d[0] - pts[i - 1][0] === 1));
      g.selectAll(null).data(over).join("path")
        .attr("d", d3.symbol(d3.symbolTriangle, 26))
        .attr("transform", d => `translate(${x(d[0])},${y(CEILING) - 5})`).attr("fill", ink(colour));
      ends.push({ y: y(Math.min(pts.at(-1)[1], CEILING)), text: narrow ? short : label,
                  color: ink(colour), weight: k === "fishing" || k === "cargo" ? 600 : 500 });
    });
    kit.endLabels(g, w, ends);
    if (seen) pens(g.node());

    const zero = P.lines.fishing.find(d => d[0] === 0);
    if (zero) {
      g.append("circle").attr("cx", x(0)).attr("cy", y(Math.min(zero[1], CEILING))).attr("r", 4.5)
        .attr("fill", ink("surface")).attr("stroke", ink("fishing")).attr("stroke-width", 2);
      // below and to the left, in the empty paper under the run-up
      const zy = y(Math.min(zero[1], CEILING));
      kit.note(g, { x: x(0), y: zy, dx: -14, dy: Math.min(h - 30 - zy, narrow ? 70 : 110), leader: true,
        anchor: "end", color: ink("fishing"),
        text: narrow ? [`${Math.round(zero[1])} % when`, "the date began"]
                     : ["when the storm's own date began, fishing was",
                        `already at ${Math.round(zero[1])} % of a normal day`] });
    }

    const flat = LINES.flatMap(([k, label, , colour]) => (P.lines[k] || []).map(d => [d[0], d[1], label, colour]));
    kit.hover(g, w, h, (px, py) => {
      const d = d3.least(flat, p => (x(p[0]) - px) ** 2 + (y(Math.min(p[1], CEILING)) - py) ** 2);
      return Math.abs(x(d[0]) - px) > 40 ? null : {
        x: x(d[0]), y: y(Math.min(d[1], CEILING)), color: ink(d[3]),
        text: `${d[2]}\n${(d[0] < 0 ? "" : "+") + (d[0] / 24).toFixed(1)} days\n${d[1]} % of a normal day` };
    });
  }

  function after() {
    const P = S.panels[current];
    document.getElementById("n-t1").textContent = P.notes.length ? `${current}: ${P.notes.join("; ")}.` : "";
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


/* ======================= T3 — the anchorages ============================ */
function anchorages() {
  const A = D.t3;
  const by = d3.group(A.rows, r => r.name);
  const mid = n => d3.median(by.get(n) || [], r => r.ratio);

  // the chart: an anchor for each, lettered with its typical storm
  const s = chart.sheet(document.getElementById("c-t3-map"), "storms-anchorages",
    { names: ["Kattegat", "Skagerrak"], scaleNm: 20,
      alt: "A chart from Skagen down to the Sound with the five Danish anchorages marked by anchors" });
  if (s) {
    // the three southern anchors sit within a few miles of each other: one
    // lettered to the west over Zealand, two to the east over Skåne, one of
    // those above its anchor and one below
    const SIDE = { "Isefjord entrance": "left up", "off Landskrona": "up", "Copenhagen roads": "down" };
    s.meta.anchors.forEach(a => {
      const m = mid(a.name);
      const l = s.box.appendChild(document.createElement("span"));
      l.className = "lbl anc " + (SIDE[a.name] || "");
      Object.assign(l.style, s.at(a.lon, a.lat));
      l.innerHTML = `<b>⚓</b><span>${a.name}<em>${m == null ? "" : "×" + m.toFixed(2)} in a storm</em></span>`;
    });
    key(document.getElementById("c-t3-map"), [["wash", "cargo", "big ships lying still, 2025"]]);
  }

  kit.figure(document.getElementById("c-t3"),
    { ratio: 0.82, ratioNarrow: 0.95,
      margin: { top: 34, right: 18, bottom: 46, left: 118 },
      marginNarrow: { left: 118, right: 14, bottom: 42 } },
    (g, w, h, narrow) => {
      const lo = Math.min(0.4, d3.min(A.rows, r => r.ratio) - 0.05);
      const hi = Math.max(1.7, d3.max(A.rows, r => r.ratio) + 0.05);
      const x = d3.scaleLinear([lo, hi], [0, w]);
      const y = d3.scalePoint(A.names, [0, h]).padding(0.6);
      kit.axis(g, x, { side: "bottom", at: h, values: [0.5, 1, 1.5],
                       fmt: d => d === 1 ? "same" : "×" + d,
                       title: narrow ? null : "ships at anchor in the storm, against the days before" });

      g.append("line").attr("x1", x(1)).attr("x2", x(1)).attr("y1", -18).attr("y2", h)
        .attr("stroke", ink("ferry")).attr("stroke-width", 2);
      kit.halo(g.append("text").attr("x", x(1)).attr("y", -24)
        .attr("text-anchor", "middle").attr("fill", ink("ferry"))
        .style("font", `italic 600 14px ${SERIF}`).text("no change"));

      A.names.forEach(name => {
        g.append("line").attr("x1", 0).attr("x2", w).attr("y1", y(name)).attr("y2", y(name))
          .attr("stroke", ink("hairline")).attr("stroke-dasharray", "1 3");
        g.append("text").attr("x", -12).attr("y", y(name)).attr("dy", "0.34em")
          .attr("text-anchor", "end").attr("fill", ink("ink"))
          .style("font", `500 ${narrow ? 10 : 11}px ${MONO}`).style("letter-spacing", ".06em")
          .text(name.toUpperCase());
        (by.get(name) || []).forEach(r => g.append("circle")
          .attr("cx", x(r.ratio)).attr("cy", y(name)).attr("r", 5.5)
          .attr("fill", ink("sea-ink")).attr("opacity", 0.5));
      });

      const worst = d3.least(A.rows, r => r.ratio);
      kit.note(g, { x: x(worst.ratio), y: y(worst.name), dx: 10, dy: -22, leader: true, color: ink("label"),
        text: narrow ? ["the one that moved most", "emptied, not filled"]
                     : ["the one that moved most emptied —", `${worst.name}, under ${worst.storm}`] });

      kit.hover(g, w, h, (px, py) => {
        const d = d3.least(A.rows, r => (x(r.ratio) - px) ** 2 + (y(r.name) - py) ** 2);
        return Math.abs(y(d.name) - py) > 18 ? null : {
          x: x(d.ratio), y: y(d.name), color: ink("sea-ink"),
          text: `${d.name} · ${d.storm}\n${d.pre} ships an hour before\n${d.during} during the storm` };
      });
    });

  kit.table(document.getElementById("t-t3"), ["storm", ...A.names],
    [...d3.group(A.rows, r => r.storm).entries()].map(([storm, rs]) =>
      [storm, ...A.names.map(n => {
        const r = rs.find(v => v.name === n);
        return r ? "×" + r.ratio.toFixed(2) : "—";
      })]));
}


sea();
hundred();
arrows();
fishingSheet();
barograph();
anchorages();
})();
