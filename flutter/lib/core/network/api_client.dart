import 'dart:convert';

import 'package:http/http.dart' as http;

import 'auth_store.dart';

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
  }) : _http = httpClient ?? http.Client();

  final String baseUrl;
  final AuthStore store;
  final http.Client _http;

  Map<String, String> _headers(String? token) => {
        'Content-Type': 'application/json',
        if (token != null && token.isNotEmpty)
          'Authorization': 'Bearer $token',
      };

  /// Unwraps the {success, data|message} envelope. Throws ApiException
  /// on transport errors, envelope failures and auth expiry.
  Future<dynamic> request(
    String method,
    String path, {
    Map<String, String>? query,
    Map<String, dynamic>? body,
    bool retryAuth = true,
  }) async {
    final uri = Uri.parse('$baseUrl$path').replace(
      queryParameters: query?.isEmpty ?? true ? null : query,
    );
    final token = await store.readAccessToken();
    http.Response response;
    try {
      response = await _send(method, uri, token, body);
    } on Exception catch (e) {
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
    return _unwrap(response);
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

  Future<dynamic> get(String path, {Map<String, String>? query}) =>
      request('GET', path, query: query);
  Future<dynamic> post(String path, {Map<String, dynamic>? body}) =>
      request('POST', path, body: body);
  Future<dynamic> patch(String path, {Map<String, dynamic>? body}) =>
      request('PATCH', path, body: body);
  Future<dynamic> put(String path, {Map<String, dynamic>? body}) =>
      request('PUT', path, body: body);
  Future<dynamic> delete(String path) => request('DELETE', path);
}
