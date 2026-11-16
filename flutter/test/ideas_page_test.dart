import 'dart:convert';

import 'package:brainstormer/core/network/api_client.dart';
import 'package:brainstormer/core/providers.dart';
import 'package:brainstormer/features/ideas/ideas_page.dart';
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

Map<String, dynamic> _idea(String id, String ref) => {
      'id': id,
      'reference_code': ref,
      'prompt_title': 'P',
      'status': 'SPARK',
      'net_score': 0,
      'comments_count': 0,
    };

Widget _harness(ApiClient client, FakeAuthStore store) => ProviderScope(
      overrides: [
        apiClientProvider.overrideWithValue(client),
        authStoreProvider.overrideWithValue(store),
        currentUserProvider.overrideWith(
            (ref) => <String, dynamic>{'id': 'u1', 'role': 'ADMIN'}),
      ],
      child: const MaterialApp(home: IdeasPage()),
    );

void main() {
  testWidgets('admin multi-selects ideas and changes status in one request',
      (tester) async {
    final store = FakeAuthStore();
    final bulkCalls = <Map<String, dynamic>>[];
    final client = ApiClient(
      baseUrl: 'http://x',
      store: store,
      httpClient: MockClient((request) async {
        if (request.url.path.endsWith('/bulk-status')) {
          bulkCalls.add(jsonDecode(request.body) as Map<String, dynamic>);
          return _ok({'moved': 2, 'skipped': [], 'status': 'SCOPE'});
        }
        return _ok({
          'ideas': [_idea('i1', 'IDEA-1'), _idea('i2', 'IDEA-2')],
          'total': 2,
          'pages': 1,
        });
      }),
    );

    await tester.pumpWidget(_harness(client, store));
    await tester.pumpAndSettle();

    // Enter selection mode: checkboxes replace the vote controls.
    await tester.tap(find.byKey(const Key('ideas_select_toggle')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('idea_select_i1')), findsOneWidget);

    await tester.tap(find.byKey(const Key('idea_select_i1')));
    await tester.tap(find.byKey(const Key('idea_select_i2')));
    await tester.pumpAndSettle();
    expect(find.text('2 selected'), findsWidgets);

    await tester.tap(find.byKey(const Key('ideas_bulk_status')));
    await tester.pumpAndSettle();
    // SPARK can move to SCOPE; the dialog lists legal targets only.
    await tester.tap(find.byKey(const Key('bulk_status_SCOPE')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('bulk_status_confirm')));
    await tester.pumpAndSettle();

    expect(bulkCalls, hasLength(1));
    expect(bulkCalls.single['idea_ids'], containsAll(<String>['i1', 'i2']));
    expect(bulkCalls.single['status'], 'SCOPE');
    // Selection mode closes after a successful move.
    expect(find.byKey(const Key('idea_select_i1')), findsNothing);
  });

  testWidgets('non-admins do not get the selection toggle', (tester) async {
    final store = FakeAuthStore();
    final client = ApiClient(
      baseUrl: 'http://x',
      store: store,
      httpClient: MockClient((_) async => _ok({
            'ideas': [_idea('i1', 'IDEA-1')],
            'total': 1,
            'pages': 1,
          })),
    );
    await tester.pumpWidget(ProviderScope(
      overrides: [
        apiClientProvider.overrideWithValue(client),
        authStoreProvider.overrideWithValue(store),
        currentUserProvider.overrideWith(
            (ref) => <String, dynamic>{'id': 'u2', 'role': 'USER'}),
      ],
      child: const MaterialApp(home: IdeasPage()),
    ));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('ideas_select_toggle')), findsNothing);
    expect(find.byKey(const Key('idea_select_i1')), findsNothing);
  });
}
