import 'package:brainstormer/core/providers.dart';
import 'package:brainstormer/core/widgets/app_shell.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

Widget _shell(String role) => ProviderScope(
  overrides: [
    currentUserProvider.overrideWith(
      (ref) => <String, dynamic>{'id': 'u', 'role': role},
    ),
  ],
  child: const MaterialApp(
    home: AppShell(title: 'Ideas', child: SizedBox()),
  ),
);

void main() {
  testWidgets('admins see the Admin destination but no Settings nav', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(_shell('ADMIN'));
    await tester.pumpAndSettle();

    expect(find.text('Ideas'), findsWidgets);
    expect(find.text('Admin'), findsOneWidget);
    // Instance settings is reached through Admin, never as a second
    // top-level entry (it used to appear twice: header and drawer).
    expect(find.text('Settings'), findsNothing);
  });

  testWidgets('regular users do not see the Admin destination', (tester) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(_shell('USER'));
    await tester.pumpAndSettle();

    expect(find.text('Ideas'), findsWidgets);
    expect(find.text('Admin'), findsNothing);
    expect(find.text('Settings'), findsNothing);
  });
}
