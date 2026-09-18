/* The sea empties — an hour-by-hour storm map, Canvas 2D, no dependencies.
 *
 * Embed (two lines, plus a container):
 *   <script src="media/land.js"></script><script src="media/storm-pia.js"></script><script src="js/storm-player.js"></script>
 *   <div id="storm"></div><script>SeafolkStorm.mount(document.getElementById('storm'), 'pia')</script>
 *
 * Plain <script> tags on purpose: the site has to open from file:// by
 * double-click, where fetch() and modules do not.
 *
 * mount(element, key, options?) -> { play, pause, toggle, seek, hours, destroy }
 *   options.autoplay  start playing (ignored under prefers-reduced-motion)
 *   options.hour      the hour to open on (default 0)
 *   options.speed     hours per second (default 8, the same as the mp4)
 *
 * The data files are written by scripts/render_storm.py. A dot is one hexagon
 * of sea about seven kilometres across in which that kind of boat sent at
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

  var LIGHT = {
    ground: "#e9eeef", surface: "#f7f9f9", hairline: "#cfdadc",
    ink: "#0f1a1d", label: "#55676c", accent: "#eb6834",
    working: "#7d8f94", ref: "#a8b8bc"
  };
  var DARK = {
    ground: "#0b1416", surface: "#122023", hairline: "#23383c",
    ink: "#e8eeef", label: "#9db0b4", accent: "#f07a45",
    working: "#7b8f94", ref: "#47605f"
  };

  // fleet -> token name for its dots, and how hard they are drawn. Fishing is
  // the accent because fishing is what the picture is about; cargo is the
  // palest because there are five times as many of its dots; --ref is too
  // faint to carry a dot in the dark theme, so the ferries take --label.
  // The same three in scripts/render_storm.py.
  var STYLE = {
    cargo: { token: "working", alpha: 0.6 },
    passenger: { token: "label", alpha: 0.8 },
    fishing: { token: "accent", alpha: 0.95 }
  };

  var BBOX = [3, 53, 17, 59];
  var LAT0 = 56;
  var ASPECT =
    ((BBOX[2] - BBOX[0]) * Math.cos((LAT0 * Math.PI) / 180)) /
    (BBOX[3] - BBOX[1]);

  var CSS =
    ".sfs{display:block;margin:0;font:inherit;color:var(--ink,#0f1a1d)}" +
    ".sfs-top{display:flex;flex-wrap:wrap;gap:.35em 1.4em;align-items:baseline;margin:0 0 .5em}" +
    ".sfs-clock{font-family:'IBM Plex Mono',ui-monospace,monospace;font-variant-numeric:tabular-nums;font-size:1.05em}" +
    ".sfs-counts{display:flex;flex-wrap:wrap;gap:.2em 1.1em;color:var(--label,#55676c);font-size:.92em}" +
    ".sfs-counts span{white-space:nowrap}" +
    ".sfs-counts i{display:inline-block;width:.6em;height:.6em;border-radius:50%;margin-right:.4em}" +
    ".sfs-counts b{font-family:'IBM Plex Mono',ui-monospace,monospace;font-variant-numeric:tabular-nums;font-weight:600;color:var(--ink,#0f1a1d)}" +
    ".sfs canvas{display:block;height:auto;border-radius:3px}" +
    ".sfs-map{margin:0 auto}" +
    ".sfs-time{margin-top:.5em;width:100%}" +
    ".sfs-bar{display:flex;align-items:center;gap:.7em;margin-top:.3em}" +
    ".sfs-bar input{flex:1 1 auto;min-width:0;margin:0;accent-color:var(--accent,#eb6834)}" +
    ".sfs-btn{flex:0 0 auto;font:inherit;font-size:.92em;padding:.3em .9em;cursor:pointer;" +
    "color:var(--ink,#0f1a1d);background:var(--surface,#f7f9f9);" +
    "border:1px solid var(--hairline,#cfdadc);border-radius:3px}" +
    ".sfs-btn:hover{border-color:var(--label,#55676c)}" +
    ".sfs-note{margin:.6em 0 0;color:var(--label,#55676c);font-size:.82em;line-height:1.5}";

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
    var base = dark ? DARK : LIGHT;
    var cs = getComputedStyle(el), out = {};
    for (var k in base) {
      var v = cs.getPropertyValue("--" + k).trim();
      out[k] = v || base[k];
    }
    return out;
  }

  function clockText(t0, h) {
    var d = new Date(t0.getTime() + h * 3600000);
    var days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    var mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    var hh = d.getUTCHours();
    return days[d.getUTCDay()] + " " + d.getUTCDate() + " " +
      mon[d.getUTCMonth()] + " · " + (hh < 10 ? "0" : "") + hh + ":00";
  }

  function el(tag, cls, parent) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (parent) parent.appendChild(n);
    return n;
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

    style();
    host.innerHTML = "";
    var root = el("figure", "sfs", host);
    var top = el("div", "sfs-top", root);
    var clock = el("div", "sfs-clock", top);
    var counts = el("div", "sfs-counts", top);
    var map = el("canvas", "sfs-map", root);
    var time = el("canvas", "sfs-time", root);
    var bar = el("div", "sfs-bar", root);
    var btn = el("button", "sfs-btn", bar);
    var range = el("input", null, bar);
    var note = el("p", "sfs-note", root);

    map.setAttribute("role", "img");
    map.setAttribute("aria-label", data.title + ". " + data.claim +
      " Each dot is a patch of sea where that kind of boat was under way in" +
      " that hour; the counts above the map are read out as it plays.");
    time.setAttribute("aria-hidden", "true");
    btn.type = "button";
    range.type = "range";
    range.min = 0;
    range.max = data.hours - 1;
    range.step = 1;
    range.value = Math.min(data.hours - 1, Math.max(0, opts.hour || 0));
    range.setAttribute("aria-label", "Hour of the storm");
    note.textContent =
      "Each dot is a patch of sea about seven kilometres across where that " +
      "kind of boat was under way in that hour. The numbers count the " +
      "patches, not the boats. Danish Maritime Authority AIS archive.";

    var order = data.order, fleets = data.fleets, num = {}, chip = {};
    for (var i = 0; i < order.length; i++) {
      var g = order[order.length - 1 - i]; // fishing first: it is the story
      var span = el("span", null, counts);
      chip[g] = el("i", null, span);
      span.appendChild(document.createTextNode(fleets[g].label + " "));
      num[g] = el("b", null, span);
    }

    // decoded frames, one lazy cache per fleet
    var cache = {}, bytes = {};
    for (var g2 in fleets) {
      cache[g2] = new Array(data.hours);
      bytes[g2] = ((fleets[g2].cells.length / 2) + 7) >> 3;
    }

    var t0 = new Date(data.t0);
    var C, dpr = 1, mw = 0, mh = 0, tw = 0, landPath = null;
    var hour = +range.value, timer = null, last = 0, acc = 0;
    var MAXH = 520; // a figure in a column of prose, not a wall map

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
      var th = tw < 520 ? 44 : 56;
      time.width = Math.round(tw * dpr);
      time.height = Math.round(th * dpr);
      time.style.height = th + "px";

      landPath = new Path2D();
      for (var r = 0; r < land.length; r++) {
        var ring = land[r];
        for (var p = 0; p < ring.length; p += 2) {
          var xy = project(ring[p] / 1000, ring[p + 1] / 1000);
          if (p === 0) landPath.moveTo(xy[0], xy[1]);
          else landPath.lineTo(xy[0], xy[1]);
        }
        landPath.closePath();
      }
      for (var g3 in STYLE) chip[g3].style.background = C[STYLE[g3].token];
      draw();
      drawTime();
    }

    function frame(g, t) {
      if (!cache[g][t]) cache[g][t] = decode(fleets[g].frames[t], bytes[g]);
      return cache[g][t];
    }

    function draw() {
      var ctx = map.getContext("2d");
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, mw, mh);
      ctx.fillStyle = C.surface;
      ctx.fillRect(0, 0, mw, mh);
      ctx.fillStyle = C.hairline;
      ctx.strokeStyle = C.ref;
      ctx.lineWidth = 0.6;
      ctx.fill(landPath);
      ctx.stroke(landPath);

      var r = Math.max(1.1, Math.min(4, (mw / 788) * 3));
      for (var i = 0; i < order.length; i++) {
        var g = order[i], f = fleets[g], bits = frame(g, hour);
        var path = new Path2D();
        for (var b = 0; b < bits.length; b++) {
          var v = bits[b];
          if (!v) continue;
          for (var j = 0; j < 8; j++) {
            if (!(v & (128 >> j))) continue;
            var c = ((b << 3) | j) * 2;
            var xy = project(f.cells[c] / 1000, f.cells[c + 1] / 1000);
            path.moveTo(xy[0] + r, xy[1]);
            path.arc(xy[0], xy[1], r, 0, 6.2832);
          }
        }
        ctx.globalAlpha = STYLE[g].alpha;
        ctx.fillStyle = C[STYLE[g].token];
        ctx.fill(path);
      }
      ctx.globalAlpha = 1;

      clock.textContent = clockText(t0, hour);
      range.setAttribute("aria-valuetext", clockText(t0, hour));
      for (var k = 0; k < order.length; k++) {
        num[order[k]].textContent = fleets[order[k]].counts[hour];
      }
    }

    function drawTime() {
      var ctx = time.getContext("2d");
      var h = time.height / dpr, n = data.hours;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, tw, h);
      var x = function (t) { return (t / (n - 1)) * tw; };
      var top = 14, bot = h - 12;

      for (var i = 0; i < data.bands.length; i++) {
        var band = data.bands[i];
        ctx.globalAlpha = 0.15;
        ctx.fillStyle = band[3] ? C.accent : C.working;
        ctx.fillRect(x(band[0]), 0, x(band[1]) - x(band[0]), bot);
        ctx.globalAlpha = 1;
      }

      var cs = fleets.fishing.counts, max = Math.max.apply(null, cs) || 1;
      var y = function (t) { return bot - (cs[t] / max) * (bot - top); };
      ctx.beginPath();
      ctx.moveTo(0, bot);
      for (var t = 0; t < n; t++) ctx.lineTo(x(t), y(t));
      ctx.lineTo(tw, bot);
      ctx.closePath();
      ctx.globalAlpha = 0.28;
      ctx.fillStyle = C.accent;
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.beginPath();
      for (var t2 = 0; t2 < n; t2++) {
        if (t2 === 0) ctx.moveTo(x(t2), y(t2));
        else ctx.lineTo(x(t2), y(t2));
      }
      ctx.strokeStyle = C.accent;
      ctx.lineWidth = 1.2;
      ctx.stroke();

      ctx.fillStyle = C.label;
      ctx.font = "10px system-ui, sans-serif";
      ctx.textAlign = "left";
      for (var d = 0; d < n; d += 24) {
        ctx.strokeStyle = C.hairline;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x(d) + 0.5, bot);
        ctx.lineTo(x(d) + 0.5, bot + 4);
        ctx.stroke();
        if (tw > 520 || d % 48 === 0) {
          ctx.fillText(clockText(t0, d).split(" · ")[0]
            .replace(/(\w+) (\d+) \w+/, "$1 $2"), x(d) + 3, h - 2);
        }
      }

      ctx.strokeStyle = C.ink;
      ctx.lineWidth = 1.3;
      ctx.beginPath();
      ctx.moveTo(x(hour) + 0.5, top - 2);
      ctx.lineTo(x(hour) + 0.5, bot);
      ctx.stroke();

      // last, so the cursor never crosses out a band's name
      ctx.font = "11px system-ui, sans-serif";
      ctx.textAlign = "center";
      for (var b = 0; b < data.bands.length; b++) {
        ctx.fillStyle = data.bands[b][3] ? C.accent : C.label;
        ctx.fillText(data.bands[b][2],
          (x(data.bands[b][0]) + x(data.bands[b][1])) / 2, 11);
      }
    }

    function seek(t) {
      hour = Math.max(0, Math.min(data.hours - 1, t | 0));
      range.value = hour;
      draw();
      drawTime();
    }

    function tick(now) {
      if (timer === null) return;
      if (last) {
        acc += ((now - last) / 1000) * speed;
        if (acc >= 1) {
          var step = Math.floor(acc);
          acc -= step;
          seek(hour + step >= data.hours ? 0 : hour + step);
        }
      }
      last = now;
      timer = requestAnimationFrame(tick);
    }

    function play() {
      if (timer !== null) return;
      if (hour >= data.hours - 1) seek(0);
      last = 0;
      acc = 0;
      timer = requestAnimationFrame(tick);
      btn.textContent = "Pause";
      btn.setAttribute("aria-label", "Pause the storm");
    }

    function pause() {
      if (timer !== null) cancelAnimationFrame(timer);
      timer = null;
      btn.textContent = "Play";
      btn.setAttribute("aria-label", "Play the storm hour by hour");
    }

    function toggle() { timer === null ? play() : pause(); }

    btn.addEventListener("click", toggle);
    range.addEventListener("input", function () {
      pause();
      seek(+range.value);
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

    pause();
    layout();
    if (opts.autoplay && !reduce) play();

    return {
      play: play, pause: pause, toggle: toggle, seek: seek,
      hours: data.hours, element: root,
      destroy: function () {
        pause();
        if (ro) ro.disconnect();
        else global.removeEventListener("resize", layout);
        if (mqDark && mqDark.removeEventListener) {
          mqDark.removeEventListener("change", onTheme);
        }
        host.innerHTML = "";
      }
    };
  }

  global.SeafolkStorm = { mount: mount };
})(window);
