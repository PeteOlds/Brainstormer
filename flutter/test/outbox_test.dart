import 'dart:convert';

import 'package:brainstormer/core/network/api_client.dart';
import 'package:brainstormer/core/network/auth_store.dart';
import 'package:brainstormer/core/network/outbox.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'api_envelope_test.dart' show FakeAuthStore;

http.Response _ok() => http.Response(
      jsonEncode({'success': true, 'data': {}}),
      200,
      headers: {'content-type': 'application/json'},
    );

http.Response _fail() => http.Response('boom', 500);

void main() {
  Outbox boxFor(http.Client httpClient) {
    final store = FakeAuthStore();
    final api = ApiClient(
        baseUrl: 'http://x', store: store, httpClient: httpClient);
    return Outbox(api);
  }

  group('Outbox', () {
    test('flush applies queued mutations in order', () async {
      final seen = <String>[];
      final box = boxFor(MockClient((request) async {
        seen.add('${request.method} ${request.url.path}');
        return _ok();
      }));
      box.enqueue('POST', '/api/v1/ideas/a/vote', {'direction': 1});
      box.enqueue('POST', '/api/v1/ideas/a/comments', {'body': 'hi'});
      final applied = await box.flush();
      expect(applied, 2);
      expect(seen, [
        'POST /api/v1/ideas/a/vote',
        'POST /api/v1/ideas/a/comments',
      ]);
    });

    test('flush stops at first failure, preserving order', () async {
      var calls = 0;
      final box = boxFor(MockClient((_) async {
        calls++;
        return calls == 1 ? _ok() : _fail();
      }));
      box.enqueue('POST', '/a', null);
      box.enqueue('POST', '/b', null);
      box.enqueue('POST', '/c', null);
      // /b fails with a non-envelope 500: ApiClient throws (no stale).
      final applied = await box.flush();
      expect(applied, 1);
    });

    test('isNetworkFailure only matches transport errors', () {
      expect(isNetworkFailure(ApiException('x', statusCode: 0)), isTrue);
      expect(isNetworkFailure(ApiException('x', statusCode: 403)), isFalse);
      expect(isNetworkFailure(StateError('x')), isFalse);
    });

    test('outbox provider starts empty', () async {
      final container = ProviderContainer();
      addTearDown(container.dispose);
      expect(container.read(outboxProvider), isEmpty);
    });
  });

  group('AuthStore', () {
    test('anonymous admin check is false', () async {
      final store = FakeAuthStore();
      expect(store.isAdmin(null), isFalse);
      expect(store.isAdmin({'role': 'USER'}), isFalse);
      expect(store.isAdmin({'role': 'ADMIN'}), isTrue);
    });
  });
}
