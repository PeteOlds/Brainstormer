import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_client.dart';
import '../../core/providers.dart';
import 'chat_models.dart';

class ChatRepository {
  ChatRepository({required this.api});

  final ApiClient api;

  Future<List<ChatSessionModel>> sessions(String ideaId) async {
    final data = await api.get('/api/v1/ideas/$ideaId/chat');
    final list =
        ((data as Map<String, dynamic>)['sessions'] as List? ?? []);
    return [
      for (final e in list)
        ChatSessionModel.fromJson(
            (e as Map).map((k, v) => MapEntry(k.toString(), v)))
    ];
  }

  Future<ChatTurnModel> send(String ideaId, String message) async {
    final data = await api.post('/api/v1/ideas/$ideaId/chat',
        body: {'message': message});
    final map = data as Map<String, dynamic>;
    final reply = map['reply'];
    return ChatTurnModel.fromJson(
        (reply as Map).map((k, v) => MapEntry(k.toString(), v)));
  }
}

final chatRepositoryProvider = Provider<ChatRepository>(
    (ref) => ChatRepository(api: ref.watch(apiClientProvider)));

final chatSessionsProvider = FutureProvider.family
    .autoDispose<List<ChatSessionModel>, String>((ref, ideaId) async {
  return ref.watch(chatRepositoryProvider).sessions(ideaId);
});
