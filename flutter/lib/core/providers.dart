import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

import 'notifications/notification_service.dart';
import 'network/api_client.dart';
import 'network/auth_store.dart';

/// Base URL override: `flutter run --dart-define=API_BASE_URL=https://…`.
///
/// On the web the app is served by the same Flask process that serves the
/// API, so requests go to the page origin (relative URLs) by default. A
/// baked-in host is a footgun for release bundles: one built with
/// `192.168.1.130` breaks on any other host and one built with the
/// `localhost:8000` default breaks on the LAN. `./scripts/build_web.sh`
/// therefore never sets this; the override stays available for `flutter run`.
/// Native builds always need an absolute URL.
const _configuredBaseUrl = String.fromEnvironment('API_BASE_URL');

final _apiBaseUrl = _configuredBaseUrl.isNotEmpty
    ? _configuredBaseUrl
    : (kIsWeb ? '' : 'http://localhost:8000');

final authStoreProvider = Provider<AuthStore>((ref) => AuthStore());

final apiClientProvider = Provider<ApiClient>((ref) {
  final instanceId = ref.watch(currentInstanceProvider);
  return ApiClient(
    baseUrl: _apiBaseUrl,
    store: ref.watch(authStoreProvider),
    httpClient: http.Client(),
    instanceId: instanceId,
  );
});

/// Signed-in user document (null when anonymous). Refreshed on login
/// and cleared on logout/expiry.
final currentUserProvider =
    StateProvider<Map<String, dynamic>?>((ref) => null);

/// Active instance id for scoped requests (null = unscoped legacy).
final currentInstanceProvider = StateProvider<String?>((ref) => null);

/// Human-readable label for the current instance (e.g. "Site 90 · Manual Test"), if known.
final currentInstanceLabelProvider = StateProvider<String?>((ref) => null);

final notificationServiceProvider = Provider<NotificationService>((ref) {
  final service = NotificationService();
  service.init();
  return service;
});
