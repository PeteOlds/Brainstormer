#!/usr/bin/env bash
# Build the Flutter web bundle that Flask serves at /.
#
# --no-web-resources-cdn is mandatory, not cosmetic. By default Flutter
# points CanvasKit at https://www.gstatic.com/flutter-canvaskit/... , but the
# app's Content-Security-Policy only allows same-origin scripts and
# connections (plus the fonts CDNs). The browser then blocks canvaskit.js and
# canvaskit.wasm and the app stays a blank page with console errors.
#
# With the flag, Flutter loads ./canvaskit/* from build/web/canvaskit, which
# is same-origin and works offline on a LAN.
#
# build/web is wiped first and the result is verified afterwards. A failed
# build (for example `flutter build web --wasm`, which this app cannot use)
# otherwise leaves a partial directory behind: index.html plus
# flutter_bootstrap.js pointing at gstatic, and no main.dart.js. Flask then
# serves index.html for the missing script and the browser reports
# "MIME type ('text/html') is not executable" on a blank page.
set -euo pipefail

cd "$(dirname "$0")/../flutter"

if ! command -v flutter >/dev/null 2>&1; then
  echo "flutter not found on PATH. Install the Flutter SDK or add it to PATH." >&2
  exit 1
fi

rm -rf build/web

flutter pub get
flutter build web --release --no-web-resources-cdn "$@"

missing=()
for artefact in index.html main.dart.js flutter_bootstrap.js canvaskit/canvaskit.wasm; do
  [[ -f "build/web/$artefact" ]] || missing+=("$artefact")
done
if (( ${#missing[@]} )); then
  echo "Incomplete web build — missing: ${missing[*]}" >&2
  exit 1
fi

# Same-origin CanvasKit only; the CDN variant is blocked by our CSP.
# `useLocalCanvasKit: false` makes the loader fetch canvaskit.wasm from
# www.gstatic.com, which the CSP refuses — a blank page with console errors.
if ! grep -q 'useLocalCanvasKit":true' build/web/flutter_bootstrap.js; then
  echo "build/web/flutter_bootstrap.js does not enable local CanvasKit; refusing to ship it." >&2
  exit 1
fi

echo "Web build OK (build/web)."
