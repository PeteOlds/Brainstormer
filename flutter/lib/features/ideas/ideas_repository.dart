import '../../core/network/api_client.dart';
import 'idea_models.dart';

/// Ideas API surface. Paginated lists, detail, votes, comments, status,
/// secondary actions and chat — all through the shared ApiClient.
class IdeasRepository {
  IdeasRepository({required this.api});

  final ApiClient api;

  Future<Map<String, dynamic>> list({
    int page = 1,
    int limit = 20,
    String status = 'ACTIVE_ONLY',
    String sortBy = 'created_at',
    String? search,
    String? promptConfigId,
    String? model,
  }) async {
    final trimmedSearch = (search ?? '').trim();
    final data = await api.get('/api/v1/ideas',
        query: {
          'page': '$page',
          'limit': '$limit',
          'status': status,
          'sort_by': sortBy,
          if (trimmedSearch.isNotEmpty) 'search': trimmedSearch,
          if (promptConfigId case final p?) 'prompt_config_id': p,
          if (model case final m?) 'model': m,
        },
        cacheFor: const Duration(seconds: 60));
    final map = data as Map<String, dynamic>;
    return {
      'ideas': [
        for (final e in (map['ideas'] as List? ?? []))
          IdeaSummary.fromJson(e as Map<String, dynamic>)
      ],
      'total': map['total'] ?? 0,
      'pages': map['pages'] ?? 1,
    };
  }

  Future<IdeaDetail> detail(String id) async {
    final data = await api.get('/api/v1/ideas/$id');
    return IdeaDetail.fromJson(data as Map<String, dynamic>);
  }

  Future<Map<String, dynamic>> vote(String id, int direction) async {
    final data = await api.post('/api/v1/ideas/$id/vote',
        body: {'direction': direction},
        invalidatePrefix: '/api/v1/ideas');
    return (data as Map<String, dynamic>);
  }

  Future<IdeaSummary> create(String title, String content) async {
    final data = await api.post('/api/v1/ideas',
        body: {
          'prompt_title': title,
          'raw_content': content,
        },
        invalidatePrefix: '/api/v1/ideas') as Map<String, dynamic>;
    return IdeaSummary.fromJson(data);
  }

  Future<IdeaSummary> changeStatus(String id, String status) async {
    final data = await api.patch('/api/v1/ideas/$id/status',
        body: {'status': status}, invalidatePrefix: '/api/v1/ideas');
    // Status endpoint returns the bare idea (with user_vote); wrap leniently.
    final map = data as Map<String, dynamic>;
    final ideaJson = map.containsKey('idea')
        ? map['idea'] as Map<String, dynamic>
        : map;
    return IdeaSummary.fromJson(ideaJson);
  }

  Future<List<IdeaComment>> comments(String id, {String? phase}) async {
    final data = await api.get('/api/v1/ideas/$id/comments',
        query: phase == null ? null : {'phase': phase});
    final list = ((data as Map<String, dynamic>)['comments'] as List? ?? []);
    return [
      for (final e in list)
        IdeaComment.fromJson((e as Map).map((k, v) => MapEntry(k.toString(), v)))
    ];
  }

  Future<IdeaComment> postComment(String id, String body,
      {String? parentId}) async {
    final data = await api.post('/api/v1/ideas/$id/comments', body: {
      'body': body,
      if (parentId case final p?) 'parent_id': p,
    });
    final map = data as Map<String, dynamic>;
    final commentJson = (map['comment'] as Map?) ?? map;
    return IdeaComment.fromJson(
        commentJson.map((k, v) => MapEntry(k.toString(), v)));
  }

  Future<Map<String, dynamic>> runAction(String id, String actionType,
      {bool confirm = false}) async {
    final data = await api.post('/api/v1/ideas/$id/actions',
        body: {'action_type': actionType, 'confirm': confirm});
    return data as Map<String, dynamic>;
  }

  Future<List<Map<String, dynamic>>> actions() async {
    final data = await api.get('/api/v1/actions');
    return [
      for (final e in ((data as Map<String, dynamic>)['actions'] as List? ?? []))
        (e as Map).map((k, v) => MapEntry(k.toString(), v))
    ];
  }
}
