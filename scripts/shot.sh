#!/usr/bin/env bash
# Screenshot a page under site/, and every figure on it, light and dark, wide
# and narrow.
#
#   scripts/shot.sh site/index.html            # the page and all its figures
#   scripts/shot.sh site/index.html i4 i7      # only these figures
#   SHOT_DIR=/tmp/shots scripts/shot.sh site/index.html
#   SHOT_QUERY='storm=Pia' SHOT_NAME=pia scripts/shot.sh site/index.html i4
#
# Output goes to $SHOT_DIR, or to a fresh mktemp -d whose path is printed last.
# Screenshots are never committed.
#
# The browser is the Playwright headless shell already cached on this machine —
# no new dependency, no node, no playwright install. It can screenshot a page
# but it cannot crop to an element, so site/js/kit.js gives every page two query
# parameters instead:
#   ?only=<figure id>  hides everything but that figure
#   ?theme=dark        forces the dark tokens from site/css/site.css
# $SHOT_QUERY is appended to both, for a page parameter that changes what is on
# screen — site/index.html reads ?storm=<name>, so the storm chart can be
# photographed for a storm that is not the one it opens on. $SHOT_NAME then
# keeps those files apart from the default ones.
# The second is why --force-dark-mode is not used: that flag repaints the page
# with the browser's own inverted colours, which is not the palette the
# stylesheet defines and not what a reader in dark mode would see.
#
# --virtual-time-budget lets the page's clock run fast and the shell exit as
# soon as it is idle, so D3 has finished drawing before the shutter.
set -euo pipefail
cd "$(dirname "$0")/.."

page="${1:?usage: scripts/shot.sh site/<page>.html [figure-id …]}"
shift
[ -f "$page" ] || { echo "no such page: $page" >&2; exit 1; }

shell=$(ls -d "$HOME"/Library/Caches/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-mac-arm64/chrome-headless-shell 2>/dev/null | tail -1)
[ -x "$shell" ] || { echo "no cached Playwright headless shell under ~/Library/Caches/ms-playwright" >&2; exit 1; }

out="${SHOT_DIR:-$(mktemp -d)}"
mkdir -p "$out"
name="${SHOT_NAME:-$(basename "$page" .html)}"
url="file://$PWD/$page"
q="${SHOT_QUERY:+&$SHOT_QUERY}"

# the figures, in the order the page lists them, unless the caller named some.
# A named id that is not on the page is an error here: site/js/kit.js leaves the
# page alone rather than blanking it, but a caller who mistyped an id would
# otherwise get a full-page screenshot under a figure's file name.
figures=("$@")
# comments are stripped first: a figure parked in an HTML comment is not on the
# page and would screenshot as an empty frame.
available=$(perl -0777 -pe 's/<!--.*?-->//gs' "$page" |
              grep -o '<figure id="[^"]*"' | cut -d'"' -f2)
for id in ${figures[@]+"${figures[@]}"}; do   # macOS bash 3.2: an empty array is "unbound" under set -u
  grep -qxF "$id" <<<"$available" || {
    echo "no <figure id=\"$id\"> on $page; it has:" >&2
    sed 's/^/  /' <<<"$available" >&2
    exit 1
  }
done
if [ ${#figures[@]} -eq 0 ]; then
  while read -r id; do figures+=("$id"); done <<<"$available"
fi

shoot() {  # <file stem> <width> <height> <query>
  "$shell" --headless --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
    --virtual-time-budget=6000 --window-size="$2,$3" \
    --screenshot="$out/$1.png" "$url$4" >/dev/null 2>&1
  echo "  $out/$1.png"
}

for theme in light dark; do
  # the whole-page shots need a window as tall as the page: the headless shell
  # captures the viewport, not the document.
  shoot "$name-page-1280-$theme" 1280 9000 "?theme=$theme$q"
  shoot "$name-page-380-$theme"   380 16000 "?theme=$theme$q"
  for id in "${figures[@]}"; do
    shoot "$name-$id-1280-$theme" 1280 900 "?only=$id&theme=$theme$q"
    shoot "$name-$id-380-$theme"   380 900 "?only=$id&theme=$theme$q"
  done
done

echo "$out"
