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
set -euo pipefail

cd "$(dirname "$0")/../flutter"

if ! command -v flutter >/dev/null 2>&1; then
  echo "flutter not found on PATH. Install the Flutter SDK or add it to PATH." >&2
  exit 1
fi

flutter pub get
flutter build web --release --no-web-resources-cdn "$@"
