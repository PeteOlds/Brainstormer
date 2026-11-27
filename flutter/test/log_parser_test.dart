import 'package:flutter_test/flutter_test.dart';
import 'package:brainstormer/core/utils/log_parser.dart';

void main() {
  test('reads lines from the api_ok envelope', () {
    expect(
      logsFromPayload({'success': true, 'data': {'lines': ['one', 'two'], 'state': 'running'}}),
      'one\ntwo',
    );
  });

  test('reads an unwrapped lines payload', () {
    expect(logsFromPayload({'lines': ['a']}), 'a');
  });

  test('shows a friendly empty state', () {
    expect(logsFromPayload({'data': {'lines': []}}), 'No output yet.');
    expect(logsFromPayload(null), 'No output yet.');
  });
}
