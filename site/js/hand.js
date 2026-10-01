/* Seafolk — the author's hand (round 4).
 *
 * Every figure on the page is something a person drew over print: a ballpoint
 * line with a tremor, pencil hatching, tally strokes, a quick sketch of a
 * boat, a note in handwriting. rough.js (jsDelivr) does the tremor; this file
 * decides what a hand would draw and in which ink. Seeded, so a figure is the
 * same drawing on every load and in every screenshot.
 *
 *   const h = hand(svgOrG);          // one per figure
 *   h.line([[x, y], …], "pen")       // ink: pen | redpen | graphite | greenpen
 *   h.text(x, y, "note", { ink, size, anchor, rot })
 *   h.tally(x, y, n, { ink, h })     // returns the x where the strokes end
 *   h.boat(x, y, s, { ink, sail })   // a sketch, not an icon
 *
 * Plain script, not a module: the page opens from file://.
 */
(function () {
"use strict";
const NS = "http://www.w3.org/2000/svg";
const css = name => getComputedStyle(document.documentElement).getPropertyValue("--" + name).trim();
const INKS = ["pen", "redpen", "graphite", "greenpen", "ink", "label"];

window.hand = function (node, seed) {
  const svg = node.ownerSVGElement || node;
  const rc = rough.svg(svg);
  let s = seed || 7;
  const rnd = () => (s = (s * 16807) % 2147483647) / 2147483647;
  const j = a => (rnd() - .5) * a;
  const ink = name => INKS.includes(name) ? css(name) : (name || css("pen"));
  const put = el => (node.appendChild(el), el);
  const opts = (o, extra) => Object.assign({
    stroke: ink(o.ink), strokeWidth: o.w || 1.5, roughness: o.rough ?? .7,
    bowing: o.bow ?? .8, seed: Math.floor(rnd() * 1e6) + 1,
  }, extra);

  const h = {
    rnd, j, ink,
    /* a pen line through the points */
    line(points, o = {}) {
      if (typeof o === "string") o = { ink: o };
      return put(rc.linearPath(points, opts(o)));
    },
    /* a smooth pen curve — for a series of a few hundred points */
    curve(points, o = {}) {
      if (typeof o === "string") o = { ink: o };
      return put(rc.curve(points, opts(o, { roughness: o.rough ?? .35, bowing: 0 })));
    },
    /* a ruled line: still a hand, but steadier */
    rule(x1, y1, x2, y2, o = {}) {
      return put(rc.line(x1, y1, x2, y2, opts(o, { roughness: o.rough ?? .35, bowing: .3 })));
    },
    /* a box filled with pencil hatching */
    shade(x, y, w, ht, o = {}) {
      return put(rc.rectangle(x, y, w, ht, opts(o, {
        stroke: o.edge === false ? "none" : ink(o.ink),
        fill: ink(o.fill || o.ink), fillStyle: o.style || "hachure",
        hachureGap: o.gap || 4, hachureAngle: o.angle ?? -41, fillWeight: o.fw || 1,
      })));
    },
    circle(cx, cy, d, o = {}) {
      return put(rc.circle(cx, cy, d, opts(o, o.fill ? {
        fill: ink(o.fill), fillStyle: o.style || "hachure", hachureGap: o.gap || 3,
      } : {})));
    },
    path(d, o = {}) { return put(rc.path(d, opts(o))); },
    /* handwriting */
    text(x, y, t, o = {}) {
      const e = document.createElementNS(NS, "text");
      e.setAttribute("x", x); e.setAttribute("y", y);
      e.setAttribute("fill", ink(o.ink));
      e.setAttribute("font-family", o.print ? css("serif") : css("hand"));
      e.setAttribute("font-size", o.size || 21);
      if (o.italic) e.setAttribute("font-style", "italic");
      if (o.anchor) e.setAttribute("text-anchor", o.anchor);
      if (o.base) e.setAttribute("dominant-baseline", o.base);
      const rot = o.rot ?? j(2);
      e.setAttribute("transform", `rotate(${rot.toFixed(2)} ${x} ${y})`);
      String(t).split("\n").forEach((line, i) => {
        const ts = e.appendChild(document.createElementNS(NS, "tspan"));
        ts.setAttribute("x", x); if (i) ts.setAttribute("dy", "1.05em");
        ts.textContent = line;
      });
      return put(e);
    },
    /* tally strokes, four and a slash, bundles spaced apart */
    tally(x, y, n, o = {}) {
      const ht = o.h || 26, gap = o.gap || 6.5, bundle = o.bundle || 14, w = o.w || 1.6;
      let cx = x;
      for (let i = 0; i < n; i++) {
        if (i % 5 < 4) {
          put(rc.line(cx + j(1.5), y + j(2), cx + j(2.5), y - ht + j(2.5), opts(o, { strokeWidth: w, roughness: .8, bowing: 1.1 })));
          cx += gap;
        } else {
          put(rc.line(cx - gap * 4 - 3 + j(2), y - ht * .22 + j(3), cx + 2 + j(2), y - ht * .8 + j(3), opts(o, { strokeWidth: w, roughness: .8 })));
          cx += bundle;
        }
      }
      return cx;
    },
    /* a boat sketched in three strokes; sail: true for a sailing boat */
    boat(x, y, sc, o = {}) {
      const k = sc || 1, q = (a, b) => [x + a * k + j(.6), y + b * k + j(.6)];
      const g = put(document.createElementNS(NS, "g"));
      const sub = window.hand(g, Math.floor(rnd() * 1e6) + 1);
      const w = o.w || Math.max(1, 1.3 * k);
      if (o.sail) {
        sub.line([q(-9, 0), q(9, 0), q(6, 4), q(-6, 4), q(-9, 0)], { ink: o.ink, w, rough: .6 });
        sub.line([q(0, 0), q(0, -17)], { ink: o.ink, w, rough: .4 });
        sub.line([q(0, -16), q(7, -2), q(0, -2)], { ink: o.ink, w, rough: .6 });
        if (o.jib !== false) sub.line([q(-1, -14), q(-7, -2), q(-1, -2)], { ink: o.ink, w, rough: .6 });
      } else if (o.kind === "fishing") {
        sub.line([q(-10, -3), q(10, -3), q(7, 3), q(-8, 3), q(-10, -3)], { ink: o.ink, w, rough: .6 });
        sub.line([q(-5, -3), q(-5, -9), q(1, -9), q(1, -3)], { ink: o.ink, w, rough: .5 });
        sub.line([q(5, -3), q(6, -16), q(11, -6)], { ink: o.ink, w, rough: .5 });
      } else {   // a ship: long hull, superstructure aft
        sub.line([q(-16, -3), q(14, -3), q(12, 3), q(-14, 3), q(-16, -3)], { ink: o.ink, w, rough: .6 });
        sub.line([q(-13, -3), q(-13, -10), q(-6, -10), q(-6, -3)], { ink: o.ink, w, rough: .5 });
        sub.line([q(-3, -3), q(-3, -7), q(10, -7), q(10, -3)], { ink: o.ink, w, rough: .5 });
      }
      return g;
    },
  };
  return h;
};
})();
