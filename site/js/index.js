/* Seafolk — the one page (round 4): every figure drawn by hand over print.
 *
 * Numbers come from the page's own data block (scripts/build_site_data.py);
 * nothing here is a typed value. The ink names are site/css/site.css's
 * --pen, --redpen, --graphite, --greenpen, used through site/js/hand.js.
 */
(function () {
"use strict";

const D = JSON.parse(document.getElementById("data").textContent);
const N = D.n;
const sp = v => d3.format(",")(v).replace(/,/g, " ");
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const el = id => document.getElementById(id);

/* A responsive figure: kit.figure redraws on resize; `hand` gets a fixed seed
 * so the redraw is the same drawing. */
function fig(id, opts, draw, seed) {
  if (!el(id)) return;
  kit.figure(el(id), Object.assign({ margin: { top: 10, right: 10, bottom: 10, left: 10 } }, opts),
    (g, w, ht, narrow) => draw(hand(g.node(), seed || 7), g, w, ht, narrow));
}

/* ------------------------------------------------------------- the hero */
hero(el("c-hero"), el("hero-clock"), el("hero-count"));
el("hero-day").textContent = window.SEAFOLK_FERRY_DAY
  ? d3.utcFormat("%A %-d %B %Y")(new Date(SEAFOLK_FERRY_DAY.day)) : "";

/* ------------------------------------------- I1: the season, on graph paper */
fig("c-i1", { ratio: .5, ratioNarrow: .8, margin: { top: 30, right: 54, bottom: 34, left: 46 } }, (h, g, w, ht, narrow) => {
  const S = D.season, years = Object.keys(S);
  const smooth = pts => pts.map((p, i) => {
    const win = pts.slice(Math.max(0, i - 3), i + 4).filter(q => Math.abs(q[0] - p[0]) <= 3);
    return [p[0], d3.mean(win, q => q[1])];
  });
  const top = d3.max(years, y => d3.max(smooth(S[y]), p => p[1])) * 1.08;
  const x = d3.scaleLinear([1, 366], [0, w]), y = d3.scaleLinear([0, top], [ht, 0]);
  h.rule(0, ht, w, ht, { ink: "graphite", w: 1.2 });
  h.rule(0, 0, 0, ht, { ink: "graphite", w: 1.2 });
  d3.range(1000, top, 1000).forEach(v => {
    h.rule(-5, y(v), 4, y(v), { ink: "graphite", w: 1 });
    h.text(-9, y(v) + 6, sp(v), { ink: "graphite", size: narrow ? 14 : 17, anchor: "end", rot: 0 });
  });
  MONTHS.forEach((m, i) => {
    const d = d3.utcDay.count(new Date(Date.UTC(2025, 0, 1)), new Date(Date.UTC(2025, i, 1))) + 1;
    if (narrow && i % 2) return;
    h.text(x(d) + 2, ht + 25, m, { ink: "graphite", size: narrow ? 15 : 18, rot: 0 });
  });
  h.text(4, -12, "boats out that day", { ink: "graphite", size: narrow ? 15 : 18, rot: 0 });
  // winter, pencilled in lightly
  h.shade(x(1), y(top * .98), x(91) - x(1), ht - y(top * .98), { ink: "graphite", edge: false, gap: 9, w: .5, fw: .4, angle: 60 });
  h.shade(x(305), y(top * .98), x(366) - x(305), ht - y(top * .98), { ink: "graphite", edge: false, gap: 9, w: .5, fw: .4, angle: 60 });
  h.text(x(12), y(top * .55), narrow ? "winter:\nalmost\nnobody" : "November to March:\nalmost nobody", { ink: "graphite", size: narrow ? 15 : 19 });
  // the years between, faint; 2015 in pencil; 2026 in pen
  years.filter(yr => yr !== "2015" && yr !== "2026").forEach(yr =>
    h.curve(smooth(S[yr]).filter((p, i) => i % 3 === 0).map(p => [x(p[0]), y(p[1])]),
      { ink: "graphite", w: .9 }).setAttribute("opacity", .38));
  h.curve(smooth(S["2015"]).filter((p, i) => i % 2 === 0).map(p => [x(p[0]), y(p[1])]), { ink: "graphite", w: 1.7 });
  const last = smooth(S["2026"]);
  h.curve(last.filter((p, i) => i % 2 === 0).map(p => [x(p[0]), y(p[1])]), { ink: "pen", w: 2.6 });
  const pk = last.reduce((a, b) => b[1] > a[1] ? b : a), p15 = smooth(S["2015"]).reduce((a, b) => b[1] > a[1] ? b : a);
  h.text(x(pk[0]) + 14, y(pk[1]) + 6, `2026: ${sp(Math.round(pk[1]))} a day`, { ink: "pen", size: narrow ? 17 : 23 });
  h.text(x(p15[0]) + 16, y(p15[1]) - 6, `2015: ${sp(Math.round(p15[1]))}`, { ink: "graphite", size: narrow ? 16 : 20 });
  if (!narrow) h.text(x(250), y(pk[1] * .7), "the years\nbetween", { ink: "graphite", size: 16 }).setAttribute("opacity", .7);
}, 3);

/* -------------------------------- I1-maps, and every chart sheet with notes */
function sheets(id, list, names, key, notes) {
  const box = el(id); if (!box) return;
  const row = box.appendChild(document.createElement("div"));
  row.className = list.length > 1 ? "sheets" : "";
  list.forEach(([cid, tag], i) => chart.sheet(row, cid, { names, tag, ticks: list.length === 1, notes: notes && notes[i] }));
  if (key) {
    const k = box.appendChild(document.createElement("ul"));
    k.className = "key";
    k.innerHTML = key.map(([cls, colour, text]) =>
      `<li style="color:var(--${colour})"><i class="${cls}"></i><span style="color:var(--label)">${text}</span></li>`).join("");
  }
}
const perDot = ((window.SEAFOLK_CHARTS || {})["i1-jul"] || {}).per_dot;
sheets("c-i1-maps", [["i1-jul", "July 2025"], ["i1-jan", "January 2025"]], ["Kattegat", "Øresund", "Storebælt"],
  [["dots", "pen", `one dot: ${perDot} boat-days, placed at random inside its patch of sea`]],
  [[{ text: "the islands south\nof Funen: full", at: [8.0, 55.25], to: [10.2, 55.0], rot: -2 }],
   [{ text: "a handful,\nnear Copenhagen", at: [13.25, 56.35], to: [12.7, 55.75], rot: -2 }]]);

/* --------------------------- I2: a page of the log, one stroke a thousand */
fig("c-i2", { ratio: .78, ratioNarrow: 1.15, margin: { top: 4, right: 8, bottom: 8, left: 0 } }, (h, g, w, ht, narrow) => {
  const F = D.fleet, n = F.years.length, row = ht / (n + 1.3);
  const gap = Math.min(7.5, w / 72), size = narrow ? 15 : 20, sx = w * (narrow ? .62 : .68);
  h.text(0, row * .55, "year", { ink: "graphite", size, rot: 0 });
  h.text(w * .14, row * .55, "small boats", { size, rot: 0 });
  h.text(sx, row * .55, "ships", { ink: "graphite", size, rot: 0 });
  F.years.forEach((yr, i) => {
    const y = row * (i + 1.6);
    h.text(0, y, yr, { ink: "graphite", size: size + 2, rot: 0 });
    const end = h.tally(w * .14, y, Math.round(F.small_boats[i] / 1000), { ink: "pen", gap, bundle: gap * 2.2, h: row * .55 });
    if (!narrow) h.text(end + 8, y - 2, sp(F.small_boats[i]), { size: size - 2 });
    h.tally(sx, y, Math.round(F.big_ships[i] / 1000), { ink: "graphite", gap, bundle: gap * 2.2, h: row * .55 });
  });
  const y0 = row * 1.6 - row * .6, y1 = row * (n + .6);
  const bx = sx - gap * 3;
  h.path(`M ${bx - 10} ${y0} q 12 0 12 ${(y1 - y0) / 2 - 8} q 0 8 9 8 q -9 0 -9 8 q 0 ${(y1 - y0) / 2 - 8} -12 ${(y1 - y0) / 2 - 8}`, { ink: "redpen", w: 1.5 });
  h.text(bx - 22, y1 + row * .55, `×${N.boats_growth}, and the ships? flat.`, { ink: "redpen", size: size + 4, anchor: "end", rot: -2 });
}, 5);

/* ------------------------------------------ I3: flags, one stroke a per cent */
fig("c-i3", { ratio: .56, ratioNarrow: 1.05, margin: { top: 6, right: 8, bottom: 6, left: 0 } }, (h, g, w, ht, narrow) => {
  const F = D.flags, order = F.order, last = F.years.length - 1;
  const row = ht / (order.length + .6), size = narrow ? 15 : 21;
  const fw = narrow ? 26 : 38, fh = fw * .66, tx = narrow ? w * .12 : w * .26;
  const gap = Math.min(6.4, (w - tx) / 62);
  const pencil = (x, y, ww, hh, c, o = {}) => h.shade(x, y, ww, hh, Object.assign({ ink: c, edge: false, gap: 1.8, angle: -50, w: .6, fw: .9, rough: .9 }, o));
  const paper = (x, y, ww, hh) => g.append("rect").attr("x", x).attr("y", y).attr("width", ww).attr("height", hh).attr("fill", "#f8f2e2");
  const FLAG = {
    German: (x, y) => ["#1d1d1d", "#c4291b", "#d9a514"].forEach((c, k) => pencil(x, y + k * fh / 3, fw, fh / 3, c)),
    Danish: (x, y) => { pencil(x, y, fw, fh, "#c4291b"); paper(x + fw * .3, y, fw * .12, fh); paper(x, y + fh * .43, fw, fh * .14); },
    Swedish: (x, y) => { pencil(x, y, fw, fh, "#2d5fa8"); pencil(x + fw * .3, y, fw * .13, fh, "#d9a514", { gap: 1.2 }); pencil(x, y + fh * .42, fw, fh * .16, "#d9a514", { gap: 1.2 }); },
    Norwegian: (x, y) => { pencil(x, y, fw, fh, "#c4291b"); paper(x + fw * .27, y, fw * .2, fh); paper(x, y + fh * .37, fw, fh * .26);
      pencil(x + fw * .32, y, fw * .1, fh, "#24418f", { gap: 1.2 }); pencil(x, y + fh * .44, fw, fh * .12, "#24418f", { gap: 1.2 }); },
    Dutch: (x, y) => { pencil(x, y, fw, fh / 3, "#c4291b"); pencil(x, y + fh * 2 / 3, fw, fh / 3, "#2d5fa8"); },
  };
  order.forEach((f, i) => {
    const y = row * (i + 1), share = F.shares[f], germ = f === "German";
    if (FLAG[f]) { FLAG[f](0, y - fh - 2); h.rule(0, y - fh - 3, 0, y + 6, { ink: "graphite", w: 1 }); }
    if (!narrow) h.text(fw + 12, y - 4, f, { ink: "ink", size, rot: 0 });
    const end = h.tally(tx, y, Math.round(share[last]), { ink: germ ? "redpen" : "pen", gap, bundle: gap * 2.1, h: row * .5 });
    h.text(end + 8, y - 3, `${Math.round(share[last])}` + (narrow ? "" : " %"), { ink: germ ? "redpen" : "pen", size: size - 1 });
    if (!narrow) h.text(w, y - 3, `2015: ${Math.round(share[0])}`, { ink: "graphite", size: size - 4, anchor: "end" });
    if (narrow) h.text(tx, y - row * .62, f, { ink: "ink", size: 13, rot: 0 });
  });
}, 9);

/* ------------------------------------------ the three fleets, each on a sheet */
sheets("c-i3-cargo", [["i3-cargo", "July 2025"]],
  ["Skagerrak", "Kattegat", "Nordsøen", "Østersøen", "Storebælt", "Øresund", "Skagen", "København", "Kiel"],
  [["wash", "graphite", "cargo ships and tankers under way: the more ships, the denser the pencil"]],
  [[{ text: "every ship for the Baltic\nsqueezes through the\nGreat Belt...", at: [8.85, 55.95], to: [10.95, 55.42] },
    { text: "...or the Sound", at: [13.25, 56.25], to: [12.72, 55.7] },
    { text: "everyone turns\nthe corner at Skagen", at: [12.35, 57.55], to: [10.85, 57.85], rot: -3 }]]);
sheets("c-i3-ferries", [["i3-ferries", "July 2025"]],
  ["Kattegat", "Storebælt", "Øresund", "Rødby", "Rønne", "Frederikshavn", "Göteborg", "Samsø", "Læsø", "Ærø"],
  [["", "redpen", "every passenger ship's own track, one line per crossing"]],
  [[{ text: "short threads:\nislands with no other way\nto the mainland", at: [8.75, 56.35], to: [10.42, 55.92] },
    { text: "Rødby – Puttgarden,\nback and forth all day", at: [9.2, 54.25], to: [11.25, 54.58], rot: -2 },
    { text: "Bornholm", at: [14.15, 55.75], to: [14.55, 55.2] }]]);
sheets("c-i3-fishing", [["i3-fishing", "2025"]],
  ["Skagerrak", "Nordsøen", "Kattegat", "Østersøen", "Skagen", "Hirtshals"],
  [["dots", "greenpen", "fishing boats under way; the denser the dots, the more hours of fishing"]],
  [[{ text: "the fishing grounds:\nSkagerrak and the North Sea", at: [12.3, 57.6], to: [9.6, 57.78], ink: "green" },
    { text: "the harbours on the\nwest coast glow", at: [9.15, 55.55], to: [8.2, 56.0], ink: "green" },
    { text: "almost nothing\nin the Baltic", at: [14.2, 55.75], to: [14.0, 54.9], ink: "green" }]]);

/* ------------------------------------------------- P1: four compass roses */
fig("c-p1", { ratio: .36, ratioNarrow: 1.1, margin: { top: 30, right: 10, bottom: 70, left: 10 } }, (h, g, w, ht, narrow) => {
  const C = D.part_pulse.clocks;
  const FL = [["sailing", "sailing boats", "pen"], ["ferries", "ferries", "redpen"],
              ["cargo", "cargo ships", "graphite"], ["fishing", "fishing boats", "greenpen"]];
  const PEAK = d3.max(FL, f => d3.max(C[f[0]])) * 1.05;
  const cols = narrow ? 2 : 4, R = Math.min(w / cols / 2 - 26, (narrow ? ht / 2 - 40 : ht) / 2) * .9;
  const NIGHT = [22, 23, 0, 1, 2, 3, 4];
  FL.forEach(([k, label, ink], i) => {
    const cx = (i % cols + .5) * w / cols, cy = narrow ? (Math.floor(i / cols) + .5) * ht / 2 - 10 : ht / 2;
    h.circle(cx, cy, 2 * R, { ink: "graphite", w: 1, rough: .5 });
    const flat = (100 / 24) / PEAK * R;
    h.circle(cx, cy, 2 * flat, { ink: "graphite", w: .7, rough: .3 }).setAttribute("stroke-dasharray", "2 4");
    [["midnight", 0], ["noon", 180]].forEach(([t, a]) => {
      const r = (a - 90) * Math.PI / 180;
      h.text(cx + Math.cos(r) * (R + 10), cy + Math.sin(r) * (R + 10) + (a ? 14 : -2), t, { ink: "graphite", size: narrow ? 12 : 15, anchor: "middle", rot: 0 });
    });
    C[k].forEach((v, hr) => {
      const r = (hr * 15 - 90) * Math.PI / 180, L = v / PEAK * R;
      h.line([[cx + Math.cos(r) * 3, cy + Math.sin(r) * 3], [cx + Math.cos(r) * L, cy + Math.sin(r) * L]], { ink, w: narrow ? 2 : 2.8, rough: .4 });
    });
    const night = d3.sum(NIGHT, hr => C[k][hr]);
    h.text(cx, cy + R + (narrow ? 40 : 46), label, { ink, size: narrow ? 17 : 22, anchor: "middle", rot: 0 });
    h.text(cx, cy + R + (narrow ? 58 : 68), `${Math.round(night)} % at night`, { ink: "graphite", size: narrow ? 13 : 16, anchor: "middle", rot: 0 });
  });
}, 13);

/* -------------------------------------------- F4: ELLEN against SKJOLDNAES */
(function race() {
  const T = window.SEAFOLK_FERRIES, box = el("c-f4");
  if (!T || !box) return;
  const s = chart.sheet(box, "ferries-ellen", { tag: "Søby – Fynshav", scaleNm: 2,
    names: [{ name: "Søby", lon: 10.255, lat: 54.938, kind: "place" },
            { name: "Fynshav", lon: 9.99, lat: 54.994, kind: "place", left: 1 },
            { name: "Lillebælt", lon: 10.07, lat: 55.06, kind: "water", big: 1 }] });
  if (!s) return;
  const NS = "http://www.w3.org/2000/svg", m = s.meta;
  const svg = s.box.appendChild(document.createElementNS(NS, "svg"));
  svg.setAttribute("class", "leaders"); svg.setAttribute("viewBox", `0 0 ${m.w} ${m.h}`);
  svg.setAttribute("preserveAspectRatio", "none");
  const h = hand(svg, 21), k = m.w / 1000;
  T.race.forEach((r, i) => {
    const ink = i ? "redpen" : "graphite", side = i ? -1 : 1;
    const pts = r.track.map(p => [p[1] * m.w, p[2] * m.h]);
    h.line(pts, { ink, w: 3.2 * k + 1, rough: .5 });
    for (let t = 10; t < r.minutes; t += 10) {
      const q = r.track.find(p => p[0] >= t); if (!q) continue;
      const qi = r.track.indexOf(q), a = r.track[Math.max(0, qi - 1)];
      const dx = (q[1] - a[1]) * m.w, dy = (q[2] - a[2]) * m.h, L = Math.hypot(dx, dy) || 1;
      const nx = -dy / L * side * 12 * k, ny = dx / L * side * 12 * k, x = q[1] * m.w, y = q[2] * m.h;
      h.line([[x - nx, y - ny], [x + nx, y + ny]], { ink, w: 2 * k + .6 });
      h.text(x + nx * 2.6, y + ny * 2.6 + 6 * k, `${t}'`, { ink, size: 24 * k, anchor: "middle" });
    }
    // the result, written in the empty water below the crossing
    h.text(m.w * .3, m.h * (i ? .9 : .8), `${r.ship}, ${r.year}: ${r.minutes} min`, { ink, size: 44 * k, rot: -2 });
  });
})();

/* ---------------------------------------------- I4: the storm, on graph paper */
fig("c-i4", { ratio: .52, ratioNarrow: .95, margin: { top: 36, right: 96, bottom: 40, left: 46 }, marginNarrow: { right: 18 } }, (h, g, w, ht, narrow) => {
  const S = D.storms, x = d3.scaleLinear([-3, 3], [0, w]), y = d3.scaleLinear([0, 100], [ht, 0]);
  h.rule(0, ht, w, ht, { ink: "graphite", w: 1.2 });
  h.rule(0, 0, 0, ht, { ink: "graphite", w: 1.2 });
  [0, 25, 50, 75, 100].forEach(v => h.text(-8, y(v) + 6, v, { ink: "graphite", size: narrow ? 14 : 17, anchor: "end", rot: 0 }));
  S.offsets.forEach(o => h.text(x(o), ht + 26, o === 0 ? "storm day" : (o > 0 ? "+" : "−") + Math.abs(o), { ink: o ? "graphite" : "redpen", size: narrow ? 14 : 18, anchor: "middle", rot: 0 }));
  h.text(2, -14, "of every 100 boats heard, how many went out", { ink: "graphite", size: narrow ? 14 : 18, rot: 0 });
  h.shade(x(-.5), y(100), x(.5) - x(-.5), ht - y(100), { ink: "redpen", edge: false, gap: 7, w: .7, fw: .6, angle: 50 });
  h.text(x(0), y(100) - 4, "the storm", { ink: "redpen", size: narrow ? 16 : 21, anchor: "middle" });
  [["fishing", "greenpen", "fishing"], ["cargo", "graphite", "ship"]].forEach(([k, ink, kind]) => {
    S[k].each.forEach(line => h.curve(line.map(p => [x(p[0]), y(p[1])]), { ink, w: .8, rough: .5 }).setAttribute("opacity", .28));
    const mean = S[k].mean;
    h.curve(mean.map(p => [x(p[0]), y(p[1])]), { ink, w: 3 });
    mean.forEach(p => h.boat(x(p[0]), y(p[1]) - 3, narrow ? .6 : .9, { ink, kind }));
    const e = mean[mean.length - 1];
    if (!narrow) h.text(x(e[0]) + 12, y(e[1]) + 6, k === "fishing" ? "fishing\nboats" : "cargo\nships", { ink, size: 22 });
  });
  const f0 = S.fishing.mean.find(p => p[0] === 0);
  h.text(x(0) + (narrow ? -30 : 20), y(f0[1]) + (narrow ? 40 : 46), `storm day: ${N.storm_fishing_day} of 100`, { ink: "greenpen", size: narrow ? 16 : 22 });
}, 17);

/* --------------------------------------- I5: the harbour on a storm day */
fig("c-i5", { ratio: .62, ratioNarrow: 1.5, margin: { top: 8, right: 6, bottom: 8, left: 0 } }, (h, g, w, ht, narrow) => {
  const rows = D.stayed, INK = { sailing: "pen", fishing: "greenpen", work: "graphite", ferries: "redpen", cargo: "graphite" };
  const row = ht / rows.length, lab = narrow ? 0 : w * .2, hullL = narrow ? 7 : 10, hullW = hullL * .42;
  const hull = (cx, cy, ang, ink, o = {}) => {
    const c = Math.cos(ang), s_ = Math.sin(ang), P = (a, b) => [cx + a * c - b * s_, cy + a * s_ + b * c];
    const [p1, p2, p3, p4] = [P(-hullL / 2, 0), P(0, -hullW / 2), P(hullL / 2, 0), P(0, hullW / 2)];
    h.path(`M ${p1} Q ${p2} ${p3} Q ${p4} ${p1}`, Object.assign({ ink, w: 1.1, rough: .5 }, o));
  };
  rows.forEach((r, i) => {
    const y0 = row * i + 8, stayed = Math.round(r.value), out = 100 - stayed, ink = INK[r.fleet];
    const by = narrow ? y0 + 26 : y0;
    if (narrow) h.text(0, y0 + 18, `${r.label}: ${stayed} of 100 stay in`, { ink, size: 16, rot: 0 });
    else {
      h.text(0, y0 + row * .38, r.label, { ink: "ink", size: 21, rot: 0 });
      h.text(0, y0 + row * .78, `${stayed}`, { ink, size: 46, rot: -2 });
      h.text(58, y0 + row * .76, "of 100\nstay in", { ink: "graphite", size: 15, rot: 0 });
    }
    // the harbour: a mole drawn round the boats that stayed, open to the sea on the right
    const cols = Math.max(2, Math.ceil(stayed / 5)), hw = cols * (hullW * 2.6) + 20, hh = row * .78 - (narrow ? 26 : 8);
    const hx = lab, hy = by;
    if (stayed > 0) {
      h.path(`M ${hx + hw} ${hy} L ${hx} ${hy} L ${hx} ${hy + hh} L ${hx + hw} ${hy + hh}`, { ink: "graphite", w: 2.2, rough: .6 });
      for (let k = 0; k < stayed; k++) {
        const c = Math.floor(k / 5), rr = k % 5;
        hull(hx + 12 + c * hullW * 2.6, hy + hh * (rr + .5) / 5, Math.PI / 2, "graphite");
      }
    }
    // the sea: the rest, out and moving, a little wake behind each
    const sx = hx + (stayed > 0 ? hw + 22 : 0), sw = w - sx - 4;
    const per = Math.max(1, Math.ceil(out / 5)), stepX = sw / per;
    for (let k = 0; k < out; k++) {
      const c = Math.floor(k / 5), rr = k % 5;
      const cx = sx + stepX * (c + .5) + h.j(stepX * .5), cy = hy + hh * (rr + .5) / 5 + h.j(hh / 8);
      const ang = -.25 + h.j(.5);
      hull(cx, cy, ang, ink);
      h.line([[cx - Math.cos(ang) * hullL * .6, cy - Math.sin(ang) * hullL * .6], [cx - Math.cos(ang) * hullL * 1.5, cy - Math.sin(ang) * hullL * 1.5]], { ink, w: .6, rough: .4 });
    }
  });
}, 23);

/* ------------------------------------------------- T4: Amy, three sheets */
(function amy() {
  const box = el("c-t4"); if (!box) return;
  const row = box.appendChild(document.createElement("div"));
  row.className = "storm-row";
  [["storms-amy-0", "the day before"], ["storms-amy-1", "Amy"], ["storms-amy-2", "two days after"]].forEach(([id, t], i) => {
    const cell = row.appendChild(document.createElement("div"));
    chart.sheet(cell, id, { ticks: false, scale: false, names: [], eager: true });
    const tl = cell.appendChild(document.createElement("p"));
    tl.className = "tagline" + (i === 1 ? " red" : "");
    const dots = ((window.SEAFOLK_CHARTS || {})[id] || {}).dots;
    tl.textContent = dots ? `${t}: ${sp(dots)} fishing hours` : t;
  });
})();

/* ------------------------------------------------ I7: the radio's ceiling */
fig("c-i7", { ratio: .5, ratioNarrow: 1.05, margin: { top: 14, right: 12, bottom: 10, left: 0 } }, (h, g, w, ht, narrow) => {
  const I = D.impossible, times = I.worst.times, full = Math.floor(times);
  const x0 = narrow ? 0 : w * .3, sw = w - x0, sh = Math.min(26, ht / (full + 4));
  const strip = (y, frac, ink) => {
    h.shade(x0, y, sw * frac, sh, { ink, gap: 3.2, w: 1, fw: .8, angle: -50 });
    for (let k = 1; k < 24; k++) if (k / 24 < frac) h.rule(x0 + sw * k / 24, y, x0 + sw * k / 24, y + sh * .35, { ink, w: .6 });
  };
  const ty = narrow ? 40 : 10;
  if (narrow) h.text(0, 22, `one radio, flat out, one day: ${sp(I.cap)}`, { ink: "graphite", size: 16 });
  else h.text(0, ty + sh * .8, `one radio, flat out,\nall day: ${sp(I.cap)}`, { ink: "graphite", size: 19 });
  strip(ty, 1, "graphite");
  const wy = ty + sh * 2.4;
  for (let k = 0; k < full; k++) strip(wy + k * sh * 1.25, 1, "redpen");
  strip(wy + full * sh * 1.25, times - full, "redpen");
  const ly = wy + (full + 1) * sh * 1.25 + (narrow ? 26 : 8);
  if (narrow) h.text(0, ly, `one ship, one day, in the archive: ${sp(I.worst.msgs)}`, { ink: "redpen", size: 16 });
  else h.text(0, wy + sh * 2, `one ship, one day,\nin the archive:\n${sp(I.worst.msgs)}`, { ink: "redpen", size: 22 });
  h.text(x0 + sw * (times - full) + 14, wy + full * sh * 1.25 + sh * .9, `×${times}`, { ink: "redpen", size: narrow ? 20 : 30 });
}, 29);

/* ---------------------------------------------- H3: the loop, as a sketch */
fig("c-h3", { ratio: .42, ratioNarrow: 1.15, margin: { top: 30, right: 10, bottom: 20, left: 10 } }, (h, g, w, ht, narrow) => {
  const P = D.part_how.pipe, size = narrow ? 15 : 20;
  const box = (x, y, bw, bh, title, sub, ink = "pen") => {
    h.shade(x, y, bw, bh, { ink, fill: ink, gap: 7, w: 1.6, fw: .35, angle: -30 });
    h.text(x + bw / 2, y + bh / 2 - 4, title, { ink, size: size + 2, anchor: "middle", rot: 0 });
    h.text(x + bw / 2, y + bh / 2 + size + 2, sub, { ink: "graphite", size: size - 3, anchor: "middle", rot: 0 });
  };
  const arrow = (a, b, label, ink = "pen") => {
    h.line([a, b], { ink, w: 1.6, rough: .6 });
    const ang = Math.atan2(b[1] - a[1], b[0] - a[0]), L = 11;
    h.line([[b[0] - L * Math.cos(ang - .45), b[1] - L * Math.sin(ang - .45)], b, [b[0] - L * Math.cos(ang + .45), b[1] - L * Math.sin(ang + .45)]], { ink, w: 1.6 });
    if (label) h.text((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - 10, label, { ink: "graphite", size: size - 4, anchor: "middle" });
  };
  if (!narrow) {
    const bw = w * .22, bh = ht * .36, cy = ht * .32;
    box(0, cy - bh / 2, bw, bh, "the archive", `${N.how_archive_tb} TB of zip files`, "graphite");
    box(w * .39, cy - bh / 2, bw, bh, "ClickHouse", `on a Mac Mini, ${P.rate_million} M lines/s`);
    box(w - bw, cy - bh / 2, bw, bh, "the counts", `${P.store_gb} GB, kept`);
    arrow([bw + 6, cy], [w * .39 - 8, cy], `one file at a time, ${N.how_ahead} waiting`);
    arrow([w * .39 + bw + 6, cy], [w - bw - 8, cy], "counts");
    const zx = w * .39 + bw / 2, zy = ht * .82;
    arrow([zx, cy + bh / 2 + 6], [zx, zy - 26], "", "redpen");
    h.text(zx, zy, "zip deleted", { ink: "redpen", size: size + 4, anchor: "middle", rot: -3 });
    h.line([[zx - 60, zy - 8], [zx + 62, zy - 14]], { ink: "redpen", w: 1.4 });
    h.path(`M ${zx + 80} ${zy - 6} C ${w * .2} ${ht * 1.02}, ${bw * .4} ${ht * .9}, ${bw * .5} ${cy + bh / 2 + 6}`, { ink: "graphite", w: 1.2, rough: .8 });
    h.text(w * .16, ht * .9, `next file: ${sp(P.files)} times`, { ink: "graphite", size: size - 2, rot: -2 });
  } else {
    const bw = w * .8, bh = ht * .14, x = (w - bw) / 2;
    box(x, 0, bw, bh, "the archive", `${N.how_archive_tb} TB of zip files`, "graphite");
    box(x, ht * .36, bw, bh, "ClickHouse", `on a Mac Mini, ${P.rate_million} M lines/s`);
    box(x, ht * .72, bw, bh, "the counts", `${P.store_gb} GB, kept`);
    arrow([w / 2, bh + 6], [w / 2, ht * .36 - 8], "one file at a time");
    arrow([w / 2, ht * .36 + bh + 6], [w / 2, ht * .72 - 8], "counts");
    h.text(w * .72, ht * .6, "zip\ndeleted", { ink: "redpen", size: 18, anchor: "middle", rot: -4 });
  }
}, 31);

})();
