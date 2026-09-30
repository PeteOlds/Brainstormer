import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

import 'network/api_client.dart';
import 'network/auth_store.dart';

/// Base URL override: flutter run --dart-define=API_BASE_URL=https://…
const _apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://localhost:8000',
);

final authStoreProvider = Provider<AuthStore>((ref) => AuthStore());

final apiClientProvider = Provider<ApiClient>((ref) => ApiClient(
      baseUrl: _apiBaseUrl,
      store: ref.watch(authStoreProvider),
      httpClient: http.Client(),
    ));

/// Signed-in user document (null when anonymous). Refreshed on login
/// and cleared on logout/expiry.
final currentUserProvider =
    StateProvider<Map<String, dynamic>?>((ref) => null);

/// Active instance id for scoped requests (null = unscoped legacy).
final currentInstanceProvider = StateProvider<String?>((ref) => null);
