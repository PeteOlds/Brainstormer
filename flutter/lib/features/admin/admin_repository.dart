import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_client.dart';
import '../../core/providers.dart';

/// Admin surface: stats, prompt health, activity, users, settings.
class AdminRepository {
  AdminRepository({required this.api});

  final ApiClient api;

  Future<Map<String, dynamic>> stats() async {
    final data = await api.get('/api/v1/admin/stats');
    return (data as Map<String, dynamic>);
  }

  Future<Map<String, dynamic>> health() async {
    final data = await api.get('/api/ready');
    return (data as Map<String, dynamic>);
  }

  Future<Map<String, dynamic>> activity({
    int page = 1,
    String runStatus = '',
    String model = '',
    String jobType = 'all',
    int days = 30,
    String? promptId,
  }) async {
    final query = <String, String>{
      'page': '$page',
      'limit': '20',
      'days': '$days',
      'job_type': jobType,
    };
    if (runStatus.isNotEmpty) query['run_status'] = runStatus;
    if (model.isNotEmpty) query['model'] = model;
    if (promptId != null && promptId.isNotEmpty) query['prompt_id'] = promptId;
    final data = await api.get('/api/v1/admin/activity/stats', query: query);
    return (data as Map<String, dynamic>);
  }

  /// One prompt's dashboard: idea pipeline, run outcomes, timings, trends.
  Future<Map<String, dynamic>> promptStats(String promptId, {int days = 30}) async {
    final data = await api.get(
      '/api/v1/admin/prompts/$promptId/stats',
      query: {'days': '$days'},
    );
    return (data as Map<String, dynamic>);
  }

  Future<Map<String, dynamic>> instance(String instanceId) async {
    final data = await api.get('/api/v1/instances/$instanceId');
    return (data as Map<String, dynamic>)['instance'] as Map<String, dynamic>;
  }

  Future<List<Map<String, dynamic>>> promptHealth() async {
    final data = await api.get('/api/v1/admin/prompts/health');
    final list =
        ((data as Map<String, dynamic>)['prompts'] as List? ?? []);
    return [
      for (final e in list)
        (e as Map).map((k, v) => MapEntry(k.toString(), v))
    ];
  }

  Future<Map<String, dynamic>> settings() async {
    final data = await api.get('/api/v1/admin/settings');
    return (data as Map<String, dynamic>);
  }

  Future<void> updateAiConnections(Map<String, dynamic> value) async {
    await api.patch('/api/v1/admin/settings/ai_connections', body: value);
  }

  Future<List<Map<String, dynamic>>> aiConfigs(String instanceId) async {
    final data = await api.get('/api/v1/instances/$instanceId/ai-configs');
    final list =
        ((data as Map<String, dynamic>)['configs'] as List? ?? []);
    return [
      for (final e in list)
        (e as Map).map((k, v) => MapEntry(k.toString(), v))
    ];
  }

  Future<void> saveAiConfig(String instanceId, Map<String, dynamic> body) async {
    await api.put('/api/v1/instances/$instanceId/ai-configs', body: body);
  }

  /// Per-stage AI defaults. Stages without a row inherit provider settings.
  Future<List<Map<String, dynamic>>> stageConfigs(String instanceId) async {
    final data = await api.get(
      '/api/v1/instances/$instanceId/stage-config',
    );
    final list = ((data as Map<String, dynamic>)['stages'] as List? ?? []);
    return [
      for (final e in list)
        (e as Map).map((k, v) => MapEntry(k.toString(), v))
    ];
  }

  Future<void> saveStageConfig(
    String instanceId,
    Map<String, dynamic> body,
  ) async {
    await api.put(
      '/api/v1/instances/$instanceId/stage-config',
      body: body,
      invalidatePrefix: '/api/v1/instances/$instanceId/stage-config',
    );
  }

  /// Skills and guideline files available for stage defaults.
  Future<Map<String, List<Map<String, dynamic>>>> discovery() async {
    final data = await api.get('/api/v1/discovery');
    final map = data as Map<String, dynamic>;
    List<Map<String, dynamic>> rows(String key) => [
          for (final e in (map[key] as List? ?? []))
            if (e is Map) e.map((k, v) => MapEntry(k.toString(), v)),
        ];
    return {'skills': rows('skills'), 'guidelines': rows('guidelines')};
  }

  Future<Map<String, dynamic>> spend(String instanceId) async {
    final data = await api.get('/api/v1/instances/$instanceId/spend');
    return (data as Map<String, dynamic>);
  }

  Future<List<Map<String, dynamic>>> oauthConfigs(String instanceId) async {
    final data = await api.get('/api/v1/instances/$instanceId/oauth');
    final list =
        ((data as Map<String, dynamic>)['configs'] as List? ?? []);
    return [
      for (final e in list)
        (e as Map).map((k, v) => MapEntry(k.toString(), v))
    ];
  }

  Future<void> saveOauthConfig(String instanceId, Map<String, dynamic> body) async {
    await api.put('/api/v1/instances/$instanceId/oauth', body: body);
  }

  Future<List<Map<String, dynamic>>> members(String instanceId) async {
    final data = await api.get('/api/v1/instances/$instanceId/members');
    final list =
        ((data as Map<String, dynamic>)['members'] as List? ?? []);
    return [
      for (final e in list)
        (e as Map).map((k, v) => MapEntry(k.toString(), v))
    ];
  }
}

final adminRepositoryProvider = Provider<AdminRepository>(
    (ref) => AdminRepository(api: ref.watch(apiClientProvider)));

final adminStatsProvider = FutureProvider.autoDispose<Map<String, dynamic>>(
    (ref) async => ref.watch(adminRepositoryProvider).stats());

final adminHealthProvider = FutureProvider.autoDispose<Map<String, dynamic>>(
    (ref) async => ref.watch(adminRepositoryProvider).health());

final adminActivityProvider = FutureProvider.autoDispose<Map<String, dynamic>>(
    (ref) async => ref.watch(adminRepositoryProvider).activity());
