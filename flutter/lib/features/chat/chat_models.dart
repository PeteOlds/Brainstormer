class ChatTurnModel {
  ChatTurnModel({
    required this.id,
    required this.role,
    required this.kind,
    required this.content,
  });

  final String id;
  final String role;
  final String kind;
  final String content;

  factory ChatTurnModel.fromJson(Map<String, dynamic> json) => ChatTurnModel(
        id: json['id'].toString(),
        role: (json['role'] ?? '').toString(),
        kind: (json['kind'] ?? 'chat').toString(),
        content: (json['content'] ?? '').toString(),
      );
}

class ChatSessionModel {
  ChatSessionModel({required this.id, this.turns = const []});

  final String id;
  final List<ChatTurnModel> turns;

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
