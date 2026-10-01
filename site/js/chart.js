/* Seafolk — a map sheet: the image scripts/chartkit.py drew, and the vector
 * parts of a nautical chart on top of it.
 *
 *   chart.sheet(el, "i3-cargo", { names: ["Kattegat", "Skagen"], tag: "July 2025" })
 *
 * The image carries the sea, the depths, the land and the data. This adds what
 * must stay sharp and stay in the site's fonts at any width: the neatline with
 * its alternating minute bar, degree labels, water names in italic, place
 * names with a dot, a scale bar in nautical miles, and a corner tag.
 *
 * The projection is a straight line in each axis (see chartkit.py), so a
 * lon/lat becomes a percentage of the sheet with two subtractions. Plain
 * script, not a module: the pages open from file://.
 */
(function () {
"use strict";
const chart = window.chart = {};

/* Everything a sheet may name. Water in italic, as charts letter it; places in
 * spaced capitals with a dot. `big` is the size of a sea, not of a strait.
 * `left` puts a place's label to the left of its dot. */
const NAMES = {
  "Skagerrak":   { lon: 9.3,   lat: 57.8, kind: "water", big: 1 },
  "Kattegat":    { lon: 11.45, lat: 56.75, kind: "water", big: 1 },
  "Nordsøen":    { lon: 8.4,   lat: 56.45,  kind: "water", big: 1 },
  "Østersøen":   { lon: 14.1,  lat: 54.72, kind: "water", big: 1 },
  "Storebælt":   { lon: 11.02, lat: 55.5,  kind: "water", rot: -72 },
  "Lillebælt":   { lon: 9.78,  lat: 55.33, kind: "water", rot: -62 },
  "Øresund":     { lon: 12.72, lat: 55.93, kind: "water", rot: -64 },
  "Femern Bælt": { lon: 11.3,  lat: 54.6,  kind: "water" },
  "Limfjorden":  { lon: 9.0,   lat: 56.93, kind: "water" },
  "Skagen":      { lon: 10.59, lat: 57.72, kind: "place" },
  "Hirtshals":   { lon: 9.96,  lat: 57.59, kind: "place", left: 1 },
  "Hanstholm":   { lon: 8.6,   lat: 57.12, kind: "place", left: 1 },
  "Thyborøn":    { lon: 8.22,  lat: 56.7,  kind: "place", left: 1 },
  "Hvide Sande": { lon: 8.13,  lat: 56.0,  kind: "place", left: 1 },
  "Esbjerg":     { lon: 8.45,  lat: 55.47, kind: "place" },
  "Frederikshavn": { lon: 10.54, lat: 57.44, kind: "place" },
  "Aarhus":      { lon: 10.21, lat: 56.15, kind: "place" },
  "Odense":      { lon: 10.39, lat: 55.4,  kind: "place" },
  "København":   { lon: 12.57, lat: 55.68, kind: "place" },
  "Helsingør":   { lon: 12.61, lat: 56.04, kind: "place" },
  "Göteborg":    { lon: 11.97, lat: 57.71, kind: "place" },
  "Kiel":        { lon: 10.14, lat: 54.32, kind: "place", left: 1 },
  "Rødby":       { lon: 11.35, lat: 54.65, kind: "place" },
  "Rønne":       { lon: 14.69, lat: 55.1,  kind: "place" },
  "Anholt":      { lon: 11.55, lat: 56.7,  kind: "place" },
  "Læsø":        { lon: 11.0,  lat: 57.27, kind: "place" },
  "Samsø":       { lon: 10.6,  lat: 55.87, kind: "place" },
  "Ærø":         { lon: 10.38, lat: 54.87, kind: "place" },
};
chart.NAMES = NAMES;

const pct = (v, a, b) => (100 * (v - a) / (b - a)).toFixed(3) + "%";

/* Pixel [x, y] of a lon/lat on a w x h sheet of box [lon0, lon1, lat0, lat1],
 * y down. The same two lines are project() in scripts/chartkit.py;
 * scripts/test_charts.py holds both to known places. */
chart.project = (box, w, h, lon, lat) =>
  [(lon - box[0]) / (box[1] - box[0]) * w, (box[3] - lat) / (box[3] - box[2]) * h];

chart.sheet = function (el, id, o) {
  o = o || {};
  const m = (window.SEAFOLK_CHARTS || {})[id];
  const box = el.appendChild(document.createElement("div"));
  box.className = "sheet";
  if (!m) {
    box.innerHTML = `<p class="source">This map (${id}) did not load. Its image is built by scripts/charts_*.py.</p>`;
    console.error(`chart: no sheet "${id}" in window.SEAFOLK_CHARTS`);
    return null;
  }
  const [x0, x1, y0, y1] = m.box;
  const at = (lon, lat) => {
    const [x, y] = chart.project(m.box, 100, 100, lon, lat);
    return { left: x.toFixed(3) + "%", top: y.toFixed(3) + "%" };
  };
  const img = box.appendChild(new Image());
  img.src = m.src; img.alt = o.alt || ""; img.width = m.w; img.height = m.h;
  img.loading = o.eager ? "eager" : "lazy"; img.decoding = "async";

  // The neatline: a double rule, and on the inner one a bar that alternates
  // ink and paper every ten minutes of arc, the way a chart's border does.
  const ns = "http://www.w3.org/2000/svg";
  const svg = box.appendChild(document.createElementNS(ns, "svg"));
  svg.setAttribute("class", "frame");
  svg.setAttribute("viewBox", `0 0 ${m.w} ${m.h}`);
  svg.setAttribute("preserveAspectRatio", "none");
  const line = (x1_, y1_, x2_, y2_, w, c) => {
    const l = svg.appendChild(document.createElementNS(ns, "line"));
    Object.entries({ x1: x1_, y1: y1_, x2: x2_, y2: y2_, stroke: c || "var(--ink)",
      "stroke-width": w, "vector-effect": "non-scaling-stroke" })
      .forEach(([k, v]) => l.setAttribute(k, v));
  };
  const X = lon => chart.project(m.box, m.w, m.h, lon, y0)[0];
  const Y = lat => chart.project(m.box, m.w, m.h, x0, lat)[1];
  if (o.ticks !== false) {
    const step = 1 / 6;
    for (let lon = Math.ceil(x0 / step) * step, k = 0; lon < x1; lon += step, k++) {
      if (k % 2) continue;
      const a = X(lon), b = X(Math.min(lon + step, x1));
      line(a, 0, b, 0, 5); line(a, m.h, b, m.h, 5);
    }
    for (let lat = Math.ceil(y0 / step) * step, k = 0; lat < y1; lat += step, k++) {
      if (k % 2) continue;
      const a = Y(lat), b = Y(Math.min(lat + step, y1));
      line(0, a, 0, b, 5); line(m.w, a, m.w, b, 5);
    }
    for (let lon = Math.ceil(x0); lon < x1; lon++) label(`${lon}°E`, "caps edge", { left: pct(lon, x0, x1), top: "calc(100% - 12px)" });
    for (let lat = Math.ceil(y0); lat < y1; lat++) label(`${lat}°N`, "caps edge", { left: "22px", top: pct(y1 - lat + y0, y0, y1) });
  }
  line(0, 0, m.w, 0, 1); line(0, m.h, m.w, m.h, 1); line(0, 0, 0, m.h, 1); line(m.w, 0, m.w, m.h, 1);

  function label(text, cls, pos, rot) {
    const s = box.appendChild(document.createElement("span"));
    s.className = "lbl " + cls;
    s.textContent = text;
    Object.assign(s.style, pos);
    if (rot) s.style.transform = `translate(-50%, -50%) rotate(${rot}deg)`;
    return s;
  }
  // a name is a key of NAMES, or a page's own {name, lon, lat, kind, big, left, rot}
  (o.names || []).forEach(n => {
    const d = typeof n === "string" ? NAMES[n] : n;
    if (typeof n !== "string") n = n.name;
    if (!d) { console.error(`chart: no name "${n}"`); return; }
    if (d.lon < x0 || d.lon > x1 || d.lat < y0 || d.lat > y1) return;
    const cls = d.kind === "water" ? "water" + (d.big ? " big" : "") : "place" + (d.left ? " left" : "");
    label(d.kind === "water" && d.big ? n.toUpperCase() : n, cls, at(d.lon, d.lat), d.rot);
  });

  // Scale bar: 0 · 20 · 40 nautical miles at the sheet's middle latitude.
  if (o.scale !== false) {
    const nm = o.scaleNm || 40;
    const kmPerDegLon = 111.2 * Math.cos((y0 + y1) / 2 * Math.PI / 180);
    const w = 100 * nm * 1.852 / kmPerDegLon / (x1 - x0);
    const s = box.appendChild(document.createElement("div"));
    s.className = "lbl scalebar";
    Object.assign(s.style, { left: "3%", top: "auto", bottom: "4.5%", transform: "none", width: w + "%" });
    s.innerHTML = `<span></span><span></span><em>${nm} nautical miles</em>`;
  }
  // Notes in the author's hand: { text, at: [lon, lat] where the writing
  // starts, to: [lon, lat] what it points at, ink: "red"|"grey"|"green",
  // rot: degrees }. The leader is drawn by hand too (rough.js when the page
  // loads it), in the sheet's own pixel space so it scales with the image.
  (o.notes || []).forEach((n, i) => {
    const t = box.appendChild(document.createElement("div"));
    t.className = "note" + (n.ink ? " " + n.ink : "");
    t.textContent = n.text;
    const p = at(...n.at);
    Object.assign(t.style, { left: p.left, top: p.top });
    if (n.rot != null) t.style.setProperty("--rot", n.rot + "deg");
    if (n.anchor === "end") t.style.translate = "-100% 0";
    if (!n.to) return;
    let lead = box.querySelector("svg.leaders");
    if (!lead) {
      lead = box.appendChild(document.createElementNS(ns, "svg"));
      lead.setAttribute("class", "leaders");
      lead.setAttribute("viewBox", `0 0 ${m.w} ${m.h}`);
      lead.setAttribute("preserveAspectRatio", "none");
    }
    const [ax, ay] = chart.project(m.box, m.w, m.h, ...(n.from || n.at));
    const [bx, by] = chart.project(m.box, m.w, m.h, ...n.to);
    const mx = (ax + bx) / 2 + (by - ay) * .18, my = (ay + by) / 2 - (bx - ax) * .18;
    const ink = getComputedStyle(document.documentElement)
      .getPropertyValue(n.ink === "red" ? "--redpen" : n.ink === "grey" ? "--graphite"
                        : n.ink === "green" ? "--greenpen" : "--pen").trim();
    const d = `M ${ax} ${ay} Q ${mx} ${my} ${bx} ${by}`;
    const ang = Math.atan2(by - my, bx - mx), hl = m.w / 90;
    const head = `M ${bx - hl * Math.cos(ang - .45)} ${by - hl * Math.sin(ang - .45)} L ${bx} ${by} ` +
                 `L ${bx - hl * Math.cos(ang + .45)} ${by - hl * Math.sin(ang + .45)}`;
    const w = Math.max(1.4, m.w / 900);
    if (window.rough) {
      const rc = rough.svg(lead);
      const opt = { stroke: ink, strokeWidth: w, roughness: .9, bowing: 1.5, seed: 11 + i };
      lead.appendChild(rc.path(d, opt));
      lead.appendChild(rc.path(head, { ...opt, bowing: .5 }));
    } else {
      [d, head].forEach(pd => {
        const p2 = lead.appendChild(document.createElementNS(ns, "path"));
        Object.entries({ d: pd, fill: "none", stroke: ink, "stroke-width": w, "stroke-linecap": "round" })
          .forEach(([k, v]) => p2.setAttribute(k, v));
      });
    }
  });

  if (o.tag) {
    const t = label(o.tag, "tag", { left: "auto", right: "2.2%", top: "3.2%" });
    t.style.transform = "none";
  }
  return { box, img, meta: m, at, xy: (lon, lat) => chart.project(m.box, m.w, m.h, lon, lat) };
};
})();
