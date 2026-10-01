import 'package:freezed_annotation/freezed_annotation.dart';

part 'chat_models.freezed.dart';
part 'chat_models.g.dart';

@freezed
class ChatTurnModel with _$ChatTurnModel {
  const factory ChatTurnModel({
    required String id,
    required String role,
    required String kind,
    required String content,
  }) = _ChatTurnModel;

  factory ChatTurnModel.fromJson(Map<String, dynamic> json) => ChatTurnModel(
        id: json['id'].toString(),
        role: (json['role'] ?? '').toString(),
        kind: (json['kind'] ?? 'chat').toString(),
        content: (json['content'] ?? '').toString(),
      );
}

@freezed
class ChatSessionModel with _$ChatSessionModel {
  const factory ChatSessionModel({
    required String id,
    @Default([]) List<ChatTurnModel> turns,
  }) = _ChatSessionModel;

  factory ChatSessionModel.fromJson(Map<String, dynamic> json) =>
      ChatSessionModel(
        id: json['id'].toString(),
        turns: [
          for (final t in (json['turns'] as List? ?? []))
            ChatTurnModel.fromJson(
                (t as Map).map((k, v) => MapEntry(k.toString(), v)))
        ],
      );
}
