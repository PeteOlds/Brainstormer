import 'package:brainstormer/features/ideas/idea_models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('IdeaSummary', () {
    test('parses the list payload', () {
      final idea = IdeaSummary.fromJson({
        'id': 'abc',
        'reference_code': 'IDEA-0001',
        'prompt_title': 'P',
        'status': 'SPARK',
        'comments_count': 2,
        'upvotes_count': 3,
        'downvotes_count': 1,
        'net_score': 2,
        'user_vote': 1,
        'structured_content': {'elevator_pitch': 'Pitch!'},
        'actions_run': ['REFINE'],
      });
      expect(idea.referenceCode, 'IDEA-0001');
      expect(idea.summary, 'Pitch!');
      expect(idea.netScore, 2);
      expect(idea.userVote, 1);
      expect(idea.actionsRun, ['REFINE']);
    });

    test('falls back gracefully on sparse payloads', () {
      final idea = IdeaSummary.fromJson({'id': 'x'});
      expect(idea.status, 'SPARK');
      expect(idea.summary, isNull);
      expect(idea.commentCount, 0);
    });
  });

  group('allowedTransitions (client mirror)', () {
    test('matches the server matrix for key moves', () {
      expect(allowedTransitions['SPARK'], contains('SCOPE'));
      expect(allowedTransitions['SPARK'], isNot(contains('SHIP')));
      expect(allowedTransitions['SHIP'], contains('SCALE'));
      expect(allowedTransitions['ARCHIVE'], isEmpty);
      expect(ideaStatuses, hasLength(8));
    });
  });
}
