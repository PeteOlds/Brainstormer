import 'dart:convert';

import 'package:brainstormer/core/network/api_client.dart';
import 'package:brainstormer/core/pipeline/pipeline_status_provider.dart';
import 'package:brainstormer/core/providers.dart';
import 'package:brainstormer/features/admin/activity_page.dart';
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

Map<String, dynamic> _emptyActivity() => {
      'performance': {'by_status': {}, 'per_model': []},
      'workers_alive': 1,
      'queues': {},
      'recent_runs': [],
      'pending_runs': [],
      'prompt_health': [],
      'recent_runs_pagination': {'page': 1, 'pages': 1, 'total': 0},
    };

Widget _harness(ApiClient client, FakeAuthStore store) => ProviderScope(
      overrides: [
        apiClientProvider.overrideWithValue(client),
        authStoreProvider.overrideWithValue(store),
        currentUserProvider.overrideWith(
          (ref) => <String, dynamic>{'id': 'u1', 'role': 'ADMIN'},
        ),
        pipelineStatusProvider.overrideWith(
          (ref) => Stream.value(PipelineStatusSnapshot.empty),
        ),
      ],
      child: const MaterialApp(home: AdminActivityPage()),
    );

void main() {
  testWidgets('recent runs can be filtered by idea number', (tester) async {
    final urls = <String>[];
    final store = FakeAuthStore();
    final client = ApiClient(
      baseUrl: 'http://x',
      store: store,
      httpClient: MockClient((request) async {
        urls.add(request.url.toString());
        return _ok(_emptyActivity());
      }),
    );

    await tester.pumpWidget(_harness(client, store));
    await tester.pumpAndSettle();

    final field = find.byKey(const Key('activity_idea_number_filter'));
    expect(field, findsOneWidget);
    await tester.enterText(field, 'IDEA-1001');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();

    expect(
      urls.any((url) => url.contains('idea_number=IDEA-1001')),
      isTrue,
      reason: 'Expected the idea filter to be sent to the activity API: $urls',
    );
    expect(find.byKey(const Key('activity_idea_filter')), findsOneWidget);

    await tester.tap(find.byKey(const Key('activity_clear_idea')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('activity_idea_filter')), findsNothing);
  });
}
