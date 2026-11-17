// Custom Flutter bootstrap.
//
// The generated bootstrap registers flutter_service_worker.js, which caches
// the shell and engine artefacts in the browser. On a rebuild the old worker
// keeps serving the previous index.html / main.dart.js and the app stays
// blank until site data is cleared — exactly the failure mode we hit in
// production. This app is served from one origin over a LAN, so the service
// worker buys us nothing; load the build fresh every time.
{{flutter_js}}
{{flutter_build_config}}

_flutter.loader.load();
