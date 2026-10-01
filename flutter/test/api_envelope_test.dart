import 'dart:convert';

import 'package:brainstormer/core/network/api_client.dart';
import 'package:brainstormer/core/network/auth_store.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// In-memory AuthStore: flutter_secure_storage has no test-platform
/// backend, so unit tests bypass the plugin entirely.
class FakeAuthStore extends AuthStore {
  FakeAuthStore() : super(storage: _FakeStorage());

  final _data = <String, String>{};

  @override
  Future<String?> readAccessToken() async => _data['a'];

  @override
  Future<String?> readRefreshToken() async => _data['r'];

  @override
  Future<void> saveSession({
    required String accessToken,
    required String refreshToken,
    Map<String, dynamic>? user,
    String? instanceId,
  }) async {
    _data['a'] = accessToken;
    _data['r'] = refreshToken;
  }

  @override
  Future<void> saveTokens(String access, String refresh) async {
    _data['a'] = access;
    _data['r'] = refresh;
  }

  @override
  Future<void> clear() async => _data.clear();
}

class _FakeStorage implements FlutterSecureStorage {
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

http.Response _ok(Map<String, dynamic> data) => http.Response(
      jsonEncode({'success': true, 'data': data}),
      200,
      headers: {'content-type': 'application/json'},
    );

http.Response _fail(String message, int status, {String? code}) {
  final body = <String, dynamic>{
    'success': false,
    'error': true,
    'message': message,
  };
  if (code != null) body['error_code'] = code;
  return http.Response(
    jsonEncode(body),
    status,
    headers: {'content-type': 'application/json'},
  );
}

void main() {
  group('ApiClient envelope', () {
    test('unwraps data on success', () async {
      final store = FakeAuthStore();
      await store.saveTokens('a', 'r');
      final client = ApiClient(
        baseUrl: 'http://x',
        store: store,
        httpClient: MockClient((_) async => _ok({'ideas': []})),
      );
      final data = await client.get('/api/v1/ideas');
      expect((data as Map)['ideas'], isEmpty);
    });

    test('throws with message and error_code on failure', () async {
      final store = FakeAuthStore();
      await store.saveTokens('a', 'r');
      final client = ApiClient(
        baseUrl: 'http://x',
        store: store,
        httpClient: MockClient(
            (_) async => _fail('Illegal transition', 400, code: 'X')),
      );
      try {
        await client.get('/api/v1/ideas');
        fail('expected ApiException');
      } on ApiException catch (e) {
        expect(e.statusCode, 400);
        expect(e.errorCode, 'X');
      }
    });

    test('401 refreshes once and retries', () async {
      final store = FakeAuthStore();
      await store.saveTokens('old-a', 'old-r');
      var calls = 0;
      final client = ApiClient(
        baseUrl: 'http://x',
        store: store,
        httpClient: MockClient((request) async {
          calls++;
          if (request.url.path.endsWith('/refresh')) {
            return _ok(
                {'access_token': 'new-a', 'refresh_token': 'new-r'});
          }
          if (calls == 1) return _fail('expired', 401);
          return _ok({'me': true});
        }),
      );
      final data = await client.get('/api/v1/me');
      expect((data as Map)['me'], isTrue);
      expect(await store.readAccessToken(), 'new-a');
    });

    test('dead refresh clears the session', () async {
      final store = FakeAuthStore();
      await store.saveTokens('a', 'bad-r');
      final client = ApiClient(
        baseUrl: 'http://x',
        store: store,
        httpClient: MockClient((request) async {
          if (request.url.path.endsWith('/refresh')) {
            return _fail('expired', 401);
          }
          return _fail('expired', 401);
        }),
      );
      try {
        await client.get('/api/v1/me');
        fail('expected ApiException');
      } on ApiException catch (e) {
        expect(e.statusCode, 401);
      }
      expect(await store.readAccessToken(), isNull);
    });
  });
}
