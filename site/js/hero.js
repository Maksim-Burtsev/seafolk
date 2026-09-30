/* Seafolk — the hero: one summer Saturday of Danish ferries, drawn by a pen.
 *
 * window.SEAFOLK_FERRY_DAY (site/media/charts/hero-ferries.js, written by
 * scripts/charts_index.py) holds every passenger ship that moved that day as
 * [minute since midnight UTC, x, y] with x and y as fractions of the hero
 * sheet. The canvas lies exactly over the sheet's image, so a fraction is a
 * pixel after one multiplication.
 *
 * Two layers: ink that only accumulates (the day's wake, drawn a few segments
 * at a time as the clock passes them) and the ships themselves, redrawn every
 * frame. The day plays in DAY_MS and holds its finished web for HOLD_MS before
 * the paper is cleaned and it starts again. Off screen it stops; with reduced
 * motion it draws the whole day once and holds still.
 */
(function () {
"use strict";
const DAY_MS = 28000, HOLD_MS = 5000;
const LOCAL = 120;          // July in Denmark is UTC+2

window.hero = function (el, clockEl, countEl) {
  const D = window.SEAFOLK_FERRY_DAY;
  const s = chart.sheet(el, "hero", { eager: true, names: ["Skagerrak", "Kattegat", "Nordsøen", "Østersøen",
    "Storebælt", "Øresund", "København", "Aarhus", "Skagen", "Kiel", "Rønne", "Esbjerg"],
    alt: "A nautical chart of Danish waters with the tracks of the day's ferries drawn over it" });
  if (!s || !D) { if (!D) console.error("hero: SEAFOLK_FERRY_DAY did not load"); return; }
  const ink = s.box.insertBefore(document.createElement("canvas"), s.box.querySelector("svg"));
  const top = s.box.insertBefore(document.createElement("canvas"), s.box.querySelector("svg"));
  const ci = ink.getContext("2d"), ct = top.getContext("2d");
  const red = getComputedStyle(document.documentElement).getPropertyValue("--ferry").trim();
  const ships = D.ships;
  let W = 0, H = 0, dpr = 1, drawnTo = -1, start = null, raf = 0, visible = true;

  function size() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = s.box.clientWidth; H = s.box.clientHeight;
    for (const c of [ink, top]) { c.width = Math.round(W * dpr); c.height = Math.round(H * dpr); }
    ci.setTransform(dpr, 0, 0, dpr, 0, 0); ct.setTransform(dpr, 0, 0, dpr, 0, 0);
    drawnTo = -1;
  }

  // Draw every segment that ends in (from, to] minutes, onto the ink layer.
  function inkUpTo(to) {
    const from = drawnTo;
    if (to <= from) return;
    ci.strokeStyle = red; ci.lineWidth = Math.max(.6, W / 1500); ci.globalAlpha = .55;
    ci.lineCap = "round"; ci.beginPath();
    for (const tr of ships) {
      for (let i = 1; i < tr.length; i++) {
        const a = tr[i - 1], b = tr[i];
        if (b[0] <= from) continue;
        if (b[0] > to) break;
        if (b[0] - a[0] > 10) continue;                 // a radio gap is not a crossing
        ci.moveTo(a[1] * W, a[2] * H); ci.lineTo(b[1] * W, b[2] * H);
      }
    }
    ci.stroke();
    drawnTo = to;
  }

  // Where each ship is at minute t, and whether it is moving.
  function positions(t) {
    const out = [];
    for (const tr of ships) {
      if (t < tr[0][0] || t > tr[tr.length - 1][0]) continue;
      let i = 1;
      while (i < tr.length && tr[i][0] < t) i++;
      if (i >= tr.length) continue;
      const a = tr[i - 1], b = tr[i];
      if (b[0] - a[0] > 10) continue;
      const f = (t - a[0]) / Math.max(b[0] - a[0], 1);
      const dx = (b[1] - a[1]) * W, dy = (b[2] - a[2]) * H;
      out.push({ x: (a[1] + f * (b[1] - a[1])) * W, y: (a[2] + f * (b[2] - a[2])) * H,
                 moving: Math.hypot(dx, dy) > W / 1400, ang: Math.atan2(dy, dx) });
    }
    return out;
  }

  function drawShips(t) {
    ct.clearRect(0, 0, W, H);
    const pos = positions(t);
    let moving = 0;
    const r = Math.max(2.2, W / 520);
    for (const p of pos) {
      if (!p.moving) continue;
      moving++;
      // a small hull pointing along its course
      ct.save(); ct.translate(p.x, p.y); ct.rotate(p.ang);
      ct.beginPath(); ct.moveTo(r * 1.9, 0); ct.lineTo(-r, r * .85); ct.lineTo(-r, -r * .85); ct.closePath();
      ct.fillStyle = red; ct.strokeStyle = "#f8f3e6"; ct.lineWidth = 1.2;
      ct.fill(); ct.stroke(); ct.restore();
    }
    return moving;
  }

  function show(t, moving) {
    const m = Math.floor(t + LOCAL) % 1440;
    if (clockEl) clockEl.textContent = `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")} in Denmark`;
    if (countEl) countEl.textContent = moving;
  }

  function frame(now) {
    if (!visible) { raf = 0; return; }
    if (start === null) start = now;
    const e = now - start;
    if (e > DAY_MS + HOLD_MS) {                           // clean the paper, go again
      ci.clearRect(0, 0, W, H); drawnTo = -1; start = now;
    }
    const t = Math.min(1439, 1440 * Math.min(e, DAY_MS) / DAY_MS);
    inkUpTo(t);
    show(t, drawShips(t));
    raf = requestAnimationFrame(frame);
  }

  function still() {
    ci.clearRect(0, 0, W, H); drawnTo = -1; inkUpTo(1440); ct.clearRect(0, 0, W, H);
    if (clockEl) clockEl.textContent = "the whole day";
    if (countEl) countEl.textContent = ships.length;
  }

  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const go = () => {
    size();
    if (reduced) { still(); return; }
    start = null;
    if (!raf) raf = requestAnimationFrame(frame);
  };
  if (s.img.complete) go(); else s.img.addEventListener("load", go);
  new ResizeObserver(() => { if (s.box.clientWidth !== W) go(); }).observe(s.box);
  new IntersectionObserver(([en]) => {
    visible = en.isIntersecting;
    if (visible && !raf && !reduced) raf = requestAnimationFrame(frame);
  }).observe(s.box);
};
})();
