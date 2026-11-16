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

    test('ignores a non-numeric user_vote instead of throwing', () {
      // Regression: the detail endpoint once sent the viewer's user id here.
      // Casting a UUID to num? crashed the whole detail page.
      final idea = IdeaSummary.fromJson({
        'id': 'a8ea58fa-821b-4c28-ace9-8963d122ba11',
        'user_vote': 'a8ea58fa-821b-4c28-ace9-8963d122ba11',
        'comments_count': '3',
        'net_score': 'oops',
      });
      expect(idea.userVote, isNull);
      expect(idea.commentCount, 0);
      expect(idea.netScore, 0);
    });
  });

  group('IdeaDetail', () {
    test('tolerates malformed sections', () {
      final detail = IdeaDetail.fromJson({
        'idea': {'id': 'x', 'reference_code': 'IDEA-1'},
        'actions': [
          1,
          {'id': 'a', 'action_type': 'REFINE', 'version': 'two'},
        ],
        'edit_history': 'not-a-list',
      });
      expect(detail.idea.referenceCode, 'IDEA-1');
      expect(detail.actions, hasLength(1));
      expect(detail.actions.single.version, 1);
      expect(detail.editHistory, isEmpty);
    });
  });

  group('freezed value semantics', () {
    test('equal payloads compare equal, copyWith diverges', () {
      final payload = {
        'id': 'x',
        'reference_code': 'IDEA-1',
        'prompt_title': 'P',
        'status': 'SPARK',
      };
      final a = IdeaSummary.fromJson(payload);
      final b = IdeaSummary.fromJson(Map<String, dynamic>.from(payload));
      expect(a, equals(b));
      expect(a.copyWith(status: 'MAP'), isNot(equals(a)));
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
