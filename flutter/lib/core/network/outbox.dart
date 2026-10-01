import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../network/api_client.dart';
import '../providers.dart';

/// Offline outbox: failed mutations (network errors only, never
/// validation/auth failures) wait here and flush on the next
/// successful load. In-memory by design — a restart drops the queue
/// rather than replaying stale intents (documented tradeoff).
class PendingMutation {
  PendingMutation({
    required this.method,
    required this.path,
    this.body,
  });

  final String method;
  final String path;
  final Map<String, dynamic>? body;
}

class Outbox extends StateNotifier<List<PendingMutation>> {
  Outbox(this._api) : super(const []);

  final ApiClient _api;

  void enqueue(String method, String path,
      [Map<String, dynamic>? body]) {
    state = [
      ...state,
      PendingMutation(method: method, path: path, body: body)
    ];
  }

  /// Replays queued mutations in order. Stops at the first failure so
  /// ordering is preserved; returns applied count.
  Future<int> flush() async {
    var applied = 0;
    final remaining = <PendingMutation>[];
    for (final m in state) {
      try {
        await _api.request(m.method, m.path, body: m.body);
        applied++;
      } on ApiException {
        remaining.add(m);
        break;
      }
    }
    state = [...remaining, ...state.skip(applied + remaining.length)];
    return applied;
  }
}

final outboxProvider =
    StateNotifierProvider<Outbox, List<PendingMutation>>(
        (ref) => Outbox(ref.watch(apiClientProvider)));

/// True for transport failures (statusCode 0) — the only kind worth
/// queueing. Auth/validation errors must surface, never queue.
bool isNetworkFailure(Object e) =>
    e is ApiException && e.statusCode == 0;
