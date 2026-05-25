#!/usr/bin/env bash
# regenerate-banner.sh — re-render the Agent M brand banner PNGs from assets/banner.html
#
# Run whenever banner.html changes:
#   bash scripts/regenerate-banner.sh
#
# Renders 2 PNGs via headless Chrome:
#   assets/agent-m/banner-1600.png (1600×430, README hero size)
#   assets/agent-m/banner-3200.png (3200×860, retina/2x)
#
# The banner is a static brand asset — no release-version dependency.
# Reqs: a Chrome install (macOS, Linux apt, or Windows in Git Bash / MSYS).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BANNER_SRC="$REPO_ROOT/assets/banner.html"
OUT_DIR="$REPO_ROOT/assets/agent-m"

# ---------- detect headless Chrome (cross-platform) ----------
detect_chrome() {
  case "$(uname -s)" in
    Darwin)
      [ -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ] && \
        { echo "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"; return 0; }
      ;;
    Linux)
      for c in google-chrome google-chrome-stable chromium chromium-browser; do
        command -v "$c" >/dev/null 2>&1 && { command -v "$c"; return 0; }
      done
      ;;
    MINGW*|CYGWIN*|MSYS*)
      for c in "/c/Program Files/Google/Chrome/Application/chrome.exe" \
               "/c/Program Files (x86)/Google/Chrome/Application/chrome.exe"; do
        [ -x "$c" ] && { echo "$c"; return 0; }
      done
      ;;
  esac
  return 1
}

CHROME="$(detect_chrome)" || {
  echo "ERROR: headless Chrome not found." >&2
  echo "  macOS:   install Google Chrome from https://chrome.google.com/" >&2
  echo "  Linux:   apt install google-chrome-stable  OR  apt install chromium-browser" >&2
  echo "  Windows: install Chrome to default Program Files path" >&2
  exit 1
}

[ -f "$BANNER_SRC" ] || { echo "ERROR: banner source missing at $BANNER_SRC" >&2; exit 1; }

# ---------- render ----------
mkdir -p "$OUT_DIR"

render() {
  local w="$1" h="$2" out="$3"
  echo "Rendering ${w}×${h} → $out ..."
  # --virtual-time-budget gives Google Fonts (Inter Tight + JetBrains Mono) time to load
  # over the network before screenshot capture; without it the cream tagline plate
  # can render with missing mono-font glyphs.
  "$CHROME" \
    --headless --disable-gpu --hide-scrollbars \
    --window-size="$w,$h" \
    --virtual-time-budget=10000 \
    --default-background-color=00000000 \
    --screenshot="$out" \
    "file://$BANNER_SRC" 2>/dev/null
}

render 1600 430 "$OUT_DIR/banner-1600.png"
render 3200 860 "$OUT_DIR/banner-3200.png"

# Portable file-size readout
fsize() {
  if stat -f %z "$1" >/dev/null 2>&1; then stat -f %z "$1"
  else stat -c %s "$1"
  fi
}

echo ""
echo "Done."
echo "  $OUT_DIR/banner-1600.png ($(fsize "$OUT_DIR/banner-1600.png") bytes)"
echo "  $OUT_DIR/banner-3200.png ($(fsize "$OUT_DIR/banner-3200.png") bytes)"
echo ""
echo "Commit the regenerated banners alongside any banner.html design changes."
