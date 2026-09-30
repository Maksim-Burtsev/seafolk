/* Seafolk — the ferries chapter, drawn as a nautical chart.
 *
 *   F0  the islands' chart: a July of passenger ships in red ink (an image by
 *       scripts/charts_ferries.py), and over it a pen that draws one Tuesday of
 *       island ferries as it happened
 *   F1  one island's year as a tide table: a row per month, a bar per day
 *   F2  every island's July timetable as ten ferries; the red ones still sail
 *       in January
 *   F3  the five worst storms, the same ten ferries: small island lines over
 *       the four big lines
 *   F4  the race: a real crossing of the old ship and of the battery ferry,
 *       started together on a zoomed chart of their route
 *
 * Data: the page's own <script id="data"> (scripts/site_data/ferries.py) and
 * window.SEAFOLK_FERRIES (site/media/charts/ferries-tracks.js). No colour
 * literal: every hue is a CSS variable from site/css/site.css. The two
 * animations autoplay, loop, stop off screen and, with reduced motion, show
 * their finished state.
 */
(function () {
"use strict";

const D = JSON.parse(document.getElementById("data").textContent);
const T = window.SEAFOLK_FERRIES;
const ink = kit.ink;
const MONTH = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"];
const DAY = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MONO = '"IBM Plex Mono", ui-monospace, monospace';
const SERIF = '"Source Serif 4", Georgia, serif';
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const LOCAL = 120;                         // July in Denmark is UTC+2
const fmt = v => (Number.isInteger(v) ? String(v) : v.toFixed(1));
const hhmm = m => `${String(Math.floor(m / 60) % 24).padStart(2, "0")}:${String(Math.floor(m % 60)).padStart(2, "0")}`;

/* A loop that runs only while its element is on screen. `frame(ms)` gets the
 * time since the loop (re)started and returns false when a lap is over. */
function loop(el, frame) {
  let raf = 0, start = null, visible = false;
  const tick = now => {
    if (!visible) { raf = 0; return; }
    if (start === null) start = now;
    if (frame(now - start) === false) start = now;
    raf = requestAnimationFrame(tick);
  };
  new IntersectionObserver(([e]) => {
    visible = e.isIntersecting;
    if (visible && !raf) raf = requestAnimationFrame(tick);
  }).observe(el);
  return { restart: () => { start = null; } };
}

/* A canvas lying exactly over a chart sheet, sized for the screen. */
function overlay(sheet, onSize) {
  const c = sheet.box.insertBefore(document.createElement("canvas"), sheet.box.querySelector("svg"));
  const ctx = c.getContext("2d");
  const o = { c, ctx, W: 0, H: 0 };
  const size = () => {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    o.W = sheet.box.clientWidth; o.H = sheet.box.clientHeight;
    c.width = Math.round(o.W * dpr); c.height = Math.round(o.H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    onSize();
  };
  new ResizeObserver(() => { if (sheet.box.clientWidth !== o.W) size(); }).observe(sheet.box);
  return o;
}

/* A small hull pointing along its course, the hero's ship. */
function hull(ctx, x, y, ang, r, colour) {
  ctx.save(); ctx.translate(x, y); ctx.rotate(ang);
  ctx.beginPath(); ctx.moveTo(r * 1.9, 0); ctx.lineTo(-r, r * .85); ctx.lineTo(-r, -r * .85); ctx.closePath();
  ctx.fillStyle = colour; ctx.strokeStyle = ink("surface"); ctx.lineWidth = 1.2;
  ctx.fill(); ctx.stroke(); ctx.restore();
}

/* Where a track [[minute, x, y], …] is at minute t, or null when it has no
 * fix within ten minutes either side (a radio gap is not a crossing). */
function at(tr, t) {
  if (t < tr[0][0] || t > tr[tr.length - 1][0]) return null;
  let i = 1;
  while (i < tr.length && tr[i][0] < t) i++;
  if (i >= tr.length) return null;
  const a = tr[i - 1], b = tr[i];
  if (b[0] - a[0] > 10) return null;
  const f = (t - a[0]) / Math.max(b[0] - a[0], .001);
  return { x: a[1] + f * (b[1] - a[1]), y: a[2] + f * (b[2] - a[2]), dx: b[1] - a[1], dy: b[2] - a[2], i };
}


/* ================= F0 — the islands, and one Tuesday of ferries ============= */
// Island names, lettered on the chart the way a søkort letters land. `minor`
// ones drop off on a phone. Positions are where the NAME sits, beside the
// island when the island is too small to hold it.
const ISLES = [
  ["Læsø", 11.02, 57.26], ["Anholt", 11.78, 56.73], ["Samsø", 10.6, 55.9],
  ["Fur", 8.96, 56.87], ["Fanø", 8.43, 55.36], ["Ærø", 10.36, 54.855],
  ["Orø", 11.84, 55.8], ["Sejerø", 11.1, 55.94], ["Fejø", 11.37, 55.0],
  ["Egholm", 9.86, 57.12, 1], ["Livø", 9.17, 56.92, 1], ["Venø", 8.55, 56.57, 1],
  ["Tunø", 10.43, 56.0, 1], ["Endelave", 10.31, 55.72, 1], ["Hjarnø", 10.0, 55.86, 1],
  ["Aarø", 9.66, 55.29, 1], ["Barsø", 9.52, 55.16, 1], ["Lyø", 10.1, 55.06, 1],
  ["Strynø", 10.66, 54.87, 1], ["Femø", 11.6, 55.02, 1], ["Askø", 11.56, 54.87, 1],
  ["Agersø", 11.24, 55.25, 1], ["Omø", 11.1, 55.13, 1], ["Nekselø", 11.37, 55.76, 1],
  ["Hirsholmene", 10.8, 57.47, 1],
];

function web() {
  const el = document.getElementById("c-f0");
  const s = chart.sheet(el, "ferries-web", { eager: true, tag: "July 2025", scaleNm: 20,
    names: [{ name: "Kattegat", lon: 11.3, lat: 56.98, kind: "water", big: 1 },
            "Storebælt", { name: "Lillebælt", lon: 9.83, lat: 55.47, kind: "water", rot: -62 },
            { name: "Limfjorden", lon: 9.45, lat: 56.95, kind: "water" },
            { name: "Smålandsfarvandet", lon: 11.5, lat: 55.12, kind: "water" }],
    alt: "A nautical chart of the Danish islands with a month of ferry tracks in red ink" });
  if (!s) return;
  ISLES.forEach(([name, lon, lat, minor]) => {
    const l = s.box.appendChild(document.createElement("span"));
    l.className = "lbl isle" + (minor ? " minor" : "");
    l.textContent = name;
    Object.assign(l.style, s.at(lon, lat));
  });

  const day = new Date(T.day + "T12:00:00Z");
  const cart = el.querySelector(".sheet").appendChild(document.createElement("div"));
  cart.className = "ferry-cart";
  cart.innerHTML = `
    <p class="eyebrow">${DAY[day.getUTCDay()]} ${day.getUTCDate()} ${MONTH[day.getUTCMonth()]} ${day.getUTCFullYear()}</p>
    <div class="n" id="f0-n"></div>
    <div class="caps" id="f0-what">island ferries under way</div>
    <div class="clock"><span>in Denmark</span><b id="f0-clock"></b></div>
    <ul class="key">
      <li style="color:var(--ferry)"><i class="thick"></i><span style="color:var(--label)">that day, drawn as it happened</span></li>
      <li style="color:var(--ferry)"><i></i><span style="color:var(--label)">the island lines, all of July</span></li>
      <li style="color:var(--ferry)"><i class="faint"></i><span style="color:var(--label)">every other passenger ship, all of July</span></li>
    </ul>`;
  // on a phone the cartouche drops below the chart: the sheet must not hold it
  const mq = matchMedia("(max-width: 760px)");
  const place = () => (mq.matches ? el : s.box).appendChild(cart);
  mq.addEventListener("change", place); place();
  const nEl = cart.querySelector("#f0-n"), clockEl = cart.querySelector("#f0-clock");

  const ships = T.ships, DAY_MS = 30000, HOLD_MS = 5000;
  const red = ink("ferry");
  let drawnTo = -1;
  const pen = overlay(s, () => { drawnTo = -1; if (REDUCED) still(); });
  const hulls = overlay(s, () => {});
  const ci = pen.ctx, ct = hulls.ctx;

  function inkUpTo(to) {
    if (to <= drawnTo) return;
    ci.strokeStyle = red; ci.globalAlpha = .9; ci.lineCap = "round"; ci.lineJoin = "round";
    ci.lineWidth = Math.max(1.1, pen.W / 700);
    ci.beginPath();
    for (const tr of ships) {
      for (let i = 1; i < tr.length; i++) {
        const a = tr[i - 1], b = tr[i];
        if (b[0] <= drawnTo) continue;
        if (b[0] > to) break;
        if (b[0] - a[0] > 10) continue;
        ci.moveTo(a[1] * pen.W, a[2] * pen.H); ci.lineTo(b[1] * pen.W, b[2] * pen.H);
      }
    }
    ci.stroke();
    drawnTo = to;
  }
  function drawShips(t) {
    const W = hulls.W, H = hulls.H;
    ct.clearRect(0, 0, W, H);
    let moving = 0;
    for (const tr of ships) {
      const p = at(tr, t);
      if (!p || Math.hypot(p.dx * W, p.dy * H) < W / 1600) continue;
      moving++;
      hull(ct, p.x * W, p.y * H, Math.atan2(p.dy * H, p.dx * W), Math.max(2.6, W / 420), red);
    }
    return moving;
  }
  function still() {
    ci.clearRect(0, 0, pen.W, pen.H); drawnTo = -1; inkUpTo(1440);
    ct.clearRect(0, 0, hulls.W, hulls.H);
    nEl.textContent = ships.length;
    cart.querySelector("#f0-what").textContent = "island ferries sailed that day";
    clockEl.textContent = "the whole day";
  }
  if (REDUCED) { still(); return; }
  loop(s.box, e => {
    if (e > DAY_MS + HOLD_MS) { ci.clearRect(0, 0, pen.W, pen.H); drawnTo = -1; return false; }
    const t = Math.min(1439, 1440 * Math.min(e, DAY_MS) / DAY_MS);
    inkUpTo(t);
    nEl.textContent = drawShips(t);
    clockEl.textContent = hhmm(t + LOCAL);
  });
}


/* ===================== F1 — one island's year as a tide table =============== */
function tide() {
  const F = D.f1, names = Object.keys(F.lines);
  let current = F.default, redraw = () => {};
  const keys = d3.select("#k-f1").selectAll("button").data(names).join("button")
    .attr("type", "button").text(d => d)
    .attr("aria-pressed", d => String(d === current))
    .on("click", (e, d) => {
      current = d;
      keys.attr("aria-pressed", k => String(k === d));
      redraw(); table();
    });

  const el = document.getElementById("c-f1");
  const rowH = n => (n ? 25 : 31);
  kit.figure(el, {
      get ratio() { return (12 * rowH(false) + 58) / Math.max(el.clientWidth, 280); },
      get ratioNarrow() { return (12 * rowH(true) + 70) / Math.max(el.clientWidth, 280); },
      margin: { top: 50, right: 46, bottom: 8, left: 40 },
      marginNarrow: { top: 62, right: 30, left: 30 } },
    (g, w, h, narrow) => { redraw = () => year(g, w, narrow); redraw(); });

  function year(g, w, narrow) {
    g.selectAll("*").remove();
    const L = F.lines[current], rh = rowH(narrow), cw = w / 31;
    const top = d3.max(L.counts) || 1;
    const days = d3.range(12).map(m => {
      const a = d3.utcDay.count(new Date(Date.UTC(F.year, 0, 1)), new Date(Date.UTC(F.year, m, 1)));
      const n = new Date(Date.UTC(F.year, m + 1, 0)).getUTCDate();
      return { a, n };
    });

    // day numbers along the top, like the head of a tide table
    [1, 5, 10, 15, 20, 25, 30].forEach(d => g.append("text")
      .attr("x", (d - .5) * cw).attr("y", -6).attr("text-anchor", "middle")
      .attr("fill", ink("label")).style("font", `400 ${narrow ? 9 : 10.5}px ${MONO}`).text(d));
    g.append("text").attr("x", w + 6).attr("y", -6).attr("fill", ink("label"))
      .style("font", `italic 400 ${narrow ? 10 : 12}px ${SERIF}`).text(narrow ? "/day" : "a day");

    days.forEach(({ a, n }, m) => {
      const base = (m + 1) * rh - 4;
      const row = g.append("g");
      row.append("line").attr("x1", 0).attr("x2", n * cw).attr("y1", base + .5).attr("y2", base + .5)
        .attr("stroke", ink("hairline"));
      row.append("text").attr("x", -8).attr("y", base - 2).attr("text-anchor", "end")
        .attr("fill", ink("ink")).style("font", `500 ${narrow ? 10 : 11.5}px ${MONO}`)
        .style("letter-spacing", ".08em").text(MONTH[m].slice(0, 3).toUpperCase());
      const sailed = [];
      for (let d = 0; d < n; d++) {
        const i = a + d, st = L.state[i], x = d * cw, cx = x + cw / 2;
        if (st === "s") {
          sailed.push(L.counts[i]);
          const bh = Math.max(1.5, (rh - 8) * L.counts[i] / top);
          row.append("rect").attr("x", x + cw * .2).attr("width", Math.max(1.5, cw * .6))
            .attr("y", base - bh).attr("height", bh).attr("fill", ink("ferry"));
        } else if (st === "c") {
          const r = Math.min(cw * .32, 4.5), y = base - r - 2;
          row.append("path").attr("d", `M${cx - r},${y - r}L${cx + r},${y + r}M${cx - r},${y + r}L${cx + r},${y - r}`)
            .attr("stroke", ink("ink")).attr("stroke-width", 1.8).attr("stroke-linecap", "round");
        } else if (st === "u") {
          row.append("rect").attr("x", x + cw * .2).attr("width", Math.max(1.5, cw * .6))
            .attr("y", base - (rh - 8) * .55).attr("height", (rh - 8) * .55).attr("fill", "none")
            .attr("stroke", ink("working")).attr("stroke-width", 1).attr("stroke-dasharray", "1.5 2");
        }
      }
      // the month's typical day, in the margin where a tide table prints its range
      const typ = sailed.length ? Math.round(d3.median(sailed)) : null;
      row.append("text").attr("x", w + 6).attr("y", base - 2)
        .attr("fill", m === 0 || m === 6 ? ink("ferry") : ink("label"))
        .style("font", `${m === 0 || m === 6 ? 600 : 400} ${narrow ? 10 : 11.5}px ${MONO}`)
        .text(typ == null ? "—" : typ);
    });

    // the one note: the longest run the line owed and did not sail, ringed
    if (L.note) {
      const date = new Date(Date.UTC(F.year, 0, 1 + L.note.i));
      const m = date.getUTCMonth(), d = date.getUTCDate() - 1;
      const cx = (d + .5) * cw, cy = (m + 1) * rh - 4 - (rh - 8) / 2;
      g.append("circle").attr("cx", cx).attr("cy", cy).attr("r", Math.max(7, rh * .42))
        .attr("fill", "none").attr("stroke", ink("ferry")).attr("stroke-width", 1.6);
      const t = kit.halo(g.append("text").attr("x", 0).attr("y", narrow ? -40 : -30)
        .attr("fill", ink("ink")).style("font", `italic 400 ${narrow ? 12.5 : 14.5}px ${SERIF}`));
      t.append("tspan").attr("fill", ink("ferry")).attr("font-style", "normal").text("◯ ");
      if (narrow) {
        t.append("tspan").text(L.note.text[0]);
        t.append("tspan").attr("x", 0).attr("dy", "1.2em").text(L.note.text[1]);
      } else t.append("tspan").text(L.note.text.join(" — "));
    }

    kit.hover(g, w, 12 * rh, (px, py) => {
      const m = Math.max(0, Math.min(11, Math.floor(py / rh))), d = Math.floor(px / cw);
      if (d < 0 || d >= days[m].n) return null;
      const i = days[m].a + d, when = new Date(Date.UTC(F.year, 0, 1 + i));
      const what = { s: `${L.counts[i]} crossings`, c: "owed a sailing, stayed in",
                     u: "nothing heard", o: "no sailing due" }[L.state[i]];
      return { x: (d + .5) * cw, y: (m + 1) * rh - 6, color: ink("ferry"),
               text: `${DAY[when.getUTCDay()]} ${when.getUTCDate()} ${MONTH[m]}\n${what}` };
    });
  }

  document.getElementById("key-f1").innerHTML = [
    ['<svg width="14" height="14"><rect x="4" y="2" width="6" height="12" fill="var(--ferry)"/></svg>', "a bar: crossings that day, taller for more"],
    ['<svg width="14" height="14"><path d="M3,3L11,11M3,11L11,3" stroke="var(--ink)" stroke-width="1.8" stroke-linecap="round"/></svg>', "owed a sailing and stayed in"],
    ['<svg width="14" height="14"><rect x="4" y="5" width="6" height="8" fill="none" stroke="var(--working)" stroke-dasharray="1.5 2"/></svg>', "nothing heard: unknown, not zero"],
  ].map(([i, t]) => `<li>${i}<span>${t}</span></li>`).join("");

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
      ["month", "typical crossings a day", "days it did not sail", "days nothing was heard"],
      by.map((m, i) => [MONTH[i], m.c.length ? Math.round(d3.median(m.c)) : "—",
                        m.miss || "—", m.unknown || "—"]));
  }
  table();
}


/* ============ F2 and F3 — a timetable drawn as ten ferries ================= */
// Side views, drawn in a 30 × 15 box standing on y = 15: a small open car
// ferry with a wheelhouse, and a big ship with decks and a funnel. The row
// length is what a reader compares, so both are the same width.
const SMALL = "M1,11L29,11L26.5,15L3.5,15Z M5,11L5,8L21,8L21,11Z M8,8L8,4.5L14,4.5L14,8Z";
const LARGE = "M0,10L30,10L27.5,15L2.5,15Z M3,10L3,6.5L26,6.5L26,10Z M6,6.5L6,3.5L22,3.5L22,6.5Z M10,3.5L10,1L15,1L15,3.5Z M18.5,3.5L19.5,0L22.5,0L22,3.5Z";
let clipN = 0;

/* ten ferries from x, standing on y; `share` in per cent is how many are red.
 * The ghosts are the ones that did not sail. */
function fleet(g, x, y, share, gw, path, count) {
  const s = gw / 34, gh = 15 * s, n = Math.max(0, share) / 10 * (count || 10) / 10;
  for (let k = 0; k < (count || 10); k++) {
    const gx = x + k * gw;
    const tr = `translate(${gx},${y - gh}) scale(${s})`;
    g.append("path").attr("d", path).attr("transform", tr).attr("fill", ink("surface"))
      .attr("stroke", ink("ref")).attr("stroke-width", 1).attr("vector-effect", "non-scaling-stroke");
    const f = Math.min(1, n - k);
    if (f <= 0) continue;
    const p = g.append("path").attr("d", path).attr("transform", tr).attr("fill", ink("ferry"));
    if (f < 1) {
      const id = `ff-clip-${++clipN}`;
      // in the glyph's own units: a clip path is read in the space of the
      // element it clips, transform included
      g.append("clipPath").attr("id", id).append("rect")
        .attr("x", -1).attr("y", -1).attr("width", 1 + f * 30).attr("height", 17);
      p.attr("clip-path", `url(#${id})`);
    }
  }
}

function winter() {
  const R = D.f2.rows.slice().sort((a, b) => b.share - a.share || a.label.localeCompare(b.label));
  const el = document.getElementById("c-f2");
  const rowH = n => (n ? 24 : 27);
  kit.figure(el, {
      get ratio() { return (R.length * rowH(false) + 64) / Math.max(el.clientWidth, 280); },
      get ratioNarrow() { return (R.length * rowH(true) + 60) / Math.max(el.clientWidth, 280); },
      margin: { top: 52, right: 84, bottom: 12, left: 128 },
      marginNarrow: { top: 46, right: 36, left: 88 } },
    (g, w, h, narrow) => {
      const rh = rowH(narrow), gw = Math.min(34, w / 10);
      // the key, drawn with the marks themselves
      const ky = -26;
      [[narrow ? -88 : 0, 100, "still sails in January"], [narrow ? 70 : 190, 0, "July only"]].forEach(([x, share, text]) => {
        const k = g.append("g").attr("transform", `translate(${x},${ky})`);
        fleet(k, 0, 0, share, 22, SMALL, 1);
        k.append("text").attr("x", 28).attr("y", -2).attr("fill", ink("label"))
          .style("font", `italic 400 ${narrow ? 12 : 13.5}px ${SERIF}`).text(text);
      });
      if (!narrow) g.append("text").attr("x", 10 * gw + 8).attr("y", -8).attr("fill", ink("label"))
        .style("font", `italic 400 12px ${SERIF}`).text("July → Jan");

      R.forEach((d, i) => {
        const base = (i + 1) * rh - 5;
        fleet(g, 0, base, d.share, gw, SMALL);
        g.append("text").attr("x", -12).attr("y", base - 2).attr("text-anchor", "end")
          .attr("fill", ink("ink")).style("font", `${d.share === 100 ? 400 : 600} ${narrow ? 12 : 13.5}px ${SERIF}`)
          .text(narrow ? d.label.replace(/^.*\((.*)\)$/, "$1").replace("/", "/\u200b") : d.label);
        g.append("text").attr("x", 10 * gw + 8).attr("y", base - 2)
          .attr("fill", d.share < 100 ? ink("ferry") : ink("label"))
          .style("font", `500 ${narrow ? 10.5 : 12}px ${MONO}`)
          .text(narrow ? `${d.share}%` : `${fmt(d.summer)} → ${fmt(d.winter)}`);
      });

      kit.hover(g, w, R.length * rh, (px, py) => {
        const d = R[Math.max(0, Math.min(R.length - 1, Math.floor(py / rh)))];
        const i = R.indexOf(d);
        return { x: d.share / 10 * gw, y: (i + 1) * rh - 12, color: ink("ferry"),
                 text: `${d.label}\n${fmt(d.summer)} a day in July\n${fmt(d.winter)} a day in January\n${d.share} % kept` };
      });
    });

  kit.table(document.getElementById("t-f2"),
    ["island line", "July weekday", "January weekday", "winter, % of summer"],
    R.map(d => [d.label, fmt(d.summer), fmt(d.winter), d.share + " %"]));
}

function storms() {
  const R = D.f3.rows;
  const el = document.getElementById("c-f3");
  const blockH = n => (n ? 88 : 76);
  const NOTE = "Malik", EXTRA = 22;        // room under Malik's rows for its note
  kit.figure(el, {
      get ratio() { return (R.length * blockH(false) + EXTRA + 30) / Math.max(el.clientWidth, 280); },
      get ratioNarrow() { return (R.length * blockH(true) + EXTRA + 30) / Math.max(el.clientWidth, 280); },
      margin: { top: 16, right: 124, bottom: 14, left: 150 },
      marginNarrow: { top: 16, right: 92, left: 6 } },
    (g, w, h, narrow) => {
      const gw = Math.min(30, w / 10), bh = blockH(narrow);
      const after = R.findIndex(r => r.storm === NOTE);
      R.forEach((d, i) => {
        const y0 = i * bh + (after >= 0 && i > after ? EXTRA : 0);
        const top = y0 + (narrow ? 22 : 0);
        // the storm, under a gale pennant
        const nx = narrow ? 0 : -140, ny = narrow ? y0 + 12 : y0 + 22;
        g.append("path").attr("d", `M${nx},${ny + 4}L${nx},${ny - 13}M${nx},${ny - 13}L${nx + 11},${ny - 9.5}L${nx},${ny - 6}Z`)
          .attr("stroke", ink("ink")).attr("stroke-width", 1.2).attr("fill", ink("ferry"));
        g.append("text").attr("x", nx + 16).attr("y", ny).attr("fill", ink("ink"))
          .style("font", `600 ${narrow ? 14 : 15.5}px ${SERIF}`).text(d.storm);
        const when = new Date(d.day + "T12:00:00Z");
        g.append("text").attr("x", narrow ? nx + 16 + d.storm.length * 8.4 + 10 : nx + 16)
          .attr("y", narrow ? ny : ny + 18).attr("fill", ink("label"))
          .style("font", `italic 400 ${narrow ? 12 : 13}px ${SERIF}`)
          .text(`${when.getUTCDate()} ${MONTH[when.getUTCMonth()]} ${when.getUTCFullYear()}`);
        [["island", SMALL, 26], ["big", LARGE, 54]].forEach(([k, path, dy]) => {
          const base = top + dy;
          fleet(g, 0, base, Math.min(d[k], 100), gw, path);
          g.append("text").attr("x", 10 * gw + 8).attr("y", base - 2)
            .attr("fill", k === "island" ? ink("ferry") : ink("ink"))
            .style("font", `500 ${narrow ? 11 : 12.5}px ${MONO}`).text(`${d[k]} %`);
          if (i === 0) g.append("text").attr("x", 10 * gw + (narrow ? 44 : 58)).attr("y", base - 2)
            .attr("fill", ink("label")).style("font", `italic 400 ${narrow ? 11.5 : 13}px ${SERIF}`)
            .text(k === "island" ? "island lines" : "big lines");
        });
        if (d.storm === NOTE) {
          kit.halo(g.append("text").attr("x", 0).attr("y", top + 54 + 20)
            .attr("fill", ink("label")).style("font", `italic 400 ${narrow ? 12 : 13}px ${SERIF}`)
            .text("the one storm that hit the big lines harder"));
        }
      });
    });

  kit.table(document.getElementById("t-f3"),
    ["storm", "worst day", "island lines", "big lines"],
    R.map(d => [d.storm, d.day, d.island + " %", d.big + " %"]));
}


/* ========================= F4 — the race to Fynshav ======================= */
function race() {
  const el = document.getElementById("c-f4");
  const F = D.f4;
  const s = chart.sheet(el, "ferries-ellen", { eager: false, tag: "Søby – Fynshav", scaleNm: 2,
    names: [{ name: "Søby", lon: 10.255, lat: 54.938, kind: "place" },
            { name: "Fynshav", lon: 9.99, lat: 54.994, kind: "place", left: 1 },
            { name: "Lillebælt", lon: 10.07, lat: 55.06, kind: "water", big: 1 }],
    alt: "A chart of the crossing from Søby on Ærø to Fynshav on Als with two ferries' tracks" });
  if (!s) return;
  [["Als", 9.9, 54.93], ["Ærø", 10.33, 54.9], ["Fyn", 10.19, 55.09, 1]].forEach(([n, lon, lat, minor]) => {
    const l = s.box.appendChild(document.createElement("span"));
    l.className = "lbl isle" + (minor ? " minor" : ""); l.textContent = n; Object.assign(l.style, s.at(lon, lat));
  });
  const strip = el.appendChild(document.createElement("div"));
  strip.className = "clock";
  strip.innerHTML = `<span>both leave Søby together</span><b id="f4-clock"></b>`;
  const clockEl = strip.querySelector("b");

  const runners = T.race.map((r, i) => ({ ...r, colour: ink(i ? "ferry" : "working"), side: i ? -1 : 1 }));
  const end = d3.max(runners, r => r.minutes);
  const RACE_MS = 15000, HOLD_MS = 5000;
  const cv = overlay(s, () => draw(REDUCED ? end : last));
  const ctx = cv.ctx;
  let last = end;

  function draw(t) {
    last = t;
    const W = cv.W, H = cv.H, narrow = W < 560;
    ctx.clearRect(0, 0, W, H);
    for (const r of runners) {
      const tr = r.track, head = at(tr, Math.min(t, r.minutes)) || { x: tr[tr.length - 1][1], y: tr[tr.length - 1][2], i: tr.length, dx: 0, dy: 0 };
      ctx.strokeStyle = r.colour; ctx.lineWidth = narrow ? 2 : 3; ctx.lineCap = "round"; ctx.lineJoin = "round";
      ctx.beginPath(); ctx.moveTo(tr[0][1] * W, tr[0][2] * H);
      for (let i = 1; i < head.i; i++) ctx.lineTo(tr[i][1] * W, tr[i][2] * H);
      ctx.lineTo(head.x * W, head.y * H); ctx.stroke();
      // a mark every ten minutes, ELLEN's to the north of her track and the
      // old ship's to the south, so the two sets never sit on each other
      ctx.font = `500 ${narrow ? 9 : 12}px ${MONO}`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      for (let m = 10; m < r.minutes && m <= t; m += 10) {
        const p = at(tr, m); if (!p) continue;
        const len = Math.hypot(p.dx * W, p.dy * H) || 1;
        const nx = -p.dy * H / len * r.side, ny = p.dx * W / len * r.side;
        const x = p.x * W, y = p.y * H, k = narrow ? 5 : 8;
        ctx.beginPath(); ctx.moveTo(x - nx * k, y - ny * k); ctx.lineTo(x + nx * k, y + ny * k); ctx.stroke();
        if (!narrow) { ctx.fillStyle = r.colour; ctx.fillText(`${m}′`, x + nx * k * 2.6, y + ny * k * 2.6); }
      }
      if (t < r.minutes) {
        const p = at(tr, t);
        if (p) hull(ctx, p.x * W, p.y * H, Math.atan2(p.dy * H, p.dx * W), narrow ? 4 : 6.5, r.colour);
      }
    }
    // at the berth: who, and how long it took, stacked by arrival in the open
    // water south of the end, clear of both tracks and their marks
    const e = runners[0].track[runners[0].track.length - 1], ex = e[1] * W, ey = e[2] * H;
    const lx = ex + (narrow ? 8 : 30), ly = ey + (narrow ? 24 : 70), gap = narrow ? 14 : 32;
    const done = runners.slice().sort((a, b) => a.minutes - b.minutes).filter(r => t >= r.minutes);
    if (done.length) {
      ctx.strokeStyle = ink("ink"); ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(ex + 3, ey + 5); ctx.lineTo(lx - 6, ly - (narrow ? 8 : 14)); ctx.stroke();
    }
    done.forEach((r, k) => {
      const y = ly + k * gap;
      ctx.textAlign = "left"; ctx.textBaseline = "middle"; ctx.lineJoin = "round";
      ctx.font = `italic 600 ${narrow ? 13 : 26}px ${SERIF}`;
      const big = `${r.minutes} min`, bw = ctx.measureText(big).width;
      ctx.lineWidth = 4; ctx.strokeStyle = ink("paper"); ctx.fillStyle = r.colour;
      ctx.strokeText(big, lx, y); ctx.fillText(big, lx, y);
      ctx.font = `${k ? 400 : 600} ${narrow ? 9.5 : 16}px ${SERIF}`;
      const text = narrow ? r.ship : `${r.ship}, ${r.year}`;
      ctx.strokeText(text, lx + bw + 10, y + 1); ctx.fillText(text, lx + bw + 10, y + 1);
    });
    clockEl.textContent = t >= end ? "both across" : `minute ${Math.floor(t)}`;
  }

  if (!REDUCED) loop(s.box, e => {
    if (e > RACE_MS + HOLD_MS) return false;
    draw(Math.min(end, end * e / RACE_MS));
  });

  document.getElementById("y-f4").innerHTML = F.years.map((y, i) =>
    `<div class="${F.vessel[i] === F.vessel[F.vessel.length - 1] ? "new" : ""}"><b>${y}</b><span>${F.vessel[i]}</span><em>${F.minutes[i]} min</em></div>`).join("");
  kit.table(document.getElementById("t-f4"),
    ["year", "ship", "minutes for the crossing"],
    F.years.map((yr, i) => [yr, F.vessel[i], F.minutes[i]]));
}


if (T) web(); else console.error("ferries: SEAFOLK_FERRIES did not load");
tide();
winter();
storms();
if (T) race();
})();
