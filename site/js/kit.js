/* Seafolk — the shared chart kit.
 *
 * Seven helpers, and each one exists because at least two charts need it. It
 * is a plain script (not a module) because the pages must open by double-click
 * from file://, where a module import is blocked by CORS. D3 7 is loaded
 * ahead of it from a CDN and used as `d3`.
 *
 * WHAT IS DELIBERATELY NOT HERE: a chart class, a config object, a theme
 * manager, a legend. A chart on this site is a function that draws into a
 * group; the colours come from site.css through getComputedStyle, so a hue
 * lives in one file; and a series is labelled at its own end, never in a box
 * off to the side (docs/SITE.md § Chart rules).
 */
(function () {
"use strict";

const kit = window.kit = {};

/* The palette, read off the stylesheet at draw time so that light and dark
 * need no second set of literals anywhere. */
kit.ink = name => getComputedStyle(document.documentElement)
  .getPropertyValue("--" + name).trim();

/* A responsive SVG that redraws itself.
 *
 * `draw(g, w, h)` receives a <g> translated past the margins and the size of
 * the plot area inside them. It is called on first paint, on every resize of
 * the container, and whenever the colour scheme flips — which is what makes
 * the dark screenshots come out right without a second stylesheet.
 */
kit.figure = function (el, opts, draw) {
  const base = { top: 22, right: 18, bottom: 34, left: 46 };
  const svg = d3.select(el).append("svg");
  let last = 0;

  function render() {
    const outer = Math.max(el.clientWidth, 280);
    const narrow = outer < 560;
    // a phone has no room for a wide right-hand gutter of series labels, so a
    // chart that needs different margins there says so rather than shrinking
    // to fit and running its labels off the card.
    const m = Object.assign({}, base, opts.margin,
                            narrow ? opts.marginNarrow : null);
    const height = Math.round(outer * (narrow ? opts.ratioNarrow || opts.ratio : opts.ratio));
    const w = outer - m.left - m.right, h = height - m.top - m.bottom;
    svg.attr("viewBox", `0 0 ${outer} ${height}`)
       .attr("role", "img").selectAll("*").remove();
    draw(svg.append("g").attr("transform", `translate(${m.left},${m.top})`), w, h, narrow);
  }

  new ResizeObserver(() => {
    if (el.clientWidth !== last) { last = el.clientWidth; render(); }
  }).observe(el);
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", render);
  new MutationObserver(render).observe(document.documentElement,
    { attributes: true, attributeFilter: ["data-theme"] });
  render();
  return svg;
};

/* Plain axes: a line, at most five ticks, no box, no minor ticks.
 * `grid` draws the horizontal rules a reader actually uses to compare bars. */
kit.axis = function (g, scale, o) {
  const a = (o.side === "left" ? d3.axisLeft : d3.axisBottom)(scale)
    .tickSize(0).tickPadding(o.side === "left" ? 8 : 9);
  o.values ? a.tickValues(o.values) : a.ticks(o.ticks || 5);
  if (o.fmt) a.tickFormat(o.fmt);
  const sel = g.append("g")
    .attr("transform", o.side === "left" ? null : `translate(0,${o.at})`)
    .call(a);
  sel.select(".domain").attr("stroke", kit.ink("hairline"));
  sel.selectAll("text").attr("fill", kit.ink("label"))
    .style("font", '400 12px "IBM Plex Mono", ui-monospace, monospace');
  if (o.grid) {
    g.insert("g", ":first-child").selectAll("line")
      .data(o.values || scale.ticks(o.ticks || 5)).join("line")
      .attr("x1", 0).attr("x2", o.grid).attr("y1", scale).attr("y2", scale)
      .attr("stroke", kit.ink("hairline"));
  }
  if (o.title) {
    // the title of a bottom axis hangs off its right end, inside the plot —
    // reading the scale's own range rather than a caller-supplied width, which
    // is how it used to end up outside the figure when the caller forgot.
    g.append("text")
      .attr("x", o.side === "left" ? 0 : scale.range()[1])
      .attr("y", o.side === "left" ? -10 : o.at + 32)
      .attr("text-anchor", o.side === "left" ? "start" : "end")
      .attr("fill", kit.ink("label"))
      .style("font", 'italic 400 14px "Source Serif 4", Georgia, serif')
      .text(o.title);
  }
  return sel;
};

/* A halo in the figure's own background colour, so a label sitting on top of a
 * line stays readable without a box around it. Every piece of text drawn INSIDE
 * a plot goes through this. */
kit.halo = sel => sel.attr("stroke", kit.ink("surface")).attr("stroke-width", 4.5)
  .attr("stroke-linejoin", "round").attr("paint-order", "stroke");

/* Direct labels at the end of each line, nudged apart so none overlaps.
 * items: [{ y, text, color, weight }] — drawn at x, sorted top down. */
kit.endLabels = function (g, x, items, gap) {
  const s = items.slice().sort((a, b) => a.y - b.y);
  gap = gap || 16;
  for (let i = 1; i < s.length; i++) s[i].y = Math.max(s[i].y, s[i - 1].y + gap);
  kit.halo(g.selectAll(null).data(s).join("text")
    .attr("x", x + 7).attr("y", d => d.y).attr("dy", "0.34em")
    .attr("fill", d => d.color)
    .style("font", d => `${d.weight || 500} 14.5px "Source Serif 4", Georgia, serif`)
    .text(d => d.text));
};

/* The one annotation a chart is allowed: a short line of text, optionally on
 * a leader back to the point it is about. The leader is drawn first so the
 * text sits over it. */
kit.note = function (g, o) {
  const x = o.x + (o.dx || 0), y = o.y + (o.dy || 0);
  if (o.leader) {
    g.append("line")
      .attr("x1", o.x).attr("y1", o.y)
      .attr("x2", x + (o.anchor === "end" ? 5 : -5)).attr("y2", y - 4)
      .attr("stroke", o.color || kit.ink("ref")).attr("stroke-width", 1);
  }
  const t = g.append("text").attr("x", x).attr("y", y)
    .attr("text-anchor", o.anchor || "start")
    .attr("fill", o.color || kit.ink("label"))
    .style("font", `italic 400 ${(o.size || 13) + 1.5}px "Source Serif 4", Georgia, serif`);
  (Array.isArray(o.text) ? o.text : [o.text]).forEach((line, i) =>
    t.append("tspan").attr("x", x).attr("dy", i ? "1.25em" : 0).text(line));
  return kit.halo(t);
};

/* Hover: one readout for the whole page, and a dot on the value it is about.
 * `find(px, py)` returns { text, x, y } for the nearest datum, or null. */
kit.hover = function (g, w, h, find) {
  const tip = document.querySelector(".tip")
    || document.body.appendChild(Object.assign(document.createElement("div"),
                                               { className: "tip" }));
  const dot = g.append("circle").attr("r", 4).attr("fill", "none")
    .attr("stroke-width", 2).style("pointer-events", "none");
  g.append("rect").attr("width", w).attr("height", h).attr("fill", "transparent")
    .on("pointermove", function (e) {
      const [px, py] = d3.pointer(e, this), hit = find(px, py);
      if (!hit) { tip.removeAttribute("data-on"); dot.attr("fill", "none"); return; }
      tip.textContent = hit.text;
      tip.dataset.on = "";
      tip.style.left = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8) + "px";
      tip.style.top = (e.clientY - tip.offsetHeight - 12) + "px";
      dot.attr("cx", hit.x).attr("cy", hit.y)
         .attr("fill", kit.ink("surface")).attr("stroke", hit.color || kit.ink("ink"));
    })
    .on("pointerleave", () => { tip.removeAttribute("data-on"); dot.attr("fill", "none"); });
};

/* The table under every chart: the same numbers, for a screen reader, for
 * someone checking, and for a page with no JavaScript at all. */
kit.table = function (el, head, rows) {
  const esc = v => String(v).replace(/&/g, "&amp;").replace(/</g, "&lt;");
  el.innerHTML =
    "<thead><tr>" + head.map(h => `<th>${esc(h)}</th>`).join("") + "</tr></thead><tbody>" +
    rows.map(r => "<tr>" + r.map((c, i) =>
      i ? `<td>${esc(c)}</td>` : `<th>${esc(c)}</th>`).join("") + "</tr>").join("") +
    "</tbody>";
};

/* ?only=<figure id> shows that figure and nothing else, and ?theme=dark forces
 * the dark palette. Both exist for scripts/shot.sh: the headless shell can
 * screenshot a page but not crop to an element, and its dark-mode flag repaints
 * the page instead of asking the stylesheet for its dark tokens. */
const q = new URLSearchParams(location.search);
// An unknown theme is ignored rather than written through: ?theme=drak used to
// set data-theme="drak", which matches no rule in site.css and silently gives
// the light palette under a dark-looking file name.
const theme = q.get("theme");
if (theme === "light" || theme === "dark") {
  document.documentElement.dataset.theme = theme;
} else if (theme) {
  console.error(`kit: unknown ?theme=${theme} — light or dark`);
}
// …and an unknown figure id leaves the page alone. Hiding everything and then
// failing to un-hide the figure is a blank PNG, which scripts/shot.sh happily
// wrote and returned 0 for.
const only = q.get("only");
if (only) {
  const fig = document.getElementById(only);
  if (fig) {
    document.body.classList.add("only");
    fig.classList.add("shot");
  } else {
    console.error(`kit: no figure #${only} on this page`);
  }
}
})();
