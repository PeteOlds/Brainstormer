import 'package:freezed_annotation/freezed_annotation.dart';

part 'idea_models.freezed.dart';
part 'idea_models.g.dart';

/// Strict domain models for ideas, comments and action results.
/// @freezed supplies value equality/copyWith; parsing stays hand-written
/// (null-tolerant backend contract) rather than generated.
@freezed
class IdeaSummary with _$IdeaSummary {
  const factory IdeaSummary({
    required String id,
    required String referenceCode,
    required String promptTitle,
    String? summary,
    required String status,
    String? promptConfigId,
    String? createdById,
    @Default(0) int commentCount,
    @Default(0) int upvotes,
    @Default(0) int downvotes,
    @Default(0) int netScore,
    int? userVote,
    String? createdAt,
    @Default([]) List<String> actionsRun,
  }) = _IdeaSummary;

  factory IdeaSummary.fromJson(Map<String, dynamic> json) => IdeaSummary(
        id: json['id'].toString(),
        referenceCode: (json['reference_code'] ?? '').toString(),
        promptTitle: (json['prompt_title'] ?? '').toString(),
        summary: json['summary']?.toString() ??
            json['excerpt']?.toString() ??
            _pickSummary(json['structured_content']),
        status: (json['status'] ?? 'SPARK').toString(),
        promptConfigId: json['prompt_config_id']?.toString(),
        createdById: json['created_by_id']?.toString(),
        commentCount: (json['comments_count'] as num?)?.toInt() ?? 0,
        upvotes: (json['upvotes_count'] as num?)?.toInt() ?? 0,
        downvotes: (json['downvotes_count'] as num?)?.toInt() ?? 0,
        netScore: (json['net_score'] as num?)?.toInt() ?? 0,
        userVote: (json['user_vote'] as num?)?.toInt(),
        createdAt: json['created_at']?.toString(),
        actionsRun: [
          for (final a in (json['actions_run'] as List? ?? [])) a.toString()
        ],
      );

  static String? _pickSummary(dynamic structured) {
    if (structured is Map<String, dynamic>) {
      for (final k in ['elevator_pitch', 'summary', 'pitch']) {
        final v = structured[k];
        if (v is String && v.trim().isNotEmpty) return v.trim();
      }
    }
    return null;
  }
}

@freezed
class IdeaDetail with _$IdeaDetail {
  const factory IdeaDetail({
    required IdeaSummary idea,
    @Default([]) List<ActionResult> actions,
    @Default([]) List<Map<String, dynamic>> editHistory,
  }) = _IdeaDetail;

  factory IdeaDetail.fromJson(Map<String, dynamic> json) {
    final ideaJson = json['idea'];
    return IdeaDetail(
      idea: IdeaSummary.fromJson(
          (ideaJson as Map<String, dynamic>?) ?? json),
      actions: [
        for (final a in (json['actions'] as List? ?? []))
          ActionResult.fromJson(a as Map<String, dynamic>)
      ],
      editHistory: [
        for (final e in (json['edit_history'] as List? ?? []))
          (e as Map).map((k, v) => MapEntry(k.toString(), v))
      ],
    );
  }
}

@freezed
class ActionResult with _$ActionResult {
  const factory ActionResult({
    required String id,
    required String actionType,
    @Default(1) int version,
    @Default(true) bool isCurrent,
    Map<String, dynamic>? output,
  }) = _ActionResult;

  factory ActionResult.fromJson(Map<String, dynamic> json) => ActionResult(
        id: json['id'].toString(),
        actionType: (json['action_type'] ?? '').toString(),
        version: (json['version'] as num?)?.toInt() ?? 1,
        isCurrent: json['is_current'] as bool? ?? true,
        output: json['output'] as Map<String, dynamic>?,
      );
}

@freezed
class IdeaComment with _$IdeaComment {
  const factory IdeaComment({
    required String id,
    required String body,
    String? author,
    String? parentId,
    String? phase,
    bool? isIgnored,
    String? createdAt,
    @Default([]) List<IdeaComment> replies,
  }) = _IdeaComment;

  factory IdeaComment.fromJson(Map<String, dynamic> json) => IdeaComment(
        id: json['id'].toString(),
        body: (json['body'] ?? '').toString(),
        author: json['author']?.toString(),
        parentId: json['parent_id']?.toString(),
        phase: json['phase']?.toString(),
        isIgnored: json['is_ignored'] as bool?,
        createdAt: json['created_at']?.toString(),
        replies: [
          for (final r in (json['replies'] as List? ?? []))
            IdeaComment.fromJson((r as Map).map((k, v) => MapEntry(k.toString(), v)))
        ],
      );
}

/// Client-side mirror of the server transition matrix (the server is
/// authoritative; this only greys out illegal targets early).
const Map<String, List<String>> allowedTransitions = {
  'SPARK': ['SCOPE', 'MAP', 'DROP', 'FREEZE'],
  'SCOPE': ['MAP', 'SHIP', 'DROP', 'FREEZE'],
  'MAP': ['SCOPE', 'SHIP', 'DROP', 'FREEZE', 'ARCHIVE'],
  'SHIP': ['SCOPE', 'MAP', 'SCALE', 'DROP', 'FREEZE', 'ARCHIVE'],
  'SCALE': ['SCOPE', 'MAP', 'SHIP', 'DROP', 'FREEZE', 'ARCHIVE'],
  'DROP': ['SCOPE', 'MAP', 'SHIP', 'SCALE', 'FREEZE', 'ARCHIVE'],
  'FREEZE': ['SCOPE', 'MAP', 'SHIP', 'SCALE', 'DROP', 'ARCHIVE'],
  'ARCHIVE': [],
};

const List<String> ideaStatuses = [
  'SPARK', 'SCOPE', 'MAP', 'SHIP', 'SCALE', 'DROP', 'FREEZE', 'ARCHIVE'
];
