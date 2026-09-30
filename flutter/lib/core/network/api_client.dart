import 'dart:convert';

import 'package:http/http.dart' as http;

import 'auth_store.dart';
import 'offline_cache.dart';

/// Backend error with the envelope message, HTTP status and optional
/// machine-readable error_code (e.g. CONFIRMATION_REQUIRED).
class ApiException implements Exception {
  ApiException(this.message, {required this.statusCode, this.errorCode});

  final String message;
  final int statusCode;
  final String? errorCode;

  @override
  String toString() => 'ApiException($statusCode): $message';
}

/// Single networking layer. Every request flows through here: Bearer
/// injection, one 401 → refresh → retry cycle, envelope unwrapping.
/// Never scatter raw `http` calls across features.
class ApiClient {
  ApiClient({
    required this.baseUrl,
    required this.store,
    http.Client? httpClient,
    OfflineCache? cache,
  })  : _http = httpClient ?? http.Client(),
        _cache = cache ?? OfflineCache();

  final String baseUrl;
  final AuthStore store;
  final http.Client _http;
  final OfflineCache _cache;

  Map<String, String> _headers(String? token) => {
        'Content-Type': 'application/json',
        if (token != null && token.isNotEmpty)
          'Authorization': 'Bearer $token',
      };

  /// Unwraps the {success, data|message} envelope. Throws ApiException
  /// on transport errors, envelope failures and auth expiry.
  ///
  /// GETs may pass [cacheFor]: fresh cache serves instantly, network
  /// failures fall back to stale cache, and any mutation invalidates
  /// the matching collection prefix.
  Future<dynamic> request(
    String method,
    String path, {
    Map<String, String>? query,
    Map<String, dynamic>? body,
    bool retryAuth = true,
    Duration? cacheFor,
    String? invalidatePrefix,
  }) async {
    final uri = Uri.parse('$baseUrl$path').replace(
      queryParameters: query?.isEmpty ?? true ? null : query,
    );
    final cacheKey =
        _cache.keyFor(method, path, uri.query);
    if (method == 'GET' && cacheFor != null) {
      final cached = _cache.get(cacheKey);
      if (cached != null) return cached;
    }
    final token = await store.readAccessToken();
    http.Response response;
    try {
      response = await _send(method, uri, token, body);
    } on Exception catch (e) {
      final stale = method == 'GET' ? _cache.getStale(cacheKey) : null;
      if (stale != null) return stale;
      throw ApiException('Network error: $e', statusCode: 0);
    }
    if (response.statusCode == 401 && retryAuth) {
      if (_isAnonymous(path)) {
        // Login/register/refresh failures are credential problems, not
        // session expiry: surface the server message, never refresh here
        // (refreshing the refresh endpoint itself would recurse).
        return _unwrap(response);
      }
      if (await _refresh()) {
        return request(method, path,
            query: query, body: body, retryAuth: false);
      }
      await store.clear();
      throw ApiException('Session expired. Please sign in again.',
          statusCode: 401);
    }
    if (invalidatePrefix != null) {
      _cache.invalidatePrefix(invalidatePrefix);
    }
    final data = _unwrap(response);
    if (method == 'GET' && cacheFor != null) {
      _cache.set(cacheKey, data, cacheFor);
    }
    return data;
  }

  static bool _isAnonymous(String path) =>
      path.endsWith('/login') ||
      path.endsWith('/register') ||
      path.endsWith('/refresh');

  Future<http.Response> _send(
      String method, Uri uri, String? token, Map<String, dynamic>? body) {
    final headers = _headers(token);
    final payload = body == null ? null : jsonEncode(body);
    switch (method.toUpperCase()) {
      case 'POST':
        return _http.post(uri, headers: headers, body: payload);
      case 'PATCH':
        return _http.patch(uri, headers: headers, body: payload);
      case 'DELETE':
        return _http.delete(uri, headers: headers);
      case 'PUT':
        return _http.put(uri, headers: headers, body: payload);
      default:
        return _http.get(uri, headers: headers);
    }
  }

  dynamic _unwrap(http.Response response) {
    dynamic decoded;
    try {
      decoded = jsonDecode(response.body);
    } catch (_) {
      decoded = null;
    }
    if (decoded is Map<String, dynamic>) {
      if (decoded['success'] == true) {
        return decoded.containsKey('data') ? decoded['data'] : decoded;
      }
      throw ApiException(
        (decoded['message'] ?? 'Request failed').toString(),
        statusCode: response.statusCode,
        errorCode: decoded['error_code']?.toString(),
      );
    }
    throw ApiException('Unexpected response (${response.statusCode}).',
        statusCode: response.statusCode);
  }

  /// Rotates the refresh token; true when the session continues.
  Future<bool> _refresh() async {
    final refresh = await store.readRefreshToken();
    if (refresh == null || refresh.isEmpty) return false;
    try {
      final response = await _http.post(
        Uri.parse('$baseUrl/api/v1/refresh'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'refresh_token': refresh}),
      );
      final decoded = jsonDecode(response.body);
      if (decoded is Map<String, dynamic> &&
          decoded['success'] == true &&
          decoded['data'] is Map<String, dynamic>) {
        final data = decoded['data'] as Map<String, dynamic>;
        final access = data['access_token']?.toString();
        final rotated = data['refresh_token']?.toString();
        if (access != null && rotated != null) {
          await store.saveTokens(access, rotated);
          return true;
        }
      }
    } catch (_) {
      // Fall through to false: caller clears the session.
    }
    return false;
  }

  Future<dynamic> get(String path,
          {Map<String, String>? query, Duration? cacheFor}) =>
      request('GET', path, query: query, cacheFor: cacheFor);
  Future<dynamic> post(String path,
          {Map<String, dynamic>? body, String? invalidatePrefix}) =>
      request('POST', path, body: body, invalidatePrefix: invalidatePrefix);
  Future<dynamic> patch(String path,
          {Map<String, dynamic>? body, String? invalidatePrefix}) =>
      request('PATCH', path, body: body, invalidatePrefix: invalidatePrefix);
  Future<dynamic> put(String path,
          {Map<String, dynamic>? body, String? invalidatePrefix}) =>
      request('PUT', path, body: body, invalidatePrefix: invalidatePrefix);
  Future<dynamic> delete(String path, {String? invalidatePrefix}) =>
      request('DELETE', path, invalidatePrefix: invalidatePrefix);

  /// Clears cached GETs (logout, instance switch).
  void clearCache() => _cache.invalidate();
}
