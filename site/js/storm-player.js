/* The sea empties — an hour-by-hour storm map, Canvas 2D, no dependencies.
 *
 * Embed (two lines, plus a container):
 *   <script src="media/land.js"></script><script src="media/storm-pia.js"></script><script src="js/storm-player.js"></script>
 *   <div id="storm"></div><script>SeafolkStorm.mount(document.getElementById('storm'), 'pia')</script>
 *
 * Plain <script> tags on purpose: the site has to open from file:// by
 * double-click, where fetch() and modules do not.
 *
 * It behaves like a GIF: it starts by itself when it scrolls into view, loops
 * with a short hold on the last frame, and pauses on click/tap or Space. A
 * slim scrubber stays for the curious. Under prefers-reduced-motion nothing
 * moves — the storm's emptiest hour is drawn and the note says so.
 *
 * mount(element, key, options?) -> { play, pause, toggle, seek, hours, destroy }
 *   options.autoplay  false switches the scroll-into-view autoplay off
 *                     (screenshots), otherwise it is on
 *   options.hour      the hour to open on (default 0)
 *   options.speed     hours per second (default 8, the same as the mp4)
 *
 * The data files are written by scripts/render_storm.py. One boat icon is one
 * hexagon of sea about seven kilometres across in which a fishing boat sent at
 * least one message while under way in that hour — places, not boats. Only
 * public fleets (cargo, ferries, fishing) are in the data at all.
 */
(function (global) {
  "use strict";

  // The frame bitmaps are base64 in an alphabet with no digits in it, so that
  // "no nine-digit integer under site/" can never trip over a data blob.
  var ALPHA =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz+-*/=_.~!@#$";
  var REV = {};
  for (var i = 0; i < 64; i++) REV[ALPHA[i]] = i;

  // The page tokens, plus four the page does not have: the map needs water to
  // read as water, and --surface is a card colour, not a sea. Anything with a
  // matching CSS custom property still wins (see tokens()).
  var LIGHT = {
    ground: "#e9eeef", surface: "#f7f9f9", hairline: "#cfdadc",
    ink: "#0f1a1d", label: "#55676c", accent: "#eb6834",
    working: "#7d8f94", ref: "#a8b8bc",
    seatop: "#dceaef", seabot: "#b4cdd8", land: "#f1f4f3", coast: "#9fb3ba"
  };
  var DARK = {
    ground: "#0b1416", surface: "#122023", hairline: "#23383c",
    ink: "#e8eeef", label: "#9db0b4", accent: "#f07a45",
    working: "#7b8f94", ref: "#47605f",
    seatop: "#123441", seabot: "#0a1d25", land: "#1b2e33", coast: "#3b545b"
  };

  // fleet -> token name and how hard it is drawn. Fishing carries the story,
  // so it gets the accent and the boat glyph; cargo and the ferries are faint
  // marks that keep the lanes visible without competing.
  var STYLE = {
    cargo: { token: "working", alpha: 0.34 },
    passenger: { token: "label", alpha: 0.45 },
    fishing: { token: "accent", alpha: 1 }
  };

  var BBOX = [3, 53, 17, 59];
  var LAT0 = 56;
  var ASPECT =
    ((BBOX[2] - BBOX[0]) * Math.cos((LAT0 * Math.PI) / 180)) /
    (BBOX[3] - BBOX[1]);

  // lon, lat, name, 1 if it is a town (gets a dot)
  var PLACES = [
    [10.58, 57.72, "Skagen", 1], [8.62, 57.12, "Hanstholm", 1],
    [8.45, 55.47, "Esbjerg", 1], [12.57, 55.68, "Copenhagen", 1],
    [14.92, 55.13, "Bornholm", 0],
    [11.5, 56.75, "KATTEGAT", 0], [4.9, 55.4, "NORTH SEA", 0]
  ];

  // A hull with a cabin, bow to the right, in units of the icon's length.
  var BOAT = new Path2D();
  BOAT.moveTo(-0.52, 0.06); BOAT.lineTo(0.55, 0.06);
  BOAT.lineTo(0.30, 0.34); BOAT.lineTo(-0.40, 0.34); BOAT.closePath();
  BOAT.moveTo(-0.16, -0.30); BOAT.lineTo(0.14, -0.30);
  BOAT.lineTo(0.19, 0.06); BOAT.lineTo(-0.21, 0.06); BOAT.closePath();

  var CSS =
    ".sfs{display:block;margin:0;font:inherit;color:var(--ink,#0f1a1d)}" +
    ".sfs canvas{display:block;height:auto;border-radius:4px}" +
    ".sfs-map{margin:0 auto;cursor:pointer;outline-offset:3px}" +
    ".sfs-time{margin-top:.45em;margin-left:auto;margin-right:auto}" +
    ".sfs-bar{display:flex;align-items:center;margin:.1em auto 0}" +
    ".sfs-bar input{flex:1 1 auto;min-width:0;margin:0;height:1em;" +
    "accent-color:var(--accent,#eb6834);opacity:.65}" +
    ".sfs-bar input:hover,.sfs-bar input:focus{opacity:1}" +
    ".sfs-note{margin:.5em 0 0;color:var(--label,#55676c);font-size:.82em;line-height:1.5}";

  function style() {
    if (document.getElementById("sfs-css")) return;
    var s = document.createElement("style");
    s.id = "sfs-css";
    s.textContent = CSS;
    document.head.appendChild(s);
  }

  function decode(s, bytes) {
    var out = new Uint8Array(bytes), acc = 0, n = 0, k = 0;
    for (var i = 0; i < s.length; i++) {
      acc = (acc << 6) | REV[s[i]];
      n += 6;
      if (n >= 8) {
        n -= 8;
        if (k < bytes) out[k++] = (acc >> n) & 255;
      }
    }
    return out;
  }

  function tokens(el) {
    var dark =
      global.matchMedia &&
      global.matchMedia("(prefers-color-scheme: dark)").matches;
    var forced = document.documentElement.getAttribute("data-theme");
    if (forced === "dark") dark = true;
    else if (forced === "light") dark = false;
    var base = dark ? DARK : LIGHT;
    var cs = getComputedStyle(el), out = {};
    for (var k in base) {
      var v = cs.getPropertyValue("--" + k).trim();
      out[k] = v || base[k];
    }
    out.dark = dark;
    return out;
  }

  var DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  var MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function at(t0, h) { return new Date(t0.getTime() + h * 3600000); }

  function clockText(t0, h) {
    var d = at(t0, h), hh = d.getUTCHours();
    return DAYS[d.getUTCDay()] + " " + d.getUTCDate() + " " +
      MON[d.getUTCMonth()] + " · " + (hh < 10 ? "0" : "") + hh + ":00";
  }

  function el(tag, cls, parent) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (parent) parent.appendChild(n);
    return n;
  }

  // A stable pseudo-random in [0,1) from an integer — the same boat gets the
  // same tilt and nudge on every frame, so the fleet does not jitter in place
  // and the cells do not read as a grid.
  function rnd(i, salt) {
    var x = Math.sin(i * 12.9898 + salt * 78.233) * 43758.5453;
    return x - Math.floor(x);
  }

  function mount(host, key, options) {
    var data = (global.SEAFOLK_STORM || {})[key];
    if (!data) throw new Error("SeafolkStorm: no data for " + key +
      " — load media/storm-" + key + ".js first");
    var land = global.SEAFOLK_LAND || [];
    var opts = options || {};
    var speed = opts.speed || 8;
    var reduce = global.matchMedia &&
      global.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // the storm's own band, and the emptiest fishing hour inside it
    var stormBand = null;
    for (var bi = 0; bi < data.bands.length; bi++) {
      if (data.bands[bi][3]) stormBand = data.bands[bi];
    }
    if (!stormBand) stormBand = [0, 0, "the storm", 1];
    var fishCounts = data.fleets.fishing.counts;
    var peak = stormBand[0];
    for (var pi = stormBand[0]; pi < Math.min(stormBand[1], data.hours); pi++) {
      if (fishCounts[pi] < fishCounts[peak]) peak = pi;
    }

    style();
    host.innerHTML = "";
    var root = el("figure", "sfs", host);
    var map = el("canvas", "sfs-map", root);
    var time = el("canvas", "sfs-time", root);
    var bar = el("div", "sfs-bar", root);
    var range = el("input", null, bar);
    var note = el("p", "sfs-note", root);

    map.setAttribute("role", "img");
    map.tabIndex = 0;
    map.setAttribute("aria-label", data.title + ". " + data.claim +
      " Each boat icon is a patch of sea where fishing boats were under way in" +
      " that hour; cargo and ferries are the faint marks behind them.");
    time.setAttribute("aria-hidden", "true");
    range.type = "range";
    range.min = 0;
    range.max = data.hours - 1;
    range.step = 1;
    // An explicit hour wins over everything — that is how the screenshots
    // land where they mean to. Otherwise reduced motion opens on the storm's
    // emptiest hour, which is the one frame worth having if only one is seen.
    range.value = Math.min(data.hours - 1,
      Math.max(0, opts.hour != null ? opts.hour : (reduce ? peak : 0)));
    range.setAttribute("aria-label", "Hour of the storm");
    note.textContent = reduce
      ? "Your system asks for reduced motion, so nothing moves here — this is " +
        "the storm at its emptiest hour. Drag the slider to see the week. " +
        "Each boat is a patch of sea about seven kilometres across where " +
        "fishing boats were under way. Danish Maritime Authority AIS archive."
      : "Each boat is a patch of sea about seven kilometres across where that " +
        "kind of boat was under way in that hour — patches, not boats. Click " +
        "the map to pause. Danish Maritime Authority AIS archive.";

    var order = data.order, fleets = data.fleets;

    // decoded frames, one lazy cache per fleet
    var cache = {}, bytes = {};
    for (var g2 in fleets) {
      cache[g2] = new Array(data.hours);
      bytes[g2] = ((fleets[g2].cells.length / 2) + 7) >> 3;
    }
    // how far each fishing cell has faded in, so icons appear and go over a
    // few frames instead of popping
    var fade = new Float32Array(fleets.fishing.cells.length / 2);

    var t0 = new Date(data.t0);
    var C, dpr = 1, mw = 0, mh = 0, tw = 0, landPath = null, xy = null;
    var hour = +range.value, timer = null, last = 0, acc = 0, hold = 0;
    var MAXH = 560; // a figure in a column of prose, not a wall map

    function project(lon, lat) {
      return [
        ((lon - BBOX[0]) / (BBOX[2] - BBOX[0])) * mw,
        ((BBOX[3] - lat) / (BBOX[3] - BBOX[1])) * mh
      ];
    }

    function layout() {
      C = tokens(root);
      dpr = Math.min(2, global.devicePixelRatio || 1);
      tw = Math.max(200, root.clientWidth || host.clientWidth || 640);
      mw = Math.min(tw, Math.round(MAXH * ASPECT));
      mh = Math.round(mw / ASPECT);
      map.width = Math.round(mw * dpr);
      map.height = Math.round(mh * dpr);
      map.style.width = mw + "px";
      map.style.height = mh + "px";
      var th = mw < 520 ? 34 : 42;
      time.width = Math.round(mw * dpr);
      time.height = Math.round(th * dpr);
      time.style.width = mw + "px";
      time.style.height = th + "px";
      bar.style.width = mw + "px";

      landPath = new Path2D();
      for (var r = 0; r < land.length; r++) {
        var ring = land[r];
        for (var p = 0; p < ring.length; p += 2) {
          var q = project(ring[p] / 1000, ring[p + 1] / 1000);
          if (p === 0) landPath.moveTo(q[0], q[1]);
          else landPath.lineTo(q[0], q[1]);
        }
        landPath.closePath();
      }
      // pixel positions per fleet, computed once per layout instead of once
      // per cell per frame
      xy = {};
      for (var g in fleets) {
        var cells = fleets[g].cells, a = new Float32Array(cells.length);
        for (var c = 0; c < cells.length; c += 2) {
          var s = project(cells[c] / 1000, cells[c + 1] / 1000);
          a[c] = s[0];
          a[c + 1] = s[1];
        }
        xy[g] = a;
      }
      draw();
      drawTime();
    }

    function frame(g, t) {
      if (!cache[g][t]) cache[g][t] = decode(fleets[g].frames[t], bytes[g]);
      return cache[g][t];
    }

    /* 0 before the storm, 1 through it, 2 after — and the weather strength,
     * ramped over six hours at each edge so the sea does not switch. */
    function phase() {
      if (hour < stormBand[0]) return 0;
      if (hour < stormBand[1]) return 1;
      return 2;
    }

    function weather() {
      var into = (hour - stormBand[0] + 6) / 6;
      var outof = (stormBand[1] + 6 - hour) / 6;
      return Math.max(0, Math.min(1, into, outof));
    }

    function phaseText() {
      return ["Before the storm", "Storm " + data.name, "After the storm"][phase()];
    }

    function sea(ctx, wx) {
      var g = ctx.createLinearGradient(0, 0, 0, mh);
      g.addColorStop(0, C.seatop);
      g.addColorStop(1, C.seabot);
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, mw, mh);
      if (wx > 0) {
        ctx.globalAlpha = wx * (C.dark ? 0.34 : 0.26);
        ctx.fillStyle = C.dark ? "#000810" : "#1b333f";
        ctx.fillRect(0, 0, mw, mh);
        ctx.globalAlpha = 1;
      }
    }

    /* A few dozen slanted strokes drifting across the water. Cheap, and at
     * this opacity it reads as weather rather than as a texture. */
    function wind(ctx, wx, t) {
      if (wx <= 0) return;
      var n = 54, len = mw * 0.09, drift = (t % 8) / 8;
      ctx.save();
      ctx.strokeStyle = C.dark ? "#cfe4ee" : "#ffffff";
      ctx.lineWidth = Math.max(1, mw / 640);
      ctx.lineCap = "round";
      ctx.globalAlpha = wx * 0.22;
      ctx.beginPath();
      for (var i = 0; i < n; i++) {
        var x = ((rnd(i, 1) + drift * 0.7) % 1) * (mw + len * 2) - len;
        var y = ((rnd(i, 2) + drift * 0.25) % 1) * mh;
        var l = len * (0.5 + rnd(i, 3));
        ctx.moveTo(x, y);
        ctx.lineTo(x + l, y + l * 0.45);
      }
      ctx.stroke();
      ctx.restore();
    }

    function places(ctx) {
      var f = Math.max(8, Math.round(mw / 74));
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.lineJoin = "round";
      ctx.strokeStyle = C.dark ? "rgba(8,20,24,.8)" : "rgba(247,249,249,.85)";
      ctx.lineWidth = Math.max(2, f / 3.2);
      for (var i = 0; i < PLACES.length; i++) {
        var p = PLACES[i], q = project(p[0], p[1]);
        ctx.globalAlpha = 0.85;
        if (p[3]) {
          ctx.fillStyle = C.label;
          ctx.beginPath();
          ctx.arc(q[0], q[1], Math.max(1.4, f / 6), 0, 6.2832);
          ctx.fill();
          ctx.font = f + "px system-ui, sans-serif";
          ctx.strokeText(p[2], q[0], q[1] - f);
          ctx.fillText(p[2], q[0], q[1] - f);
        } else {
          ctx.fillStyle = C.label;
          ctx.globalAlpha = 0.6;
          ctx.font = (f - 1) + "px system-ui, sans-serif";
          ctx.fillText(p[2].split("").join(" "), q[0], q[1]);
        }
      }
      ctx.globalAlpha = 1;
    }

    /* A soft scrim at the top and the bottom of the map. Without it the
     * phase label and the counter land on whatever happens to be under
     * them — white Jutland one hour, dark water the next — and neither
     * reads. */
    function scrim(ctx, h, up) {
      var g = ctx.createLinearGradient(0, up ? 0 : mh, 0, up ? h : mh - h);
      var bg = C.dark ? "11,20,22" : "247,249,249";
      g.addColorStop(0, "rgba(" + bg + ",0.78)");
      g.addColorStop(0.55, "rgba(" + bg + ",0.38)");
      g.addColorStop(1, "rgba(" + bg + ",0)");
      ctx.fillStyle = g;
      ctx.fillRect(0, up ? 0 : mh - h, mw, h);
    }

    function overlay(ctx) {
      var pad = Math.round(mw / 26);
      var big = Math.max(17, Math.round(mw / 21));
      scrim(ctx, pad + big * 2.1, true);
      scrim(ctx, pad + Math.max(22, Math.round(mw / 15)) * 1.9, false);
      ctx.textAlign = "left";
      ctx.textBaseline = "alphabetic";

      ctx.fillStyle = phase() === 1 ? C.accent : C.ink;
      ctx.font = "700 " + big + "px Georgia, 'Source Serif 4', serif";
      ctx.fillText(phaseText(), pad, pad + big);
      ctx.fillStyle = C.label;
      ctx.font = Math.round(big * 0.52) +
        "px ui-monospace, 'IBM Plex Mono', monospace";
      ctx.fillText(clockText(t0, hour), pad, pad + big * 1.65);

      // the counter, bottom left
      var num = Math.max(22, Math.round(mw / 15));
      var y = mh - pad;
      ctx.fillStyle = C.label;
      ctx.font = Math.max(10, Math.round(mw / 62)) + "px system-ui, sans-serif";
      ctx.fillText("patches of sea with fishing boats moving", pad, y);
      ctx.fillStyle = C.accent;
      ctx.font = "700 " + num +
        "px ui-monospace, 'IBM Plex Mono', monospace";
      ctx.fillText(String(fleets.fishing.counts[hour]), pad, y - num * 0.52);

      // the key, bottom right
      var k = Math.max(9, Math.round(mw / 68));
      var narrow = mw < 520, ky = narrow ? pad + k : mh - pad;
      ctx.textAlign = "right";
      ctx.font = k + "px system-ui, sans-serif";
      var rows = [["fishing", "fishing boats"], ["passenger", "ferries"],
                  ["cargo", "cargo ships"]];
      for (var i = 0; i < rows.length; i++) {
        var g = rows[i][0];
        var yy = narrow ? ky + i * k * 1.55 : ky - i * k * 1.55;
        ctx.globalAlpha = 0.9;
        ctx.fillStyle = C.label;
        ctx.fillText(rows[i][1], mw - pad, yy);
        ctx.fillStyle = C[STYLE[g].token];
        var mx = mw - pad - ctx.measureText(rows[i][1]).width - k * 1.2;
        if (g === "fishing") boat(ctx, mx, yy - k * 0.35, k * 1.25, 0);
        else {
          ctx.globalAlpha = 0.75;
          ctx.beginPath();
          ctx.arc(mx, yy - k * 0.35, k * 0.28, 0, 6.2832);
          ctx.fill();
        }
      }
      ctx.globalAlpha = 1;
    }

    /* `edge` draws a hairline of sea around the hull, so a crowded fishing
     * ground reads as a crowd of boats instead of as one orange blob. */
    function boat(ctx, x, y, s, rot, edge) {
      ctx.save();
      ctx.translate(x, y);
      if (rot) ctx.rotate(rot);
      ctx.scale(s, s);
      ctx.fill(BOAT);
      if (edge) {
        ctx.lineWidth = 1 / s;
        ctx.strokeStyle = C.dark ? "rgba(8,20,24,.85)" : "rgba(255,255,255,.9)";
        ctx.stroke(BOAT);
      }
      ctx.restore();
    }

    function marks(ctx, g) {
      var bits = frame(g, hour), a = xy[g], r = Math.max(0.9, mw / 560);
      var path = new Path2D();
      for (var b = 0; b < bits.length; b++) {
        var v = bits[b];
        if (!v) continue;
        for (var j = 0; j < 8; j++) {
          if (!(v & (128 >> j))) continue;
          var c = ((b << 3) | j) * 2;
          path.moveTo(a[c] + r, a[c + 1]);
          path.arc(a[c], a[c + 1], r, 0, 6.2832);
        }
      }
      ctx.globalAlpha = STYLE[g].alpha;
      ctx.fillStyle = C[STYLE[g].token];
      ctx.fill(path);
      ctx.globalAlpha = 1;
    }

    /* Step every fishing cell towards on/off. `jump` snaps (a scrub or the
     * first paint), otherwise it takes about four frames. */
    function fishing(ctx, jump) {
      var bits = frame("fishing", hour), a = xy.fishing;
      var s = Math.max(8, Math.min(12, mw / 58));
      for (var i = 0; i < fade.length; i++) {
        var on = (bits[i >> 3] & (128 >> (i & 7))) ? 1 : 0;
        fade[i] = jump ? on : fade[i] + (on - fade[i]) * 0.34;
        if (fade[i] < 0.02) { fade[i] = 0; continue; }
        var c = i * 2;
        var k = fade[i];
        ctx.globalAlpha = k * STYLE.fishing.alpha;
        ctx.fillStyle = C.accent;
        boat(ctx,
          a[c] + (rnd(i, 4) - 0.5) * s * 0.5,
          a[c + 1] + (rnd(i, 5) - 0.5) * s * 0.5,
          s * (0.82 + rnd(i, 6) * 0.36) * (0.5 + k * 0.5),
          (rnd(i, 7) - 0.5) * 0.7, 1);
      }
      ctx.globalAlpha = 1;
    }

    function draw(jump) {
      var ctx = map.getContext("2d");
      var wx = weather();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, mw, mh);
      sea(ctx, wx);
      ctx.fillStyle = C.land;
      ctx.strokeStyle = C.coast;
      ctx.lineWidth = 0.9;
      ctx.lineJoin = "round";
      ctx.fill(landPath);
      ctx.stroke(landPath);
      wind(ctx, wx, hour);
      marks(ctx, "cargo");
      marks(ctx, "passenger");
      fishing(ctx, jump);
      places(ctx);
      overlay(ctx);

      range.setAttribute("aria-valuetext",
        phaseText() + ", " + clockText(t0, hour));
    }

    function drawTime() {
      var ctx = time.getContext("2d");
      var h = time.height / dpr, n = data.hours, w = mw;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      var x = function (t) { return (t / (n - 1)) * w; };
      var top = 12, bot = h - 10;

      for (var i = 0; i < data.bands.length; i++) {
        var band = data.bands[i];
        ctx.globalAlpha = 0.16;
        ctx.fillStyle = band[3] ? C.accent : C.working;
        ctx.fillRect(x(band[0]), 0, x(band[1]) - x(band[0]), bot);
        ctx.globalAlpha = 1;
      }

      var cs = fleets.fishing.counts, max = Math.max.apply(null, cs) || 1;
      var y = function (t) { return bot - (cs[t] / max) * (bot - top); };
      ctx.beginPath();
      ctx.moveTo(0, bot);
      for (var t = 0; t < n; t++) ctx.lineTo(x(t), y(t));
      ctx.lineTo(w, bot);
      ctx.closePath();
      ctx.globalAlpha = 0.26;
      ctx.fillStyle = C.accent;
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.beginPath();
      for (var t2 = 0; t2 < n; t2++) {
        if (t2 === 0) ctx.moveTo(x(t2), y(t2));
        else ctx.lineTo(x(t2), y(t2));
      }
      ctx.strokeStyle = C.accent;
      ctx.lineWidth = 1.1;
      ctx.stroke();

      ctx.fillStyle = C.label;
      ctx.font = "9.5px system-ui, sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "alphabetic";
      for (var d = 0; d < n; d += 24) {
        ctx.strokeStyle = C.hairline;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x(d) + 0.5, bot);
        ctx.lineTo(x(d) + 0.5, bot + 3);
        ctx.stroke();
        if (w > 520 || d % 48 === 0) {
          var dd = at(t0, d);
          ctx.fillText(DAYS[dd.getUTCDay()] + " " + dd.getUTCDate(),
            x(d) + 3, h - 1);
        }
      }

      ctx.strokeStyle = C.ink;
      ctx.lineWidth = 1.3;
      ctx.beginPath();
      ctx.moveTo(x(hour) + 0.5, 0);
      ctx.lineTo(x(hour) + 0.5, bot);
      ctx.stroke();

      // last, so the cursor never crosses out a band's name
      ctx.font = "10px system-ui, sans-serif";
      ctx.textAlign = "center";
      for (var b = 0; b < data.bands.length; b++) {
        ctx.fillStyle = data.bands[b][3] ? C.accent : C.label;
        ctx.fillText(data.bands[b][2],
          (x(data.bands[b][0]) + x(data.bands[b][1])) / 2, 10);
      }
    }

    function seek(t, jump) {
      hour = Math.max(0, Math.min(data.hours - 1, t | 0));
      range.value = hour;
      draw(jump);
      drawTime();
    }

    function tick(now) {
      if (timer === null) return;
      if (hold) {
        if (now < hold) { timer = requestAnimationFrame(tick); return; }
        hold = 0;
        last = 0;
        seek(0, true);
      }
      if (last) {
        acc += ((now - last) / 1000) * speed;
        if (acc >= 1) {
          var step = Math.floor(acc);
          acc -= step;
          if (hour + step >= data.hours - 1) {
            seek(data.hours - 1);
            hold = now + 1100;   // a beat on the last frame, then round again
          } else {
            seek(hour + step);
          }
        } else {
          draw();                // keep the fade and the wind moving
        }
      }
      last = now;
      timer = requestAnimationFrame(tick);
    }

    function play() {
      if (timer !== null || reduce) return;
      if (hour >= data.hours - 1) seek(0, true);
      last = 0;
      acc = 0;
      hold = 0;
      timer = requestAnimationFrame(tick);
    }

    function pause() {
      if (timer !== null) cancelAnimationFrame(timer);
      timer = null;
      hold = 0;
    }

    function toggle() { timer === null ? play() : pause(); }

    map.addEventListener("click", toggle);
    map.addEventListener("keydown", function (e) {
      if (e.key === " " || e.key === "Spacebar" || e.key === "Enter") {
        e.preventDefault();
        toggle();
      }
    });
    range.addEventListener("input", function () {
      pause();
      seek(+range.value, true);
    });

    var mqDark = global.matchMedia &&
      global.matchMedia("(prefers-color-scheme: dark)");
    var onTheme = function () { layout(); };
    if (mqDark && mqDark.addEventListener) {
      mqDark.addEventListener("change", onTheme);
    }
    var ro = global.ResizeObserver ? new ResizeObserver(layout) : null;
    if (ro) ro.observe(root);
    else global.addEventListener("resize", layout);

    layout();
    seek(hour, true);

    // It plays like a GIF: on screen it runs, off screen it stops.
    var io = null;
    if (opts.autoplay !== false && !reduce && global.IntersectionObserver) {
      io = new IntersectionObserver(function (es) {
        es[0].isIntersecting ? play() : pause();
      }, { threshold: 0.35 });
      io.observe(root);
    }

    return {
      play: play, pause: pause, toggle: toggle,
      seek: function (t) { seek(t, true); },
      hours: data.hours, element: root,
      destroy: function () {
        pause();
        if (io) io.disconnect();
        if (ro) ro.disconnect();
        else global.removeEventListener("resize", layout);
        if (mqDark && mqDark.removeEventListener) {
          mqDark.removeEventListener("change", onTheme);
        }
        host.innerHTML = "";
      }
    };
  }

  /* load(keys, done) — pull in the clips the build asked for, then call
   * done(the keys that arrived).
   *
   * Which storms have a clip is decided by scripts/render_storm.py and read
   * off the directory by site_data.clips, so the page cannot carry the file
   * names as <script src> tags: it would be a fourth place that has to agree
   * with the other three. A <script> element appended here still works from
   * file://, where fetch() does not.
   */
  function load(keys, done) {
    var got = [], left = keys.length;
    if (!left) return done(got);
    keys.forEach(function (key) {
      function settle(ok) {
        if (ok) got.push(key);
        if (--left === 0) done(keys.filter(function (k) {
          return got.indexOf(k) >= 0;
        }));
      }
      if ((global.SEAFOLK_STORM || {})[key]) return settle(true);
      var s = document.createElement("script");
      s.src = "media/storm-" + key + ".js";
      s.onload = function () { settle(!!(global.SEAFOLK_STORM || {})[key]); };
      s.onerror = function () { settle(false); };
      document.head.appendChild(s);
    });
  }

  /* The one thing a reader sees when the clip does not arrive. Both pages
   * used to fail differently and both failures were silent: the story page
   * hid the figure while the paragraph above it still said "here is the same
   * storm as a map", and the chapter left an empty captioned box. */
  function unavailable(host, key) {
    host.innerHTML = "";
    var p = document.createElement("p");
    p.className = "source";
    p.textContent = "The animation could not be loaded — open "
      + "site/media/storm-" + key + ".mp4";
    host.appendChild(p);
  }

  global.SeafolkStorm = { mount: mount, load: load, unavailable: unavailable };
})(window);
