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

  Future<Map<String, dynamic>> activity() async {
    final data = await api.get('/api/v1/admin/activity/stats');
    return (data as Map<String, dynamic>);
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

final adminActivityProvider = FutureProvider.autoDispose<Map<String, dynamic>>(
    (ref) async => ref.watch(adminRepositoryProvider).activity());
