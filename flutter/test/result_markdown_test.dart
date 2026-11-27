import 'package:flutter_test/flutter_test.dart';
import 'package:brainstormer/core/utils/result_markdown.dart';

void main() {
  group('resultToMarkdown', () {
    test('renders legacy Brief sections as headings', () {
      final md = resultToMarkdown({
        'executive_summary': 'A clear summary.',
        'assumptions_risks': 'Dependencies and risks here.',
        'open_questions': ['Should ideas be deletable?'],
      });
      expect(md, contains('## Executive summary'));
      expect(md, contains('A clear summary.'));
      expect(md, contains('## Assumptions, dependencies and risks'));
      expect(md, contains('- Should ideas be deletable?'));
      expect(md, isNot(contains('{')));
    });

    test('renders typed design specs as readable bullets', () {
      final md = resultToMarkdown({
        'architecture': 'Flask API with SQLite.',
        'screen_specs': [
          {
            'name': 'IdeaList',
            'purpose': 'Browse ideas',
            'components': ['table', 'filters'],
            'states': ['loading', 'empty'],
          },
        ],
        'endpoint_specs': [
          {'method': 'GET', 'path': '/api/ideas', 'auth': 'JWT'},
        ],
      });
      expect(md, contains('## Screens (structured)'));
      expect(md, contains('- Name: IdeaList'));
      expect(md, contains('Components:'));
      expect(md, contains('table, filters'));
      expect(md, contains('## API contracts (structured)'));
      expect(md, contains('GET /api/ideas'));
    });

    test('title-cases unknown keys', () {
      final md = resultToMarkdown({'new_action_field': 'value'});
      expect(md, contains('## New Action Field'));
      expect(md, contains('value'));
    });

    test('handles empty output', () {
      expect(resultToMarkdown(null), 'No content.');
    });
  });
}
