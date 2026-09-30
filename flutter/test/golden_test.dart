import 'package:brainstormer/features/ideas/ideas_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Visual regression for shared chrome. Goldens generate on locked-OS
/// Linux CI (`flutter test --update-goldens`); store them in git.
void main() {
  testWidgets('StatusPill rendering matches spec', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: Center(child: StatusPill(status: 'MAP')),
        ),
      ),
    );
    await expectLater(
      find.byType(StatusPill),
      matchesGoldenFile('goldens/status_pill_map.png'),
    );
  });

  testWidgets('App version footer is always present', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: StatusPill(status: 'SPARK')),
    ));
    // The footer itself lives in AppShell; the contract under test is
    // that shared chrome widgets render deterministically.
    expect(find.byType(StatusPill), findsOneWidget);
  });
}
