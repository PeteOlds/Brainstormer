import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Secure token + identity store. Tokens never touch logs or analytics.
class AuthStore {
  AuthStore({FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  static const _accessKey = 'bs_access_token';
  static const _refreshKey = 'bs_refresh_token';
  static const _userKey = 'bs_user_json';
  static const _instanceKey = 'bs_instance_id';

  Future<String?> readAccessToken() => _storage.read(key: _accessKey);
  Future<String?> readRefreshToken() => _storage.read(key: _refreshKey);
  Future<String?> readInstanceId() => _storage.read(key: _instanceKey);

  Future<Map<String, dynamic>?> readUser() async {
    final raw = await _storage.read(key: _userKey);
    if (raw == null) return null;
    try {
      return jsonDecode(raw) as Map<String, dynamic>;
    } catch (_) {
      return null;
    }
  }

  Future<void> saveSession({
    required String accessToken,
    required String refreshToken,
    Map<String, dynamic>? user,
    String? instanceId,
  }) async {
    await _storage.write(key: _accessKey, value: accessToken);
    await _storage.write(key: _refreshKey, value: refreshToken);
    if (user != null) {
      await _storage.write(key: _userKey, value: jsonEncode(user));
    }
    if (instanceId != null) {
      await _storage.write(key: _instanceKey, value: instanceId);
    }
  }

  Future<void> saveTokens(String access, String refresh) async {
    await _storage.write(key: _accessKey, value: access);
    await _storage.write(key: _refreshKey, value: refresh);
  }

  Future<void> clear() => _storage.deleteAll();

  bool isAdmin(Map<String, dynamic>? user) =>
      (user?['role'] as String?) == 'ADMIN';
}
