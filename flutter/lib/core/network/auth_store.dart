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
  static const _instanceLabelKey = 'bs_instance_label';

  Future<String?> readAccessToken() => _storage.read(key: _accessKey);
  Future<String?> readRefreshToken() => _storage.read(key: _refreshKey);
  Future<String?> readInstanceId() => _storage.read(key: _instanceKey);
  Future<String?> readInstanceLabel() => _storage.read(key: _instanceLabelKey);

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
    String? instanceLabel,
  }) async {
    await _storage.write(key: _accessKey, value: accessToken);
    await _storage.write(key: _refreshKey, value: refreshToken);
    if (user != null) {
      await _storage.write(key: _userKey, value: jsonEncode(user));
    }
    if (instanceId != null) {
      await _storage.write(key: _instanceKey, value: instanceId);
    }
    if (instanceLabel != null) {
      await _storage.write(key: _instanceLabelKey, value: instanceLabel);
    }
  }

  Future<void> saveTokens(String access, String refresh) async {
    await _storage.write(key: _accessKey, value: access);
    await _storage.write(key: _refreshKey, value: refresh);
  }

  Future<void> clear() async {
    await _storage.delete(key: _accessKey);
    await _storage.delete(key: _refreshKey);
    await _storage.delete(key: _userKey);
    await _storage.delete(key: _instanceKey);
    await _storage.delete(key: _instanceLabelKey);
  }

  bool isAdmin(Map<String, dynamic>? user) {
    final role = user?['role'] as String?;
    if (role == 'ADMIN') return true;
    if (user?['is_site_admin'] == true) return true;
    final adminInstances = user?['admin_instance_ids'];
    if (adminInstances is List && adminInstances.isNotEmpty) return true;
    return false;
  }
}
