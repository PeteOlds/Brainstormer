import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_client.dart';
import '../../core/network/outbox.dart';
import '../../core/providers.dart';
import 'idea_models.dart';
import 'ideas_repository.dart';

final ideasRepositoryProvider = Provider<IdeasRepository>(
  (ref) => IdeasRepository(api: ref.watch(apiClientProvider)),
);

class IdeasFilter {
  const IdeasFilter({
    this.status = 'ACTIVE_ONLY',
    this.sortBy = 'created_at',
    this.search = '',
    this.promptConfigId,
    this.model,
  });

  final String status;
  final String sortBy;
  final String search;

  /// Deep-link filters used by Activity and the prompt dashboard.
  final String? promptConfigId;
  final String? model;

  IdeasFilter copyWith({
    String? status,
    String? sortBy,
    String? search,
    String? promptConfigId,
    String? model,
    bool clearPrompt = false,
    bool clearModel = false,
  }) => IdeasFilter(
    status: status ?? this.status,
    sortBy: sortBy ?? this.sortBy,
    search: search ?? this.search,
    promptConfigId: clearPrompt
        ? null
        : (promptConfigId ?? this.promptConfigId),
    model: clearModel ? null : (model ?? this.model),
  );
}

class IdeasState {
  const IdeasState({
    this.items = const [],
    this.total = 0,
    this.page = 1,
    this.pages = 1,
    this.filter = const IdeasFilter(),
    this.loading = false,
    this.error,
  });

  final List<IdeaSummary> items;
  final int total;
  final int page;
  final int pages;
  final IdeasFilter filter;
  final bool loading;
  final String? error;

  IdeasState copyWith({
    List<IdeaSummary>? items,
    int? total,
    int? page,
    int? pages,
    IdeasFilter? filter,
    bool? loading,
    String? error,
  }) => IdeasState(
    items: items ?? this.items,
    total: total ?? this.total,
    page: page ?? this.page,
    pages: pages ?? this.pages,
    filter: filter ?? this.filter,
    loading: loading ?? this.loading,
    error: error,
  );
}

class IdeasController extends StateNotifier<IdeasState> {
  IdeasController(this._repo, this._ref) : super(const IdeasState());

  final IdeasRepository _repo;
  final Ref _ref;

  /// [fresh] bypasses the 60s GET cache. Use it when the list is re-shown
  /// after a screen that could have changed an idea (detail phase change,
  /// secondary action) — otherwise the cached page wins and the phase looks
  /// like it did not persist.
  Future<void> load({int? page, bool fresh = false}) async {
    final previousTotal = state.total;
    final firstLoad = state.items.isEmpty && previousTotal == 0;
    state = state.copyWith(loading: true, error: null);
    try {
      final result = await _repo.list(
        page: page ?? state.page,
        status: state.filter.status,
        sortBy: state.filter.sortBy,
        search: state.filter.search,
        promptConfigId: state.filter.promptConfigId,
        model: state.filter.model,
        fresh: fresh,
      );
      final total = result['total'] as int;
      state = state.copyWith(
        loading: false,
        items: (result['ideas'] as List<IdeaSummary>),
        total: total,
        pages: result['pages'] as int,
        page: page ?? state.page,
      );
      // Flush queued offline mutations once we know we're online.
      await flushOutbox();
      if (!firstLoad && total > previousTotal) {
        // Digest: new ideas arrived since the last load.
        try {
          await _ref
              .read(notificationServiceProvider)
              .showIdeaDigest(total - previousTotal);
        } catch (_) {
          // Best effort by design.
        }
      }
    } on ApiException catch (e) {
      state = state.copyWith(loading: false, error: e.message);
    }
  }

  void setFilter(IdeasFilter filter) {
    state = state.copyWith(filter: filter, page: 1);
    load(page: 1);
  }

  Future<void> vote(String id, int direction) async {
    try {
      final result = await _repo.vote(id, direction);
      // Apply the server's authoritative payload immediately (Jinja pattern).
      final items = state.items.map((i) {
        if (i.id != id) return i;
        return i.copyWith(
          netScore: result.netVotes,
          userVote: result.userVote,
          upvotes: result.upvotes,
          downvotes: result.downvotes,
        );
      }).toList();
      state = state.copyWith(items: items);
      await load(fresh: true);
    } on ApiException catch (e) {
      if (isNetworkFailure(e)) {
        _ref.read(outboxProvider.notifier).enqueue('POST', '/api/v1/ideas/$id/vote', {'direction': direction});
        state = state.copyWith(error: 'Offline — change queued and will retry.');
        return;
      }
      state = state.copyWith(error: e.message);
    }
  }

  /// Runs a mutation, queueing it offline on transport failure.
  /// Returns true when the server applied it now.
  Future<bool> _mutate({
    required String method,
    required String path,
    Map<String, dynamic>? body,
    required Future<void> Function() apply,
  }) async {
    try {
      await apply();
      await load(fresh: true);
      return true;
    } on ApiException catch (e) {
      if (isNetworkFailure(e)) {
        _ref.read(outboxProvider.notifier).enqueue(method, path, body);
        state = state.copyWith(
          error: 'Offline — change queued and will retry.',
        );
        return false;
      }
      state = state.copyWith(error: e.message);
      return false;
    }
  }

  Future<bool> postComment(String id, String body, {String? parentId}) async {
    final payload = <String, dynamic>{'body': body};
    final parent = parentId;
    if (parent != null) payload['parent_id'] = parent;
    return _mutate(
      method: 'POST',
      path: '/api/v1/ideas/$id/comments',
      body: payload,
      apply: () async {
        await _repo.postComment(id, body, parentId: parentId);
      },
    );
  }

  Future<int> flushOutbox() =>
      _ref.read(outboxProvider.notifier).flush().then((n) async {
        if (n > 0) await load();
        return n;
      });

  Future<bool> changeStatus(String id, String status) async {
    try {
      await _repo.changeStatus(id, status);
      await load();
      return true;
    } on ApiException catch (e) {
      state = state.copyWith(error: e.message);
      return false;
    }
  }

  /// Move several ideas at once. Returns the server summary (moved/skipped)
  /// or null on failure.
  Future<Map<String, dynamic>?> bulkStatus(
    List<String> ids,
    String status,
  ) async {
    if (ids.isEmpty) return null;
    try {
      final result = await _repo.bulkStatus(ids, status);
      await load();
      return result;
    } on ApiException catch (e) {
      state = state.copyWith(error: e.message);
      return null;
    }
  }
}

final ideasControllerProvider =
    StateNotifierProvider<IdeasController, IdeasState>(
      (ref) => IdeasController(ref.watch(ideasRepositoryProvider), ref),
    );
