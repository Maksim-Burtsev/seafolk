/* Static map figures — Canvas 2D, no dependencies, no h3 library.
 *
 * Embed (two lines, plus a container):
 *   <script src="media/land.js"></script><script src="media/maps.js"></script><script src="js/minimap.js"></script>
 *   <div id="m"></div><script>SeafolkMap.draw(document.getElementById('m'), {layer: 'fishing_2025'})</script>
 *
 * Two side by side, on one honest colour scale:
 *   <div id="p"></div><script>SeafolkMap.pair(document.getElementById('p'), [{layer:'small_july_2025'},{layer:'small_january_2025',scaleTo:'small_july_2025'}])</script>
 *
 * Plain <script> tags on purpose: the site has to open from file:// by
 * double-click, where fetch() and modules do not.
 *
 * draw(element, options) -> { redraw, destroy, element }
 *   layer     key in window.SEAFOLK_MAPS.layers  (required)
 *   title     the short label over the map; defaults to the layer's own
 *   colour    "accent" (the thing the figure is about) or "ink" (context)
 *   labels    place names, default true
 *   legend    the "few … many" strip, default true
 *   scaleTo   another layer key, or an array of them: the two maps then share
 *             one colour scale, so July-vs-January is a comparison and not two
 *             pictures each stretched to its own maximum.
 * pair(element, [a, b]) and triptych(element, [a, b, c]) lay maps out side by
 * side at 700 px and up, stacked below it, and give every map in the group the
 * group's shared scale unless the caller set one.
 *
 * The data is written by scripts/build_map_figures.py from dist/dataset only.
 * A cell carries a precomputed centre; the hexagon's radius and rotation come
 * once per resolution out of the same file, measured there from a real H3
 * boundary — which is why nothing here knows what H3 is.
 */
(function (global) {
  "use strict";

  var LIGHT = {
    ground: "#e9eeef", surface: "#f7f9f9", hairline: "#cfdadc",
    ink: "#0f1a1d", label: "#55676c", accent: "#eb6834", ref: "#a8b8bc"
  };
  var DARK = {
    ground: "#0b1416", surface: "#122023", hairline: "#23383c",
    ink: "#e8eeef", label: "#9db0b4", accent: "#f07a45", ref: "#47605f"
  };

  // 5–7 quiet places, enough to tell a reader which sea this is. The last
  // three drop out on a narrow map, where there is no room for seven.
  var PLACES = [
    ["Skagen", 57.724, 10.583], ["Aarhus", 56.157, 10.210],
    ["Copenhagen", 55.676, 12.568], ["Bornholm", 55.130, 14.920],
    ["Esbjerg", 55.467, 8.452], ["Kiel", 54.323, 10.139],
    ["Gothenburg", 57.708, 11.975]
  ];
  var FEW_PLACES = 4;

  var MAXH = 520;        // a figure in a column of prose, not a wall map
  var LEGEND_H = 30;
  // Colour buckets, one Path2D each. Fourteen and not nine: on a sqrt ramp
  // the first bucket covers everything below 1/STEPS^2 of the top — on the
  // fishing map that is nine cells in ten — and a coarse first bucket drew all
  // of them at a fifth of full strength, which washed the whole sea one colour
  // and hid the grounds the map is about.
  var STEPS = 14;
  var OVERDRAW = 1.05;   // close the seams a constant hexagon leaves behind
  var SIDE_BY_SIDE = 700;

  var CSS =
    // The site's own `figure` rule gives a figure a border, a background and
    // 28 px of padding, and clientWidth counts padding — so a map sized from
    // it overflowed its own box by exactly twice that. A map figure is not the
    // site's figure block; it is the picture inside one.
    ".sfm{display:block;margin:0;padding:0;border:0;background:none;gap:0;font:inherit;color:var(--ink,#0f1a1d)}" +
    ".sfm canvas{display:block;height:auto;border-radius:3px;margin:0 auto}" +
    ".sfm-cap{margin:0 0 .45em;font:500 13px/1.3 'IBM Plex Mono',ui-monospace,monospace;" +
    "letter-spacing:.06em;color:var(--label,#55676c);text-align:center;max-width:none}" +
    ".sfm-row{display:flex;gap:16px;align-items:flex-start}" +
    ".sfm-row>*{flex:1 1 0;min-width:0}" +
    ".sfm-col{flex-direction:column}" +
    ".sfm-col>*{width:100%}";

  function style() {
    if (document.getElementById("sfm-css")) return;
    var s = document.createElement("style");
    s.id = "sfm-css";
    s.textContent = CSS;
    document.head.appendChild(s);
  }

  function tokens(el) {
    var dark = document.documentElement.getAttribute("data-theme");
    dark = dark ? dark === "dark"
      : !!(global.matchMedia &&
           global.matchMedia("(prefers-color-scheme: dark)").matches);
    var base = dark ? DARK : LIGHT, cs = getComputedStyle(el), out = {};
    for (var k in base) {
      var v = cs.getPropertyValue("--" + k).trim();
      out[k] = hex(v) ? v : base[k];
    }
    out.dark = dark;
    // Sea and land, both derived so the figure follows the page's tokens.
    // The sea is the page's own surface pulled towards one water colour — the
    // only hue in this file that is not a page token, because a sea mixed out
    // of the neutral greys comes out as flat cardboard. Land is a shade of the
    // page itself, a touch away from the water so a coast reads without a
    // hard outline.
    out.sea = mix(out.surface, dark ? "#0a2630" : "#b9d2da", dark ? 0.55 : 0.55);
    out.land = mix(out.surface, out.ref, dark ? 0.05 : 0.07);
    out.coast = mix(out.sea, out.ref, dark ? 0.35 : 0.5);
    return out;
  }

  function hex(s) { return /^#[0-9a-f]{6}$/i.test(s || ""); }

  function mix(a, b, t) {
    if (!hex(a) || !hex(b)) return a;
    var o = "#";
    for (var i = 1; i < 7; i += 2) {
      var v = Math.round(parseInt(a.substr(i, 2), 16) * (1 - t) +
                         parseInt(b.substr(i, 2), 16) * t);
      o += (v < 16 ? "0" : "") + v.toString(16);
    }
    return o;
  }

  function data() {
    var d = global.SEAFOLK_MAPS;
    if (!d) throw new Error("SeafolkMap: load media/maps.js first");
    return d;
  }

  function layerOf(key) {
    var l = data().layers[key];
    if (!l) throw new Error("SeafolkMap: no layer " + key);
    return l;
  }

  /* The top of the colour scale. Not the maximum: one harbour cell is forty
   * times a busy fishing ground, and scaling to it paints the whole sea one
   * flat colour. Values above the top clamp to the strongest shade.
   *
   * With scaleTo the quantile is taken over the POOLED values of every layer
   * in the group, never over each layer's own — a per-layer 99th percentile
   * moves with the number of cells, so a storm day with a tenth of the cells
   * came out with a HIGHER top than the calm day before it, which would have
   * drawn the emptier map darker. */
  var topCache = {};
  function scaleTop(keys) {
    var id = keys.join("|");
    if (topCache[id]) return topCache[id];
    var all = [];
    for (var i = 0; i < keys.length; i++) {
      var c = layerOf(keys[i]).cells;
      for (var j = 2; j < c.length; j += 3) all.push(c[j]);
    }
    all.sort(function (a, b) { return a - b; });
    return (topCache[id] = Math.max(1, all[Math.floor(all.length * 0.99)]));
  }

  function draw(host, options) {
    var opts = options || {};
    var layer = layerOf(opts.layer);
    var d = data(), bbox = d.bbox, shape = d.hex[String(layer.res)];
    var land = global.SEAFOLK_LAND || [];
    var title = opts.title || layer.title;
    var showLabels = opts.labels !== false, showLegend = opts.legend !== false;
    var group = [opts.layer].concat(opts.scaleTo || []);
    var aspect = ((bbox[2] - bbox[0]) *
      Math.cos(((bbox[1] + bbox[3]) / 2) * Math.PI / 180)) / (bbox[3] - bbox[1]);

    style();
    host.innerHTML = "";
    var root = el("figure", "sfm", host);
    var cap = el("figcaption", "sfm-cap", root);
    var cv = el("canvas", null, root);
    cap.textContent = title;
    cv.setAttribute("role", "img");
    cv.setAttribute("aria-label", title + " — a map of Danish waters. " +
      layer.note + " Darker patches of sea held more.");

    var C, dpr = 1, mw = 0, mh = 0;

    function project(lon, lat) {
      return [((lon - bbox[0]) / (bbox[2] - bbox[0])) * mw,
              ((bbox[3] - lat) / (bbox[3] - bbox[1])) * mh];
    }

    function render() {
      C = tokens(root);
      dpr = Math.min(2, global.devicePixelRatio || 1);
      var avail = Math.max(160, root.clientWidth || host.clientWidth || 640);
      mw = Math.min(avail, Math.round(MAXH * aspect));
      mh = Math.round(mw / aspect);
      // The strip is reserved even when it is not drawn, so the panels of a
      // pair or a triptych — only the first of which carries the legend —
      // still line up along the bottom.
      var th = mh + (showLegend || opts.reserveLegend ? LEGEND_H : 0);
      cv.width = Math.round(mw * dpr);
      cv.height = Math.round(th * dpr);
      cv.style.width = mw + "px";
      cv.style.height = th + "px";

      var ctx = cv.getContext("2d");
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, mw, th);
      ctx.fillStyle = C.sea;
      ctx.fillRect(0, 0, mw, mh);

      var lp = new Path2D();
      for (var r = 0; r < land.length; r++) {
        var ring = land[r];
        for (var p = 0; p < ring.length; p += 2) {
          var xy = project(ring[p] / 1000, ring[p + 1] / 1000);
          if (p === 0) lp.moveTo(xy[0], xy[1]); else lp.lineTo(xy[0], xy[1]);
        }
        lp.closePath();
      }
      ctx.fillStyle = C.land;
      ctx.fill(lp);
      ctx.strokeStyle = C.coast;
      ctx.lineWidth = 0.7;
      ctx.stroke(lp);

      hexes(ctx);
      if (showLabels) places(ctx);
      if (showLegend) legend(ctx, mh);
    }

    function hexes(ctx) {
      var top = scaleTop(group), base = C[opts.colour === "ink" ? "ink" : "accent"];
      var cells = layer.cells;
      // The hexagon, once: radius in degrees of latitude, and the six vertex
      // offsets in equal-aspect space. Longitude is stretched per cell by
      // 1/cos(lat), which over six degrees of latitude is a visible difference.
      var rad = (shape[0] * OVERDRAW) / 111.19, rot = shape[1] * Math.PI / 180;
      var ox = [], oy = [];
      for (var k = 0; k < 6; k++) {
        ox.push(Math.cos(rot + k * Math.PI / 3) * rad);
        oy.push(Math.sin(rot + k * Math.PI / 3) * rad);
      }
      var paths = [];
      for (var s = 0; s < STEPS; s++) paths.push(new Path2D());
      for (var i = 0; i < cells.length; i += 3) {
        var lon = cells[i] / 1000, lat = cells[i + 1] / 1000, v = cells[i + 2];
        // sqrt: the eye reads area, not count, so a cell with four times the
        // boats should look twice as strong, not four times.
        var t = Math.min(1, Math.sqrt(v / top));
        var bucket = Math.min(STEPS - 1, Math.floor(t * STEPS));
        var kx = 1 / Math.cos(lat * Math.PI / 180), path = paths[bucket];
        for (var k2 = 0; k2 < 6; k2++) {
          var xy = project(lon + ox[k2] * kx, lat + oy[k2]);
          if (k2 === 0) path.moveTo(xy[0], xy[1]); else path.lineTo(xy[0], xy[1]);
        }
        path.closePath();
      }
      for (var b = 0; b < STEPS; b++) {
        ctx.fillStyle = shade(base, b);
        ctx.fill(paths[b]);
      }
    }

    // One hue, pale to strong: the accent mixed into the sea, from a wash that
    // barely shows to the colour itself. In the dark theme the ramp runs the
    // other way round in lightness and the same way round in strength.
    function shade(base, b) {
      var t = (b + 0.5) / STEPS;          // the bucket's middle, not its top
      return mix(C.sea, base, 0.05 + 0.95 * t);
    }

    function places(ctx) {
      // Seven names need about 420 px before Skagen starts sitting on
      // Gothenburg; below that the map keeps the four that say "this is
      // Denmark" and drops the rest.
      var list = mw < 420 ? PLACES.slice(0, FEW_PLACES) : PLACES;
      var fs = mw < 320 ? 9 : mw < 520 ? 10 : 12;
      ctx.font = "500 " + fs + "px system-ui, sans-serif";
      ctx.textBaseline = "middle";
      ctx.lineJoin = "round";
      for (var i = 0; i < list.length; i++) {
        var xy = project(list[i][2], list[i][1]);
        var right = xy[0] < mw * 0.72;
        ctx.beginPath();
        ctx.arc(xy[0], xy[1], 1.9, 0, 6.2832);
        ctx.fillStyle = C.ink;
        ctx.globalAlpha = 0.55;
        ctx.fill();
        ctx.globalAlpha = 1;
        ctx.textAlign = right ? "left" : "right";
        var tx = xy[0] + (right ? 5 : -5);
        // A halo of the sea's own colour: the only way a name stays readable
        // both over empty water and over the darkest hexagons.
        ctx.strokeStyle = C.sea;
        ctx.lineWidth = 3;
        ctx.strokeText(list[i][0], tx, xy[1]);
        ctx.fillStyle = C.label;
        ctx.fillText(list[i][0], tx, xy[1]);
      }
    }

    function legend(ctx, y0) {
      var base = C[opts.colour === "ink" ? "ink" : "accent"];
      var fs = mw < 320 ? 10 : 11;
      ctx.font = fs + "px system-ui, sans-serif";
      ctx.textBaseline = "middle";
      ctx.textAlign = "left";
      ctx.fillStyle = C.label;
      var yc = y0 + LEGEND_H / 2 + 1;
      ctx.fillText("few", 0, yc);
      var x0 = ctx.measureText("few").width + 7;
      var x1 = mw - ctx.measureText("many").width - 7;
      var sw = Math.max(6, Math.min(44, (x1 - x0) / STEPS));
      for (var b = 0; b < STEPS; b++) {
        ctx.fillStyle = shade(base, b);
        ctx.fillRect(x0 + b * sw, yc - 6, sw + 0.5, 12);
      }
      ctx.fillStyle = C.label;
      ctx.textAlign = "right";
      ctx.fillText("many", mw, yc);
    }

    var ro = global.ResizeObserver ? new ResizeObserver(render) : null;
    if (ro) ro.observe(root); else global.addEventListener("resize", render);
    var off = onTheme(render);
    render();

    return {
      element: root, redraw: render,
      destroy: function () {
        if (ro) ro.disconnect(); else global.removeEventListener("resize", render);
        off();
        host.innerHTML = "";
      }
    };
  }

  /* Both ways the page can change theme: the reader's system setting, and
   * <html data-theme="…">, which is how scripts/shot.sh forces a theme and how
   * a reader's own toggle would work. Watching only the first one left every
   * canvas on the page drawn in the wrong palette. */
  function onTheme(fn) {
    var mq = global.matchMedia && global.matchMedia("(prefers-color-scheme: dark)");
    if (mq && mq.addEventListener) mq.addEventListener("change", fn);
    var mo = global.MutationObserver ? new MutationObserver(fn) : null;
    if (mo) mo.observe(document.documentElement,
      { attributes: true, attributeFilter: ["data-theme"] });
    return function () {
      if (mq && mq.removeEventListener) mq.removeEventListener("change", fn);
      if (mo) mo.disconnect();
    };
  }

  function row(host, list) {
    style();
    host.innerHTML = "";
    var wrap = el("div", "sfm-row", host);
    var keys = list.map(function (o) { return o.layer; });
    // One scale, one legend. Repeating it under every panel says the maps
    // might be scaled differently, which is the opposite of the point. The
    // panels that do not carry it still reserve its height, so the group lines
    // up along the bottom — and if the caller turned the legend off everywhere,
    // nothing is reserved and there is no empty strip under the maps.
    var plans = list.map(function (o, i) {
      var opts = {}, k;
      for (k in o) opts[k] = o[k];
      if (!opts.scaleTo) opts.scaleTo = keys;   // one scale for the whole group
      if (opts.legend === undefined) opts.legend = i === 0;
      return opts;
    });
    var anyLegend = plans.some(function (o) { return o.legend; });
    var maps = plans.map(function (opts) {
      opts.reserveLegend = anyLegend;
      return draw(el("div", null, wrap), opts);
    });
    function lay() {
      var stack = (host.clientWidth || wrap.clientWidth) < SIDE_BY_SIDE;
      wrap.classList.toggle("sfm-col", stack);
      maps.forEach(function (m) { m.redraw(); });
    }
    var ro = global.ResizeObserver ? new ResizeObserver(lay) : null;
    if (ro) ro.observe(host); else global.addEventListener("resize", lay);
    lay();
    return {
      element: wrap, maps: maps, redraw: lay,
      destroy: function () {
        if (ro) ro.disconnect(); else global.removeEventListener("resize", lay);
        maps.forEach(function (m) { m.destroy(); });
        host.innerHTML = "";
      }
    };
  }

  function el(tag, cls, parent) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (parent) parent.appendChild(n);
    return n;
  }

  global.SeafolkMap = {
    draw: draw,
    pair: row,
    triptych: row,
    /* The three keys of a storm's triptych, in order, as the build wrote them
     * — the page never spells out a date that the data does not carry. */
    storm: function (key) { return (data().triptychs || {})[key]; }
  };
})(window);
