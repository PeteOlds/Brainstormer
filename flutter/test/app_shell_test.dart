import 'package:brainstormer/core/providers.dart';
import 'package:brainstormer/core/widgets/app_shell.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

Widget _shell(String role) => ProviderScope(
      overrides: [
        currentUserProvider
            .overrideWith((ref) => <String, dynamic>{'id': 'u', 'role': role}),
      ],
      child: const MaterialApp(
        home: AppShell(title: 'Ideas', child: SizedBox()),
      ),
    );

void main() {
  testWidgets('admins see the Settings destination', (tester) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(_shell('ADMIN'));
    await tester.pumpAndSettle();

    expect(find.text('Ideas'), findsWidgets);
    expect(find.text('Settings'), findsOneWidget);
  });

  testWidgets('regular users do not see the Settings destination',
      (tester) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(_shell('USER'));
    await tester.pumpAndSettle();

    expect(find.text('Ideas'), findsWidgets);
    expect(find.text('Settings'), findsNothing);
  });
}
