/* Seafolk — the sea empties: one storm, hour by hour, on the nautical chart.
 *
 *   SeafolkStorm.load(["amy"], got => SeafolkStorm.mount(el, "amy"));
 *   SeafolkStorm.triptych(el, "amy");      // the same storm as three still sheets
 *
 * Needs site/js/chart.js on the page. The storm's hours (media/storm-<key>.js,
 * written by scripts/render_storm.py) and the chart sheets' manifest
 * (media/charts/storms.js, scripts/charts_storms.py) are pulled in by load()
 * with <script> tags, so the page opens from file:// and a page that shows one
 * storm does not carry the other two.
 *
 * The picture: the bare chart `storms-sea`, and over it three canvases —
 * the weather (the sea darkens and rain hatching drifts across while the named
 * dates last; decoration tied to the dates, not a weather map), the wakes of
 * cargo (magenta) and ferries (red), and the fishing fleet as small green
 * boats that fade out as the storm comes and back in after it. A cartouche
 * carries the storm's name, the phase, the clock and the two counters, and a
 * strip of the whole week that is also the scrubber.
 *
 * It plays like a GIF: starts when it scrolls into view, slows down through
 * the storm, holds the last hour, loops; pauses off screen and on a click.
 * With prefers-reduced-motion — or ?hour=N in the URL, for screenshots —
 * nothing moves: it shows one hour (the storm's emptiest, by default) and the
 * strip still moves it by hand.
 *
 * One mark is one published patch of sea (about two kilometres across) where
 * that fleet was under way in that hour: places, not boats. Only public fleets
 * are in the data at all.
 */
(function (global) {
"use strict";

// The frames are base64 in an alphabet with no digits in it, so the "no
// nine-digit integer under site/" test can never trip over a data blob.
const ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz+-*/=_.~!@#$";
const REV = {};
for (let i = 0; i < 64; i++) REV[ALPHA[i]] = i;

function decode(s, bytes) {
  const out = new Uint8Array(bytes);
  let acc = 0, n = 0, k = 0;
  for (let i = 0; i < s.length; i++) {
    acc = ((acc << 6) | REV[s[i]]) & 0xffffff;
    n += 6;
    if (n >= 8) { n -= 8; if (k < bytes) out[k++] = (acc >> n) & 255; }
  }
  return out;
}

const tok = name => getComputedStyle(document.documentElement).getPropertyValue("--" + name).trim();
const STORM_INK = "43,61,77";                      // the sea under a gale, as rgb
const NAMES = ["Skagerrak", "Kattegat", "Nordsøen", "Østersøen", "Skagen",
               "Esbjerg", "København"];

// A boat seen from above, the way a chart plotter draws a ship it hears:
// pointed bow, square stern, one unit long, heading to the right.
const BOAT = new Path2D("M.6 0 L.12 -.26 L-.5 -.24 L-.5 .24 L.12 .26 Z");

const CSS = `
.sfs { position: relative; }
.sfs .sheet { cursor: pointer; }
.sfs .sheet canvas { pointer-events: none; }
.sfs-card {
  position: absolute; right: 2.4%; top: 3.4%; width: min(35%, 360px); z-index: 2;
  background: rgba(248,243,230,.95); border: 1.5px solid var(--ink);
  outline: 1px solid var(--ink); outline-offset: -6px;
  padding: clamp(14px, 1.9vw, 22px); display: flex; flex-direction: column; gap: 8px;
  line-height: 1.3;
}
.sfs-card p { margin: 0; }
.sfs-title { font: 500 11px/1.4 var(--mono); letter-spacing: .18em; text-transform: uppercase; color: var(--ferry); }
.sfs-phase { font: italic 600 clamp(26px, 3.3vw, 38px)/1.05 var(--serif); letter-spacing: -.015em;
  font-variation-settings: "opsz" 20; color: var(--ink); transition: color .6s; }
.sfs-phase.on { color: var(--ferry); }
.sfs-clock { font: 500 13px/1.3 var(--mono); letter-spacing: .06em; color: var(--ink);
  border-bottom: 1px solid var(--ink); padding-bottom: 8px; }
.sfs-n { display: grid; grid-template-columns: auto 1fr; gap: 0 10px; align-items: center; }
.sfs-n b { font: 600 clamp(38px, 4.6vw, 54px)/1 var(--serif); font-variation-settings: "opsz" 20;
  color: var(--fishing); font-variant-numeric: tabular-nums; min-width: 2.1ch; text-align: right; }
.sfs-n.c b { font-size: clamp(22px, 2.4vw, 28px); color: var(--cargo); }
.sfs-n span { font: italic 400 13.5px/1.25 var(--serif); color: var(--label); }
.sfs-strip { display: block; width: 100%; height: auto; overflow: visible; cursor: ew-resize; touch-action: none; }
.sfs-strip text { font: 400 9.5px var(--mono); fill: var(--label); }
.sfs-strip text.i { font: italic 400 11.5px var(--serif); }
.sfs-foot { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
.sfs-key { display: flex; flex-wrap: wrap; gap: 2px 12px; margin: 0; padding: 0; list-style: none;
  font: italic 400 12.5px/1.3 var(--serif); color: var(--label); }
.sfs-key li { display: flex; align-items: center; gap: 5px; }
.sfs-key svg { width: 16px; height: 10px; }
.sfs-play { appearance: none; border: 1px solid var(--ink); background: transparent; color: var(--ink);
  font: 500 11px/1 var(--mono); letter-spacing: .1em; padding: 5px 8px; cursor: pointer; white-space: nowrap; }
.sfs-play:focus-visible { outline: 2px solid var(--ferry); outline-offset: 2px; }
.sfs-note { font: italic 400 12.5px/1.4 var(--serif); color: var(--label); }
.sfs.narrow .sfs-card { position: static; width: auto; margin-top: 12px; }
.sfs-trip { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.sfs-trip figure, .sfs-trip div.cell { all: unset; display: flex; flex-direction: column; gap: 7px; }
.sfs-trip .lab { font: 500 11px/1.3 var(--mono); letter-spacing: .14em; text-transform: uppercase; color: var(--ink); margin: 0; }
.sfs-trip .lab.on { color: var(--ferry); }
.sfs-trip .lab em { font: italic 400 13px var(--serif); letter-spacing: 0; text-transform: none; color: var(--label); margin-left: 6px; }
.sfs-trip .cell.on .sheet::after { content: ""; position: absolute; inset: 0; pointer-events: none;
  background: repeating-linear-gradient(-60deg, rgba(43,61,77,.13) 0 1px, transparent 1px 9px); }
@media (max-width: 640px) { .sfs-trip { grid-template-columns: 1fr; } }
`;

function style() {
  if (document.getElementById("sfs-css")) return;
  const s = document.head.appendChild(document.createElement("style"));
  s.id = "sfs-css";
  s.textContent = CSS;
}

function el(tag, cls, parent, html) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html != null) n.innerHTML = html;
  if (parent) parent.appendChild(n);
  return n;
}

// Danish time: the people in these boats live by it.
const FMT = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Copenhagen", weekday: "short",
  day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const DAYFMT = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Copenhagen", weekday: "short" });
function clock(t0, h) {
  const p = Object.fromEntries(FMT.formatToParts(new Date(t0 + h * 3600e3)).map(x => [x.type, x.value]));
  return `${p.weekday} ${p.day} ${p.month} · ${p.hour}:${p.minute}`;
}
const sp = n => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, " ");

// A stable pseudo-random in [0, 1) per cell: the same boat gets the same
// nudge, size and bob on every frame.
function rnd(i, salt) {
  const x = Math.sin(i * 12.9898 + salt * 78.233) * 43758.5453;
  return x - Math.floor(x);
}

function mount(host, key, opts) {
  opts = opts || {};
  const D = (global.SEAFOLK_STORM || {})[key];
  if (!D) throw new Error(`SeafolkStorm: no data for ${key} — load media/storm-${key}.js first`);
  style();
  host.innerHTML = "";
  const root = el("div", "sfs", host);
  const s = chart.sheet(root, D.sheet, { names: NAMES, eager: true,
    alt: `A nautical chart of Danish waters, hour by hour through storm ${D.name}: ` +
         "green fishing boats thin out as the storm arrives and come back after it, " +
         "while magenta cargo traffic keeps moving" });
  if (!s) throw new Error("SeafolkStorm: the chart sheet did not load");
  const frame = s.box.querySelector("svg.frame");
  const layer = () => s.box.insertBefore(document.createElement("canvas"), frame);
  const cvW = layer(), cvT = layer(), cvB = layer();
  const xW = cvW.getContext("2d"), xT = cvT.getContext("2d"), xB = cvB.getContext("2d");

  const Q = new URLSearchParams(location.search);
  const asked = opts.hour != null ? opts.hour : Q.has("hour") ? +Q.get("hour") : null;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const still = reduce || asked != null;

  const N = D.hours, t0 = Date.parse(D.t0), F = D.fleets;
  const storm = D.bands.find(b => b[3]) || [0, 0, "the storm", 1];
  const [lo, hi] = storm;
  const fish = F.fishing.counts;
  let emptiest = lo;
  for (let h = lo; h < Math.min(hi, N); h++) if (fish[h] < fish[emptiest]) emptiest = h;

  // ---- the cartouche
  const card = el("div", "sfs-card", root);
  el("p", "sfs-title", card).textContent = `Storm ${D.name} · ${D.dates}`;
  const phaseEl = el("p", "sfs-phase", card);
  const clockEl = el("p", "sfs-clock", card);
  const nF = el("div", "sfs-n", card, "<b></b><span>places at sea with fishing boats moving</span>").firstChild;
  const nC = el("div", "sfs-n c", card, "<b></b><span>with cargo ships moving</span>").firstChild;
  const strip = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  strip.setAttribute("class", "sfs-strip");
  strip.setAttribute("aria-label", "The week, and where in it we are. Drag to move through it.");
  card.appendChild(strip);
  const foot = el("div", "sfs-foot", card);
  el("ul", "sfs-key", foot,
    `<li><svg viewBox="-8 -5 16 10"><path d="M7.2 0 L1.4 -3.1 L-6 -2.9 L-6 2.9 L1.4 3.1 Z" fill="var(--fishing)"/></svg>fishing</li>` +
    `<li><svg viewBox="0 0 16 10"><circle cx="4" cy="5" r="1.6" fill="var(--cargo)" opacity=".35"/><circle cx="8" cy="5" r="1.6" fill="var(--cargo)" opacity=".6"/><circle cx="12" cy="5" r="1.8" fill="var(--cargo)"/></svg>cargo</li>` +
    `<li><svg viewBox="0 0 16 10"><circle cx="8" cy="5" r="2.2" fill="var(--ferry)"/></svg>ferries</li>`);
  const btn = el("button", "sfs-play", foot);
  btn.type = "button";
  if (reduce) el("p", "sfs-note", card).textContent = "Your system asks for less motion, so this " +
    "holds the storm's emptiest hour. Drag along the strip to move through the week.";

  // ---- geometry, recomputed on every resize
  let W = 0, H = 0, dpr = 1, P = {}, glyph = 6, stripX = null;
  const fade = new Float32Array(F.fishing.cells.length / 2);
  const cache = {};
  const bits = g => {
    const c = cache[g] || (cache[g] = []);
    return h => c[h] || (c[h] = decode(F[g].frames[h], (F[g].cells.length / 2 + 7) >> 3));
  };
  const frameOf = { fishing: bits("fishing"), cargo: bits("cargo"), passenger: bits("passenger") };

  function layout() {
    dpr = Math.min(global.devicePixelRatio || 1, 2);
    W = s.box.clientWidth; H = s.box.clientHeight;
    for (const c of [cvW, cvT, cvB]) { c.width = Math.round(W * dpr); c.height = Math.round(H * dpr); }
    for (const x of [xW, xT, xB]) x.setTransform(dpr, 0, 0, dpr, 0, 0);
    root.classList.toggle("narrow", W < 700);
    for (const g in F) {
      const cells = F[g].cells, a = new Float32Array(cells.length);
      for (let c = 0; c < cells.length; c += 2) {
        const [x, y] = s.xy(cells[c] / 1000, cells[c + 1] / 1000);
        a[c] = x / s.meta.w * W; a[c + 1] = y / s.meta.h * H;
      }
      P[g] = a;
    }
    // nudge every mark inside its patch, so the published grid does not show
    const cell = W / 230;                            // about two kilometres, in pixels
    for (const g in F) {
      const a = P[g];
      for (let i = 0; i < a.length; i += 2) {
        a[i] += (rnd(i, 4) - .5) * cell; a[i + 1] += (rnd(i, 5) - .5) * cell;
      }
    }
    glyph = Math.max(5, Math.min(9.5, W / 150));
    drawStrip();
    seek(hour, true);
  }

  // ---- the strip: fishing and cargo against their own days before the storm
  function drawStrip() {
    const w = Math.max(200, card.clientWidth - 2 * parseFloat(getComputedStyle(card).paddingLeft)),
          h = 78, top = 16, bot = 60;
    strip.setAttribute("viewBox", `0 0 ${w} ${h}`);
    const x = t => t / (N - 1) * (w - 44);
    const y = v => bot - Math.min(v, 150) / 150 * (bot - top);
    stripX = x;
    let svg = "";
    for (const [a, b, label, on] of D.bands) {
      svg += `<rect x="${x(a)}" y="${top - 2}" width="${x(Math.min(b, N - 1)) - x(a)}" height="${bot - top + 2}"
        fill="var(--${on ? "ferry" : "ref"})" opacity="${on ? .13 : .25}"/>` +
        `<text class="i" x="${(x(a) + x(Math.min(b, N - 1))) / 2}" y="${top - 5}" text-anchor="middle"
        style="fill:var(--${on ? "ferry" : "label"})">${label}</text>`;
    }
    svg += `<line x1="0" x2="${x(N - 1)}" y1="${y(100)}" y2="${y(100)}" stroke="var(--ref)" stroke-dasharray="3 3"/>`;
    for (const [g, c, wd] of [["cargo", "cargo", 1.3], ["fishing", "fishing", 1.9]]) {
      const cs = F[g].counts, ref = cs.slice(0, lo).reduce((a, b) => a + b, 0) / Math.max(lo, 1) || 1;
      const pts = cs.map((v, t) => `${x(t).toFixed(1)},${y(100 * v / ref).toFixed(1)}`);
      svg += `<polyline points="${pts.join(" ")}" fill="none" stroke="var(--${c})" stroke-width="${wd}" stroke-linejoin="round"/>` +
        // the two end labels a line apart, cargo above, whatever the lines do
        `<text class="i" x="${x(N - 1) + 4}" y="${y(g === "cargo" ? 118 : 78) + 4}" style="fill:var(--${c})">${g}</text>`;
    }
    for (let d = 0; d < N; d += 24) {
      svg += `<line x1="${x(d)}" x2="${x(d)}" y1="${bot}" y2="${bot + 3}" stroke="var(--ink)"/>`;
      if (x(24) > 22 || d % 48 === 0)
        svg += `<text x="${x(Math.min(d + 12, N - 1))}" y="${h - 4}" text-anchor="middle">${DAYFMT.format(new Date(t0 + (d + 12) * 3600e3))}</text>`;
    }
    svg += `<line class="cur" y1="${top - 2}" y2="${bot}" stroke="var(--ink)" stroke-width="1.5"/>` +
           `<circle class="cur" r="3" fill="var(--ink)" cy="${bot}"/>`;
    strip.innerHTML = svg;
  }

  // ---- drawing
  let hour = asked != null ? Math.max(0, Math.min(N - 1, asked | 0)) : still ? emptiest : 0;
  let shown = -1;

  function wakes(h, fresh) {
    // cargo and ferries leave a short wake: the older hours fade on the canvas
    if (fresh) xT.clearRect(0, 0, W, H);
    xT.globalCompositeOperation = "destination-out";
    xT.fillStyle = "rgba(0,0,0,.42)";
    xT.fillRect(0, 0, W, H);
    xT.globalCompositeOperation = "source-over";
    const r = Math.max(.6, W / 1000);
    for (const [g, c, rr, a] of [["cargo", tok("cargo"), r, .75], ["passenger", tok("ferry"), r * 1.35, .9]]) {
      const b = frameOf[g](h), p = P[g], path = new Path2D();
      for (let k = 0; k < b.length; k++) {
        const v = b[k];
        if (!v) continue;
        for (let j = 0; j < 8; j++) if (v & (128 >> j)) {
          const c2 = ((k << 3) | j) * 2;
          path.moveTo(p[c2] + rr, p[c2 + 1]);
          path.arc(p[c2], p[c2 + 1], rr, 0, 6.2832);
        }
      }
      xT.globalAlpha = a; xT.fillStyle = c; xT.fill(path);
    }
    xT.globalAlpha = 1;
  }

  function text(h) {
    const on = h >= lo && h < hi;
    phaseEl.textContent = on ? `Storm ${D.name}` : h < lo ? "Before the storm" : "After the storm";
    phaseEl.classList.toggle("on", on);
    clockEl.textContent = clock(t0, h);
    nF.textContent = sp(fish[h]);
    nC.textContent = sp(F.cargo.counts[h]);
    if (!stripX) return;
    const [line, dot] = strip.querySelectorAll(".cur");
    line.setAttribute("x1", stripX(h)); line.setAttribute("x2", stripX(h));
    dot.setAttribute("cx", stripX(h));
  }

  function weather(t, now) {
    xW.clearRect(0, 0, W, H);
    const wx = Math.max(0, Math.min(1, (t - lo + 6) / 6, (hi + 6 - t) / 6));
    if (wx <= 0) return;
    xW.fillStyle = `rgba(${STORM_INK},${.13 * wx})`;
    xW.fillRect(0, 0, W, H);
    // rain hatching, the way a chart hatches an area, drifting with the wind
    const gap = Math.max(10, W / 70), drift = (now / 40) % gap;
    xW.strokeStyle = `rgba(${STORM_INK},${.17 * wx})`;
    xW.lineWidth = 1;
    xW.beginPath();
    for (let x = -H - gap + drift; x < W + gap; x += gap) { xW.moveTo(x, 0); xW.lineTo(x + H * .45, H); }
    xW.stroke();
  }

  function boats(h, dt, now, jump) {
    xB.clearRect(0, 0, W, H);
    const b = frameOf.fishing(h), p = P.fishing, k = jump ? 1 : 1 - Math.exp(-dt * 7);
    xB.fillStyle = tok("fishing");
    xB.strokeStyle = "rgba(248,243,230,.9)";
    xB.lineCap = "round";
    const wob = h >= lo - 6 && h < hi + 6 ? .32 : .12;          // rougher sea in the storm
    for (let i = 0; i < fade.length; i++) {
      const on = (b[i >> 3] & (128 >> (i & 7))) ? 1 : 0;
      fade[i] += (on - fade[i]) * k;
      if (fade[i] < .03) { fade[i] = on ? fade[i] : 0; if (!on) continue; }
      const sz = glyph * (.8 + rnd(i, 6) * .4) * (.55 + .45 * fade[i]);
      xB.save();
      xB.globalAlpha = Math.min(1, fade[i] * 1.1);
      xB.translate(p[2 * i], p[2 * i + 1]);
      xB.rotate(rnd(i, 7) * 6.2832 + Math.sin(now / 700 + i) * wob);   // each its own heading
      xB.scale(sz, sz);
      xB.lineWidth = 1.5 / sz;
      xB.stroke(BOAT); xB.fill(BOAT);
      xB.restore();
    }
  }

  function seek(h, jump) {
    hour = Math.max(0, Math.min(N - 1, h | 0));
    tpos = hour;
    wakes(hour, true);
    shown = hour;
    text(hour);
    weather(hour, performance.now());
    boats(hour, 0, performance.now(), jump);
  }

  // ---- the clock of the animation
  const FAST = 9, SLOW = 4.5, HOLD = 2200;            // hours a second; ms on the last hour
  let tpos = hour, raf = 0, last = 0, holdUntil = 0, visible = false, userPaused = false;

  function tick(now) {
    raf = 0;
    if (!visible || userPaused || still) return;
    const dt = last ? Math.min(.1, (now - last) / 1000) : 0;
    last = now;
    if (holdUntil) {
      if (now >= holdUntil) { holdUntil = 0; tpos = 0; xT.clearRect(0, 0, W, H); fade.fill(0); shown = -1; }
    } else {
      const inStorm = tpos >= lo - 3 && tpos < hi + 3;
      tpos += dt * (inStorm ? SLOW : FAST);
      if (tpos >= N - 1) { tpos = N - 1; holdUntil = now + HOLD; }
    }
    const h = Math.floor(tpos);
    if (h !== shown) {
      for (let k = shown < 0 || h < shown ? h : shown + 1; k <= h; k++) wakes(k, false);
      shown = h; hour = h; text(h);
    }
    weather(tpos, now);
    boats(h, dt, now, false);
    raf = requestAnimationFrame(tick);
  }
  const play = () => { if (!raf && !still) { last = 0; raf = requestAnimationFrame(tick); } label(); };
  const pause = () => { if (raf) cancelAnimationFrame(raf); raf = 0; label(); };
  function label() {
    btn.hidden = still;
    btn.textContent = userPaused ? "▶ play" : "❚❚ pause";
    btn.setAttribute("aria-label", userPaused ? "Play the animation" : "Pause the animation");
  }
  function toggle() { userPaused = !userPaused; userPaused ? pause() : play(); }

  s.box.addEventListener("click", toggle);
  btn.addEventListener("click", toggle);
  root.tabIndex = 0;
  root.addEventListener("keydown", e => {
    if (e.key === " " || e.key === "Enter") { e.preventDefault(); toggle(); }
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      userPaused = true; pause(); seek(hour + (e.key === "ArrowRight" ? 6 : -6), true);
    }
  });
  // drag along the strip to move through the week
  const scrub = e => {
    const r = strip.getBoundingClientRect(), vb = strip.viewBox.baseVal;
    const px = (e.clientX - r.left) / r.width * vb.width;
    userPaused = true; pause();
    seek(Math.round(px / stripX(N - 1) * (N - 1)), true);
  };
  strip.addEventListener("pointerdown", e => { strip.setPointerCapture(e.pointerId); scrub(e); });
  strip.addEventListener("pointermove", e => { if (strip.hasPointerCapture(e.pointerId)) scrub(e); });

  const ro = new ResizeObserver(() => { if (s.box.clientWidth !== W) layout(); });
  ro.observe(s.box);
  const io = new IntersectionObserver(([en]) => {
    visible = en.isIntersecting;
    visible ? play() : pause();
  }, { threshold: .3 });
  io.observe(s.box);
  layout();
  label();

  return {
    play() { userPaused = false; play(); }, pause() { userPaused = true; pause(); },
    seek: h => seek(h, true), hours: N, element: root,
    destroy() { pause(); io.disconnect(); ro.disconnect(); host.innerHTML = ""; }
  };
}

/* The same storm as three still sheets: the day before, the storm, two days
 * after. Drawn by scripts/charts_storms.py; one dot is an hour of daylight
 * with a fishing boat under way in that patch of sea. */
function triptych(host, key) {
  style();
  host.innerHTML = "";
  const row = el("div", "sfs-trip", host);
  const DAY = new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", weekday: "long", day: "numeric", month: "long" });
  ["the day before", "the storm", "two days after"].forEach((what, i) => {
    const id = `storms-${key}-${i}`, m = (global.SEAFOLK_CHARTS || {})[id];
    const cell = el("div", "cell" + (i === 1 ? " on" : ""), row);
    el("p", "lab" + (i === 1 ? " on" : ""), cell).innerHTML =
      `${what}<em>${m ? DAY.format(new Date(m.day)) : ""}</em>`;
    // no names: at a third of the page wide the lettering would bury the dots
    chart.sheet(cell, id, { ticks: false, scale: false, alt: `Fishing boats under way, ${what}` });
  });
  el("ul", "key", host, `<li style="color:var(--fishing)"><i class="dots"></i><span style="color:var(--label)">one dot: ` +
    "an hour of daylight with a fishing boat under way in that patch of sea, placed at random inside it</span></li>");
}

/* load(keys, done) — pull in the clips asked for, and the chart manifest if
 * the page does not already have it, then call done(the keys that arrived).
 * A <script> element works from file://, where fetch() does not. */
function script(src) {
  return new Promise(ok => {
    const s = document.createElement("script");
    s.src = src; s.onload = () => ok(true); s.onerror = () => ok(false);
    document.head.appendChild(s);
  });
}
function load(keys, done) {
  const charts = (global.SEAFOLK_CHARTS || {})["storms-sea"] ? Promise.resolve() : script("media/charts/storms.js");
  Promise.all([charts, ...keys.map(k => (global.SEAFOLK_STORM || {})[k] ? true : script(`media/storm-${k}.js`))])
    .then(() => done(keys.filter(k => (global.SEAFOLK_STORM || {})[k])));
}

/* What a reader sees when the clip does not arrive: the figure keeps its place
 * and says so, rather than leaving a captioned empty box. */
function unavailable(host, key) {
  host.innerHTML = "";
  el("p", "source", host).textContent = `The animation could not be loaded — open site/media/storm-${key}.mp4`;
}

global.SeafolkStorm = { mount, load, triptych, unavailable };
})(window);
