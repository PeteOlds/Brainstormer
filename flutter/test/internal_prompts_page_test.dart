import 'dart:convert';

import 'package:brainstormer/core/network/api_client.dart';
import 'package:brainstormer/core/providers.dart';
import 'package:brainstormer/features/admin/internal_prompts_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'api_envelope_test.dart' show FakeAuthStore;

http.Response _ok(Object data) => http.Response(
      jsonEncode({'success': true, 'data': data}),
      200,
      headers: {'content-type': 'application/json'},
    );

Widget _harness(ApiClient client, FakeAuthStore store) => ProviderScope(
      overrides: [
        apiClientProvider.overrideWithValue(client),
        authStoreProvider.overrideWithValue(store),
        currentUserProvider.overrideWith(
          (ref) => <String, dynamic>{'id': 'u1', 'role': 'ADMIN'},
        ),
      ],
      child: const MaterialApp(home: InternalPromptsPage()),
    );

void main() {
  testWidgets('lists shared prompts and shows the selected body', (tester) async {
    final store = FakeAuthStore();
    final client = ApiClient(
      baseUrl: 'http://x',
      store: store,
      httpClient: MockClient((request) async => _ok({
            'prompts': [
              {
                'key': 'strict_retry',
                'label': 'Strict JSON retry',
                'source': 'default',
                'body': 'Retry with \${ERRORS}',
                'default_body': 'Retry with \${ERRORS}',
                'required_placeholders': ['ERRORS'],
                'updated_at': null,
              }
            ]
          })),
    );

    await tester.pumpWidget(_harness(client, store));
    await tester.pumpAndSettle();

    expect(find.text('Strict JSON retry'), findsWidgets);
    expect(find.byKey(const Key('prompt_body')), findsOneWidget);
    expect(find.byKey(const Key('prompt_save')), findsOneWidget);
    expect(find.byKey(const Key('prompt_reset')), findsNothing);
  });
}
