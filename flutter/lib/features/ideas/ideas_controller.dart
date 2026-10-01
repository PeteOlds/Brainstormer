import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_client.dart';
import '../../core/network/outbox.dart';
import '../../core/providers.dart';
import 'idea_models.dart';
import 'ideas_repository.dart';

final ideasRepositoryProvider = Provider<IdeasRepository>(
    (ref) => IdeasRepository(api: ref.watch(apiClientProvider)));

class IdeasFilter {
  const IdeasFilter({
    this.status = 'ACTIVE_ONLY',
    this.sortBy = 'created_at',
    this.search = '',
  });

  final String status;
  final String sortBy;
  final String search;

  IdeasFilter copyWith({String? status, String? sortBy, String? search}) =>
      IdeasFilter(
        status: status ?? this.status,
        sortBy: sortBy ?? this.sortBy,
        search: search ?? this.search,
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
  }) =>
      IdeasState(
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

  Future<void> load({int? page}) async {
    final previousTotal = state.total;
    final firstLoad = state.items.isEmpty && previousTotal == 0;
    state = state.copyWith(loading: true, error: null);
    try {
      final result = await _repo.list(
        page: page ?? state.page,
        status: state.filter.status,
        sortBy: state.filter.sortBy,
        search: state.filter.search,
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
    await _mutate(
      method: 'POST',
      path: '/api/v1/ideas/$id/vote',
      body: {'direction': direction},
      apply: () => _repo.vote(id, direction),
    );
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
      await load();
      return true;
    } on ApiException catch (e) {
      if (isNetworkFailure(e)) {
        _ref.read(outboxProvider.notifier).enqueue(method, path, body);
        state = state.copyWith(
            error: 'Offline — change queued and will retry.');
        return false;
      }
      state = state.copyWith(error: e.message);
      return false;
    }
  }

  Future<bool> postComment(String id, String body,
      {String? parentId}) async {
    return _mutate(
      method: 'POST',
      path: '/api/v1/ideas/$id/comments',
      body: {
        'body': body,
        if (parentId != null) 'parent_id': parentId,
      },
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
}

final ideasControllerProvider =
    StateNotifierProvider<IdeasController, IdeasState>(
        (ref) => IdeasController(ref.watch(ideasRepositoryProvider), ref));
