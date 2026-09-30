/* Seafolk — the three figures on "How it was made", drawn in chart language.
 *
 *   H1  the >= 5 rule: one real chart sheet twice, "heard on the radio" and
 *       "published". Invented boats in invented patches (scripts/charts_how.py
 *       places them over water); a patch with five or more gets dots and its
 *       count on the published sheet, a patch with fewer stays blank.
 *   H2  what the rule costs: two blocks of a hundred marks, patches and boats.
 *   H3  the pipeline as a harbour plan: the archive as a stretch of sea, files
 *       at anchor while they download, one lock, counts left on the quay.
 *       The three squares are drawn to one scale of area.
 *
 * Numbers come from the page's <script type="application/json" id="data">,
 * written by scripts/site_data/how.py; the H1 sheet and its candidate positions
 * from site/media/charts/how.js. No colour literal: kit.ink reads site.css.
 */
(function () {
"use strict";

const D = JSON.parse(document.getElementById("data").textContent);
const ink = kit.ink;
const SERIF = '"Source Serif 4", Georgia, serif';
const MONO = '"IBM Plex Mono", ui-monospace, monospace';

/* A sailing boat seen from the side, about 12 units tall, standing on (0, 0). */
const BOAT = "M0.4,-10.5 L0.4,-2.2 L-5.2,-2.2 Z M1.4,-8.6 L1.4,-2.2 L4.8,-2.2 Z " +
             "M-6,-1 L6,-1 L4,2 L-4,2 Z";
/* A ship seen from above, bow to the right, about 16 units long. */
const HULL = "M-8,-2.8 L2.5,-2.8 L9,0 L2.5,2.8 L-8,2.8 Z";

/* text with a halo in the sheet's colour, the way kit.halo does it */
function say(g, x, y, text, font, colour, anchor) {
  return kit.halo(g.append("text").attr("x", x).attr("y", y)
    .attr("text-anchor", anchor || "start").attr("fill", colour || ink("ink"))
    .style("font", font).text(text));
}


/* ================= H1 — the rule, drawn on a chart ======================= */
function rule() {
  const M = (window.SEAFOLK_CHARTS || {})["how-h1"];
  const P = D.picture;
  const el = document.getElementById("c-h1");
  const row = el.appendChild(document.createElement("div"));
  row.className = "sheets";
  if (!M) { chart.sheet(row, "how-h1"); return; }       // prints the "did not load" note

  const [x0, x1] = M.box;
  const kmPerPx = 111.2 * Math.cos(56 * Math.PI / 180) * (x1 - x0) / M.w;
  const R = M.patch_km / kmPerPx;                          // a patch's radius in image pixels

  [["heard", "Heard on the radio"], ["published", "Published"]].forEach(([side, tag]) => {
    const s = chart.sheet(row.appendChild(document.createElement("div")), "how-h1", {
      tag, scaleNm: 10, eager: true,
      names: ["Ærø", { name: "Lillebælt", lon: 9.69, lat: 55.29, kind: "water", rot: -62 }],
      alt: side === "heard"
        ? "A chart of the South Funen islands with seven dashed patches of sea, each holding a few drawn boats"
        : "The same chart with only the patches of five or more boats filled with dots and a count; the rest is blank" });
    if (!s) return;
    const svg = d3.select(s.box).insert("svg", "svg.frame").attr("class", "marks")
      .attr("viewBox", `0 0 ${M.w} ${M.h}`);
    let last = 0;

    function draw() {
      const k = s.box.clientWidth / M.w;         // screen pixels per image pixel
      if (!k || k === last) return;
      last = k;
      svg.selectAll("*").remove();
      const px = v => v / k;                       // a size in screen pixels, in image units
      M.patches.forEach((p, i) => {
        const n = P.counts[i], kept = n >= P.floor, short = n === P.floor - 1;
        const [cx, cy] = s.xy(p.lon, p.lat);
        const g = svg.append("g");
        if (side === "heard") {
          g.append("circle").attr("cx", cx).attr("cy", cy).attr("r", R)
            .attr("fill", ink("surface")).attr("fill-opacity", .55)
            .attr("stroke", ink("ink")).attr("stroke-width", px(1.1))
            .attr("stroke-dasharray", `${px(4)} ${px(3)}`);
          const size = Math.min(px(11), R * .3) / 12;
          p.pts.slice(0, n).forEach(([lon, lat]) => {
            const [x, y] = s.xy(lon, lat);
            g.append("path").attr("d", BOAT).attr("fill", ink("ink"))
              .attr("transform", `translate(${x},${y + 4 * size}) scale(${size})`);
          });
          // a phone-width sheet has room for the number, not the word
          const word = s.box.clientWidth < 420 ? "" : n === 1 ? " boat" : " boats";
          // the one-short label is the longest; it hangs to the left, clear of its neighbour
          say(g, short ? cx + R * .5 : cx, cy - R - px(7), `${n}${word}${short ? " · one short" : ""}`,
              `${kept ? 600 : 400} ${px(12)}px ${MONO}`,
              ink(kept ? "accent-tx" : short ? "ferry" : "label"), short ? "end" : "middle");
        } else if (kept) {
          p.dots.slice(0, Math.min(p.dots.length, n * 5)).forEach(([lon, lat]) => {
            const [x, y] = s.xy(lon, lat);
            g.append("circle").attr("cx", x).attr("cy", y).attr("r", px(1.7))
              .attr("fill", ink("accent")).attr("fill-opacity", .85);
          });
          say(g, cx, cy + px(9), n, `italic 600 ${px(26)}px ${SERIF}`, ink("accent-tx"), "middle");
        } else if (short) {
          g.append("circle").attr("cx", cx).attr("cy", cy).attr("r", R)
            .attr("fill", "none").attr("stroke", ink("ref")).attr("stroke-width", px(1))
            .attr("stroke-dasharray", `${px(1.5)} ${px(3)}`);
          say(g, cx, cy + px(5), "blank", `italic 400 ${px(14)}px ${SERIF}`, ink("label"), "middle");
        }
      });
    }
    new ResizeObserver(draw).observe(s.box);
    draw();
  });
}


/* ================= H2 — what the rule costs ============================= */
function cost() {
  const F = D.floor;
  const blocks = [
    { title: "patches of sea kept", value: Math.round(F.cells_pct), mark: "patch" },
    { title: "boat movement kept", value: Math.round(F.moving_pct), mark: "boat" }];

  kit.figure(document.getElementById("c-h2"),
    { ratio: 0.5, ratioNarrow: 1.95, margin: { top: 6, right: 4, bottom: 6, left: 4 } },
    (g, w, h, narrow) => {
      const head = 78;                                  // the title and the big number
      const gap = narrow ? 34 : 40;
      const bw = narrow ? w : (w - gap) / 2;
      const side = Math.min(bw / 10, ((narrow ? (h - gap) / 2 : h) - head) / 10);

      blocks.forEach((b, bi) => {
        const bx = narrow ? 0 : bi * (bw + gap);
        const by = narrow ? bi * ((h - gap) / 2 + gap) : 0;
        const blk = g.append("g").attr("transform", `translate(${bx},${by})`);
        blk.append("text").attr("y", 12).attr("fill", ink("label"))
          .style("font", `500 11.5px ${MONO}`).style("letter-spacing", ".18em")
          .text(b.title.toUpperCase());
        const big = blk.append("text").attr("y", 60).attr("fill", ink(bi ? "accent-tx" : "ink"))
          .style("font", `italic 600 46px ${SERIF}`).text(b.value);
        big.append("tspan").attr("dx", 8).attr("fill", ink("label"))
          .style("font", `italic 400 16px ${SERIF}`).text("of every hundred");

        const grid = blk.append("g").attr("transform", `translate(0,${head})`);
        const rnd = d3.randomLcg(5);
        d3.range(100).forEach(i => {
          const on = i < b.value;
          const x = (i % 10 + .5) * side, y = (Math.floor(i / 10) + .5) * side;
          if (b.mark === "patch") {
            // a published patch is drawn as the maps draw one: a stipple of dots
            // at random inside it; a dropped one is an empty dashed ring
            grid.append("circle").attr("cx", x).attr("cy", y).attr("r", side * .36)
              .attr("fill", "none").attr("stroke", on ? ink("accent") : ink("ref"))
              .attr("stroke-width", on ? .8 : 1).attr("stroke-dasharray", on ? null : "2.5 2.5")
              .attr("stroke-opacity", on ? .5 : 1);
            if (on) d3.range(11).forEach(() => {
              const a = rnd() * 2 * Math.PI, d = side * .3 * Math.sqrt(rnd());
              grid.append("circle").attr("cx", x + Math.cos(a) * d).attr("cy", y + Math.sin(a) * d)
                .attr("r", Math.max(1.2, side * .045)).attr("fill", ink("accent"));
            });
          } else {
            grid.append("path").attr("d", BOAT)
              .attr("transform", `translate(${x},${y + side * .3}) scale(${side / 17})`)
              .attr("fill", on ? ink("accent") : "none")
              .attr("stroke", on ? "none" : ink("ref")).attr("stroke-width", 17 / side);
          }
        });
      });
    });

  kit.table(document.getElementById("t-h2"),
    ["counted as", "published", "dropped by the rule"],
    [["patches of sea", F.cells_pct + " %", (100 - F.cells_pct).toFixed(1) + " %"],
     ["boat movement", F.moving_pct + " %", (100 - F.moving_pct).toFixed(1) + " %"]]);
}


/* ================= H3 — the pipeline as a harbour plan ================== */
function harbour() {
  const n = D.n;
  const offered = parseFloat(n.archive_tb), pulled = parseFloat(n.pulled_tb);
  const kept = parseFloat(n.store_gb) / 1000;           // TB, for the areas
  const files = D.pipe.files, ahead = +n.ahead;

  // Two plans in design units, scaled to the width they are given, so the
  // drawing keeps its proportions and its type sizes relative to each other.
  //   at      the archive square's top-left     under   its caption
  //   anchor  the anchorage (x, y, r)            lock    the channel through it
  //   quay    the land: a polygon                store   the counts, on the quay
  //   gone    where the file is deleted          loop    the way back for the next one
  const WIDE = {
    W: 1000, H: 470, sq: 250, at: [18, 96], under: [18, 394, "start"],
    anchor: [460, 250, 58], anchorLabel: [[460, 172, "middle"], [460, 338, "middle"]],
    lock: { x0: 566, x1: 736, y: 250, horizontal: true }, lockLabel: [651, 124, "middle"],
    mole: [566, 206, 170, 31],
    quay: [[566, 470], [566, 263], [760, 263], [760, 336], [1000, 336], [1000, 470]], coast: 5,
    spoil: [796, 214, 92, 96], spoilLabel: [842, 204, "middle"],
    store: [640, 336], storeLabel: [672, 356],
    gone: [842, 250], goneLabel: [842, 292, "middle"],
    loop: [[888, 250], [944, 250], [944, 58], [300, 58], [300, 118], [272, 118]],
    loopLabel: [[622, 46, "middle"]],
  };
  const NARROW = {
    W: 340, H: 830, sq: 200, at: [50, 40], under: [150, 284, "middle"],
    anchor: [150, 404, 50], anchorLabel: [[210, 384, "start"], [210, 406, "start"], [210, 426, "start"]],
    lock: { x0: 490, x1: 610, y: 150, horizontal: false }, lockLabel: [204, 506, "start"],
    mole: [163, 490, 30, 120],
    quay: [[0, 490], [137, 490], [137, 830], [0, 830]], coast: 3,
    spoil: [139, 634, 22, 80], spoilLabel: [172, 664, "start"],
    store: [40, 596], storeLabel: [10, 650],
    gone: [150, 674], goneLabel: [172, 686, "start"],
    loop: [[150, 714], [150, 766], [328, 766], [328, 150], [256, 150]],
    loopLabel: [[238, 794, "middle"], [238, 814, "middle"]],
  };

  kit.figure(document.getElementById("c-h3"),
    { ratio: WIDE.H / WIDE.W, ratioNarrow: NARROW.H / NARROW.W,
      margin: { top: 0, right: 0, bottom: 0, left: 0 } },
    (root, w, h, narrow) => {
      const L = narrow ? NARROW : WIDE, lk = L.lock;
      const g = root.append("g").attr("transform", `scale(${w / L.W})`);
      const red = ink("ferry"), sea = ink("sea-ink"), coast = ink("label");
      const line = (pts, colour, width, dash) => g.append("path").attr("d", d3.line()(pts))
        .attr("fill", "none").attr("stroke", colour).attr("stroke-width", width)
        .attr("stroke-dasharray", dash || null);
      const arrow = (x, y, ang, colour) => g.append("path")
        .attr("d", "M-8,-5 L1,0 L-8,5").attr("fill", "none")
        .attr("stroke", colour || red).attr("stroke-width", 1.7)
        .attr("transform", `translate(${x},${y}) rotate(${ang})`);
      // a recommended track, as a chart draws one: a line with an arrowhead mid-way
      const track = (a, b) => {
        line([a, b], red, 1.7);
        arrow((a[0] + b[0]) / 2 + 4 * Math.sign(b[0] - a[0]), (a[1] + b[1]) / 2 + 4 * Math.sign(b[1] - a[1]),
              Math.atan2(b[1] - a[1], b[0] - a[0]) * 180 / Math.PI);
      };
      const hull = (x, y, ang, ghost, k) => g.append("path").attr("d", HULL)
        .attr("transform", `translate(${x},${y}) rotate(${ang}) scale(${k || 1.55})`)
        .attr("fill", ghost ? "none" : ink("ink"))
        .attr("stroke", ghost ? red : ink("surface"))
        .attr("stroke-width", ghost ? .8 : .7).attr("stroke-dasharray", ghost ? "1.6 1.4" : null);
      // lines of type stacked downwards; spaced capitals get more room under them
      const words = (x, y, anchor, list) => list.forEach(([text, font, colour, caps]) => {
        const t = say(g, x, y, text, font, colour, anchor);
        if (caps) t.style("letter-spacing", ".16em");
        y += caps ? 24 : font.includes("34px") ? 26 : 20;
      });
      const CAPS = `500 11.5px ${MONO}`, IT = `italic 400 15px ${SERIF}`, TX = `400 15px ${SERIF}`;

      // --- the land: the quay, and the mole the lock is built against
      g.append("path").attr("d", d3.line()(L.quay) + "Z").attr("fill", ink("land")).attr("stroke", "none");
      line(L.quay.slice(0, L.coast), coast, 1);   // the coastline: the sides that face the water
      {
        const [x, y, mw, mh] = L.mole;
        g.append("rect").attr("x", x).attr("y", y).attr("width", mw).attr("height", mh)
          .attr("fill", ink("land")).attr("stroke", coast).attr("stroke-width", 1);
      }

      // --- the archive: all of it dashed, what was pulled as shallow water with
      // one dot per file; the store on the quay is drawn to the same scale.
      const [ax, ay] = L.at, side = L.sq, inner = side * Math.sqrt(pulled / offered);
      const ix = ax + side - inner, iy = ay + side - inner;
      g.append("rect").attr("x", ax).attr("y", ay).attr("width", side).attr("height", side)
        .attr("fill", "none").attr("stroke", ink("ink")).attr("stroke-width", 1).attr("stroke-dasharray", "6 4");
      say(g, ax + 10, ay + 22, `${n.archive_tb} TB on offer, 2014 onward`, `italic 400 14px ${SERIF}`, ink("label"));
      g.append("rect").attr("x", ix).attr("y", iy).attr("width", inner).attr("height", inner)
        .attr("fill", ink("shoal")).attr("stroke", sea).attr("stroke-width", 1);
      const rnd = d3.randomLcg(7);
      for (let i = 0; i < files; i++) {
        g.append("circle").attr("r", 1.2).attr("fill", ink("ink")).attr("fill-opacity", .72)
          .attr("cx", ix + 4 + rnd() * (inner - 8)).attr("cy", iy + 4 + rnd() * (inner - 8));
      }
      say(g, ax, ay - 16, "THE ARCHIVE · AISDATA.AIS.DK", CAPS, ink("label")).style("letter-spacing", ".16em");
      {
        const [x, y, anchor] = L.under;
        const t = say(g, x, y, `${n.pulled_tb} TB`, `italic 600 38px ${SERIF}`, ink("ink"), anchor);
        t.append("tspan").attr("dx", 8).style("font", IT).attr("fill", ink("label")).text("pulled down");
        say(g, x, y + 24, `${n.files} zip files, one dot each`, TX, ink("label"), anchor);
      }

      // --- the anchorage: files waiting while they download. Ships at anchor
      // all swing to the same wind, so they all point one way.
      const [cx, cy, r] = L.anchor;
      g.append("circle").attr("cx", cx).attr("cy", cy).attr("r", r).attr("fill", ink("shoal"))
        .attr("fill-opacity", .45).attr("stroke", sea).attr("stroke-width", 1.1).attr("stroke-dasharray", "8 3 1.5 3");
      g.append("path").attr("transform", `translate(${cx},${cy}) scale(1.2)`)
        .attr("d", "M0,-9 a2.2,2.2 0 1,1 0.01,0 M0,-6.8 L0,8 M-4.5,-3.5 L4.5,-3.5 M-7,2.5 Q-6,8 0,8 Q6,8 7,2.5")
        .attr("fill", "none").attr("stroke", sea).attr("stroke-width", 1.4).attr("stroke-linecap", "round");
      d3.range(ahead).forEach(i => {
        const a = -Math.PI / 2 + (i + .5) * 2 * Math.PI / ahead;
        hull(cx + Math.cos(a) * r * .66, cy + Math.sin(a) * r * .66, 205, false, 1.3);
      });
      {
        const [[x1, y1, a1], ...rest] = L.anchorLabel;
        say(g, x1, y1, "ANCHORAGE", CAPS, sea, a1).style("letter-spacing", ".16em");
        const txt = narrow ? [`${n.ahead} downloads`, "wait at anchor"] : [`${n.ahead} downloads wait at anchor`];
        txt.forEach((t, i) => say(g, rest[i][0], rest[i][1], t, IT, ink("ink"), rest[i][2]));
      }

      // --- the lock: one file at a time, gates shut at both ends
      const gap = 13, H = lk.horizontal;
      const P = (along, across) => H ? [along, lk.y + across] : [lk.y + across, along];
      track(H ? [cx + r, cy] : [cx, cy + r], P(lk.x0, 0));
      [lk.x0, lk.x1].forEach(e => line([P(e, -gap), P(e, gap)], ink("ink"), 3));
      hull(...P((lk.x0 + lk.x1) / 2, 0), H ? 0 : 90);
      {
        const [x, y, anchor] = L.lockLabel;
        const head = `600 19px ${SERIF}`;
        const it14 = `italic 400 14px ${SERIF}`, head17 = `600 17px ${SERIF}`;
        words(x, y, anchor, narrow
          ? [["THE LOCK", CAPS, ink("label"), 1], ["ClickHouse", head17, ink("ink")], ["on a Mac Mini", head17, ink("ink")],
             ["one file at a time,", it14, ink("ink")], [`${n.rate_million} million lines`, it14, ink("ink")], ["a second", it14, ink("ink")]]
          : [["THE LOCK · ONE FILE AT A TIME", CAPS, ink("label"), 1], ["ClickHouse on a Mac Mini", head, ink("ink")],
             [`${n.rate_million} million lines a second`, IT, ink("ink")]]);
      }

      // --- the counts go ashore, to the store: a small square on the quay
      const ss = side * Math.sqrt(kept / offered);
      const [sx, sy] = L.store;
      g.append("rect").attr("x", sx).attr("y", sy).attr("width", ss).attr("height", ss).attr("fill", ink("accent"));
      {
        const mid = (lk.x0 + lk.x1) / 2, to = [sx + ss / 2, sy - 3];
        const pts = H ? [P(mid - 20, gap + 3), [mid - 20, (lk.y + gap + to[1]) / 2], [to[0], (lk.y + gap + to[1]) / 2], to]
                      : [P(mid - 20, -gap - 3), [to[0], mid - 20], to];
        line(pts, ink("accent"), 1.4, "3 3");
        arrow(to[0], to[1], 90, ink("accent"));
        const [x, y] = L.storeLabel;
        words(x, y, "start", [[`${n.store_gb} GB`, `italic 600 34px ${SERIF}`, ink("accent-tx")],
          ["of counts, kept", TX, ink("ink")], [`${n.days} days of sea`, TX, ink("label")]]);
      }

      // --- out of the lock the file goes to the spoil ground — where a chart
      // marks the place dredged material is dumped — and is deleted there.
      {
        const [x, y, sw, sh] = L.spoil;
        g.append("rect").attr("x", x).attr("y", y).attr("width", sw).attr("height", sh)
          .attr("fill", "none").attr("stroke", red).attr("stroke-width", 1).attr("stroke-dasharray", "7 2 1.5 2");
        const [lx, ly, la] = L.spoilLabel;
        say(g, lx, ly, "SPOIL GROUND", `500 10.5px ${MONO}`, red, la).style("letter-spacing", ".14em");
      }
      track(P(lk.x1, 0), H ? [L.gone[0] - 16, lk.y] : [lk.y, L.gone[1] - 16]);
      hull(L.gone[0], L.gone[1], H ? 0 : 90, true);
      {
        const [x, y, anchor] = L.goneLabel;
        say(g, x, y, "zip deleted", `italic 600 16px ${SERIF}`, red, anchor);
      }
      line(L.loop, red, 1.4, "6 4");
      const [p, q] = L.loop.slice(-2);
      arrow(q[0], q[1], Math.atan2(q[1] - p[1], q[0] - p[0]) * 180 / Math.PI);
      const back = narrow ? ["the next file comes in", `${n.files} times`] : [`the next file comes in · ${n.files} times`];
      back.forEach((t, i) => say(g, L.loopLabel[i][0], L.loopLabel[i][1], t, IT, red, L.loopLabel[i][2]));

      // track from the archive to the anchorage, drawn last so it sits on top
      track(H ? [ix + inner, cy] : [ax + side / 2, L.under[1] + 34], H ? [cx - r, cy] : [cx, cy - r]);
    });

  kit.table(document.getElementById("t-h3"), ["what", "how much"],
    [["archive on offer, 2014 onward", n.archive_tb + " TB"],
     ["pulled down", n.pulled_tb + " TB"],
     ["archive files downloaded and deleted", n.files],
     ["downloads kept running ahead", n.ahead],
     ["lines of radio read", n.rows_billion + " billion"],
     ["lines kept after filtering", n.kept_billion + " billion"],
     ["days of sea", n.days],
     ["hexagons the store knows", D.pipe.cells],
     ["lines a second, a usual file", n.rate_million + " million"],
     ["database time, whole reload", n.load_hours + " hours"],
     ["wall clock, whole reload", n.reload_hours + " hours"],
     ["counts left on disk", n.store_gb + " GB"]]);
}


rule();
cost();
harbour();
})();
