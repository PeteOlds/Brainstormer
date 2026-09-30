import 'dart:convert';

import 'package:brainstormer/core/network/api_client.dart';
import 'package:brainstormer/core/providers.dart';
import 'package:brainstormer/features/auth/login_page.dart';
import 'package:brainstormer/features/ideas/ideas_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'api_envelope_test.dart' show FakeAuthStore;

http.Response _fail(String message, int status) => http.Response(
      jsonEncode({'success': false, 'error': true, 'message': message}),
      status,
      headers: {'content-type': 'application/json'},
    );

http.Response _sessionOk() => http.Response(
      jsonEncode({
        'success': true,
        'data': {
          'user': {
            'id': 'u1',
            'email': 'a@b.c',
            'role': 'ADMIN',
            'can_create_ideas': true
          },
          'access_token': 'a',
          'refresh_token': 'r',
        }
      }),
      200,
      headers: {'content-type': 'application/json'},
    );

Widget _harness(ApiClient client, FakeAuthStore store) => ProviderScope(
      overrides: [
        apiClientProvider.overrideWithValue(client),
        authStoreProvider.overrideWithValue(store),
      ],
      child: const MaterialApp(home: LoginPage()),
    );

void main() {
  testWidgets('failed login shows the error box', (tester) async {
    final store = FakeAuthStore();
    final client = ApiClient(
      baseUrl: 'http://x',
      store: store,
      httpClient: MockClient((_) async => _fail('Invalid credentials.', 401)),
    );
    await tester.pumpWidget(_harness(client, store));
    await tester.enterText(
        find.byKey(const Key('login_email')), 'a@b.c');
    await tester.enterText(find.byKey(const Key('login_password')), 'nope');
    await tester.tap(find.byKey(const Key('login_submit')));
    // Explicit pumps: the loading spinner animates forever, so
    // pumpAndSettle would never settle (see Guides/Guide_UITesting.md).
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    await tester.pump(const Duration(seconds: 1));
    expect(find.byKey(const Key('login_error')), findsOneWidget);
    expect(find.text('Invalid credentials.'), findsOneWidget);
  });

  testWidgets('successful login navigates to the instance picker',
      (tester) async {
    final store = FakeAuthStore();
    final client = ApiClient(
      baseUrl: 'http://x',
      store: store,
      httpClient: MockClient((request) async {
        if (request.url.path.endsWith('/instances')) {
          return http.Response(
              jsonEncode({
                'success': true,
                'data': {
                  'instances': [
                    {'id': 'i1', 'number': 5, 'name': 'Production'}
                  ]
                }
              }),
              200,
              headers: {'content-type': 'application/json'});
        }
        return _sessionOk();
      }),
    );
    await tester.pumpWidget(ProviderScope(
      overrides: [
        apiClientProvider.overrideWithValue(client),
        authStoreProvider.overrideWithValue(store),
      ],
      child: MaterialApp(
        home: const LoginPage(),
        routes: {
          '/instances': (_) => const Scaffold(
              body: Text('picker', key: Key('picker'))),
        },
      ),
    ));
    await tester.enterText(
        find.byKey(const Key('login_email')), 'a@b.c');
    await tester.enterText(
        find.byKey(const Key('login_password')), 'admin123');
    await tester.tap(find.byKey(const Key('login_submit')));
    for (var i = 0; i < 10; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
    expect(find.byKey(const Key('picker')), findsOneWidget);
  });

  testWidgets('status pill renders the state label', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: StatusPill(status: 'FREEZE')),
    ));
    expect(find.text('FREEZE'), findsOneWidget);
  });
}
