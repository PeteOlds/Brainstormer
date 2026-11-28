import 'package:brainstormer/core/providers.dart';
import 'package:brainstormer/core/widgets/site_header.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

Widget _header(Map<String, dynamic> user) => ProviderScope(
  overrides: [
    currentUserProvider.overrideWith((ref) => user),
    currentInstanceProvider.overrideWith((ref) => 'site-90'),
    currentInstanceLabelProvider.overrideWith((ref) => 'Site 90'),
  ],
  child: const MaterialApp(home: Scaffold(appBar: SiteHeader(title: 'Test'))),
);

void main() {
  testWidgets('standard user account menu hides Prompts', (tester) async {
    await tester.pumpWidget(_header({'id': 'u', 'role': 'USER'}));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Account'));
    await tester.pumpAndSettle();
    expect(find.text('Prompts'), findsNothing);
    expect(find.text('Ideas'), findsWidgets);
  });

  testWidgets('product manager account menu shows Prompts', (tester) async {
    await tester.pumpWidget(_header({
      'id': 'u',
      'role': 'USER',
      'product_manager_instance_ids': ['site-90'],
    }));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Account'));
    await tester.pumpAndSettle();
    expect(find.text('Prompts'), findsWidgets);
  });
}
