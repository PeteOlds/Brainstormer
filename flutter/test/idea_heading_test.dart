import 'package:brainstormer/features/ideas/idea_detail_page.dart';
import 'package:brainstormer/features/ideas/idea_models.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('shared heading uses IDEA number and title', (tester) async {
    const idea = IdeaSummary(
      id: 'i1',
      referenceCode: 'IDEA-6031',
      promptTitle: 'Consistent heading',
      status: 'SPARK',
    );
    await tester.pumpWidget(
      const MaterialApp(home: Scaffold(body: IdeaHeading(idea: idea))),
    );
    expect(find.byKey(const Key('idea_consistent_heading')), findsOneWidget);
    expect(find.text('IDEA-6031: Consistent heading'), findsOneWidget);
  });
}
