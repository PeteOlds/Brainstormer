# Brainstormer Flutter client (Phase 7)

Web + mobile from one codebase (Riverpod). Replaces all Jinja/Alpine
pages; the Flask backend is API-only. Requires the V2 backend
(`VERSION` ≥ 0.36.0) and Dart ≥ 3.11 / Flutter ≥ 3.41.

```bash
# Install deps
flutter pub get

# Run against local backend
flutter run -d chrome --dart-define=API_BASE_URL=http://localhost:8000

# Static analysis + tests (gates: zero errors/warnings)
flutter analyze
flutter test

# Regenerate goldens (locked-OS Linux CI only, to avoid font drift)
flutter test --update-goldens test/golden_test.dart

# Release web build
flutter build web --release
```

## Conventions (enforced in review)

- Feature-first layout: `lib/features/<auth|ideas|chat|prompts|admin|settings>/`
  plus `lib/core/<network|theme|widgets>/`. The Flask app stays
  layer-based — do not restructure it to match.
- Backend contract first: strict `fromJson` models before UI
  (`Guide_ProjectOverview.md` §3). The `{success, data|message}`
  envelope is unwrapped in exactly one place (`ApiClient`).
- Dumb widgets, Riverpod controllers, single `ApiClient` with
  401 → refresh → retry. Tokens in `flutter_secure_storage`, never logs.
- Design tokens only (`core/theme/tokens.dart`): Inter, primary blue
  `#3B82F6/#2563EB`, 44px-equivalent touch targets, dark mode.
- Version parity: `pubspec.yaml` mirrors the backend `VERSION` file;
  both bump together. The build number renders in the app footer.
- Deep-link parity: `/ideas?status&prompt&model&idea`,
  `/admin/activity?run_status&model`, `/prompts?edit=` (via `Uri.base`
  on web bootstrap).
- Testing pyramid: unit (models, envelope, matrix) → widget (login
  flow, pills) → golden (shared chrome, git-tracked) → integration
  (`integration_test`, staging backend) — pytest keeps API behaviour,
  Flutter owns widget/visual.

## Offline + notifications

- GETs accept a TTL (`cacheFor`): fresh cache serves instantly,
  network failures fall back to stale cache, mutations invalidate by
  collection prefix. The shell shows an offline banner via
  `connectivity_plus` while cached content stays usable.
- Local notifications (`flutter_local_notifications`): new-idea digest
  on list growth, chat-reply alerts. No-op on unsupported platforms.
- Remote push (FCM) is pending Firebase project credentials and is
  deliberately NOT wired: adding `firebase_messaging` requires
  `google-services.json` / `GoogleService-Info.plist`, without which
  Android/iOS builds break. Follow-up when credentials exist:
  1. `flutterfire configure`, 2. backend device-token table +
  `POST /api/v1/devices`, 3. route `NotificationService` through FCM
  (call sites already centralised).
