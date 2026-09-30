import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:integration_test/integration_test.dart';

/// Staging smoke: exercises the live API contract end to end with a
/// throwaway user (created and cleaned up by the test itself).
///
/// Run against a staging backend — never production:
///   flutter test integration_test/app_test.dart \
///     --dart-define=API_BASE_URL=https://staging.example.com
///
/// The backend under test needs an empty (or throwaway) database; the
/// test registers a unique user and deletes its comments afterwards.
const _baseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://localhost:8000',
);

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('staging auth + ideas + vote + comment flow',
      (tester) async {
    final stamp = DateTime.now().millisecondsSinceEpoch;
    final email = 'it-$stamp@example.com';
    const password = 'password123';

    Map<String, String> auth(String token) => {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        };

    dynamic decode(http.Response r) {
      expect(r.statusCode, lessThan(400),
          reason: '${r.request?.url} -> ${r.statusCode} ${r.body}');
      return jsonDecode(r.body)['data'];
    }

    // Register + login.
    var res = await http.post(
      Uri.parse('$_baseUrl/api/v1/register'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email, 'password': password}),
    );
    var data = decode(res) as Map<String, dynamic>;
    final token = data['access_token'] as String;

    // Me + ideas list (envelope parity with the unit-tested client).
    data = decode(await http.get(
      Uri.parse('$_baseUrl/api/v1/me'),
      headers: auth(token),
    )) as Map<String, dynamic>;
    expect(data['user']['email'], email);

    data = decode(await http.get(
      Uri.parse('$_baseUrl/api/v1/ideas?status=ACTIVE_ONLY&limit=5'),
      headers: auth(token),
    )) as Map<String, dynamic>;
    expect(data['ideas'], isList);

    // Create -> vote -> comment -> delete comment.
    data = decode(await http.post(
      Uri.parse('$_baseUrl/api/v1/ideas'),
      headers: auth(token),
      body: jsonEncode({
        'prompt_title': 'IT smoke $stamp',
        'raw_content': 'Created by flutter/integration_test, safe to ignore.',
      }),
    )) as Map<String, dynamic>;
    final ideaId = data['id'] as String;

    data = decode(await http.post(
      Uri.parse('$_baseUrl/api/v1/ideas/$ideaId/vote'),
      headers: auth(token),
      body: jsonEncode({'direction': 1}),
    )) as Map<String, dynamic>;
    expect(data['net_votes'], 1);

    data = decode(await http.post(
      Uri.parse('$_baseUrl/api/v1/ideas/$ideaId/comments'),
      headers: auth(token),
      body: jsonEncode({'body': 'IT smoke comment'}),
    )) as Map<String, dynamic>;
    final commentId = (data['comment'] as Map)['id'] as String;

    final del = await http.delete(
      Uri.parse('$_baseUrl/api/v1/comments/$commentId'),
      headers: auth(token),
    );
    expect(del.statusCode, lessThan(400));

    // Chat history endpoint is reachable (no generation asserted).
    data = decode(await http.get(
      Uri.parse('$_baseUrl/api/v1/ideas/$ideaId/chat'),
      headers: auth(token),
    )) as Map<String, dynamic>;
    expect(data['sessions'], isList);
  });
}
