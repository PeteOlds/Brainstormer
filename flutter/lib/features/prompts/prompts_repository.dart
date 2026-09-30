import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_client.dart';
import '../../core/providers.dart';
import 'prompt_models.dart';

class PromptsRepository {
  PromptsRepository({required this.api});

  final ApiClient api;

  Future<List<PromptSummary>> list() async {
    final data = await api.get('/api/v1/prompts', query: {'limit': '100'});
    final list =
        ((data as Map<String, dynamic>)['prompts'] as List? ?? []);
    return [
      for (final e in list)
        PromptSummary.fromJson(e as Map<String, dynamic>)
    ];
  }

  Future<List<String>> ollamaModels() async {
    final data = await api.get('/api/v1/ollama/models');
    final list =
        ((data as Map<String, dynamic>)['models'] as List? ?? []);
    return [
      for (final e in list)
        (e is Map ? (e['name'] ?? e['model'] ?? e).toString() : e.toString())
    ];
  }

  Future<List<String>> providerModels(String provider) async {
    final data = await api
        .get('/api/v1/ollama/models', query: {'provider': provider});
    final list =
        ((data as Map<String, dynamic>)['models'] as List? ?? []);
    return [for (final e in list) e.toString()];
  }

  Future<void> save({
    String? id,
    required String title,
    required String body,
    required int intervalMinutes,
    required String modelName,
    required String provider,
    required bool isActive,
  }) async {
    final payload = {
      'title': title,
      'prompt_body': body,
      'interval_minutes': intervalMinutes,
      'model_name': modelName,
      'provider': provider,
      'is_active': isActive,
    };
    if (id == null) {
      await api.post('/api/v1/prompts', body: payload);
    } else {
      await api.patch('/api/v1/prompts/$id', body: payload);
    }
  }

  Future<void> runNow(String id, {int count = 1}) async {
    await api.post('/api/v1/prompts/$id/run-now', body: {'count': count});
  }

  Future<void> remove(String id) async {
    await api.delete('/api/v1/prompts/$id');
  }
}

final promptsRepositoryProvider = Provider<PromptsRepository>(
    (ref) => PromptsRepository(api: ref.watch(apiClientProvider)));

final promptsListProvider =
    FutureProvider.autoDispose<List<PromptSummary>>((ref) async {
  return ref.watch(promptsRepositoryProvider).list();
});
