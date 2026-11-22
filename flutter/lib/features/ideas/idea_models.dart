import 'package:freezed_annotation/freezed_annotation.dart';

part 'idea_models.freezed.dart';
part 'idea_models.g.dart';

/// Lenient numeric parsing. The backend contract is null-tolerant, and a
/// single bad field (e.g. a vote id where a count belongs) must never blank
/// the whole detail page.
int? _asInt(dynamic value) => value is num ? value.toInt() : null;

int _asIntOr(dynamic value, int fallback) => _asInt(value) ?? fallback;

bool? _asBool(dynamic value) => value is bool ? value : null;

Map<String, dynamic>? _asMap(dynamic value) =>
    value is Map ? value.map((k, v) => MapEntry(k.toString(), v)) : null;

List<dynamic> _asList(dynamic value) => value is List ? value : const [];

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
    String? instanceId,
    String? parentId,
    @Default(0) int commentCount,
    @Default(0) int upvotes,
    @Default(0) int downvotes,
    @Default(0) int netScore,
    int? userVote,
    String? createdAt,
    @Default([]) List<String> actionsRun,
    @Default(0) int pendingRuns,
  }) = _IdeaSummary;

  factory IdeaSummary.fromJson(Map<String, dynamic> json) => IdeaSummary(
    id: json['id'].toString(),
    referenceCode: (json['reference_code'] ?? '').toString(),
    promptTitle: (json['prompt_title'] ?? '').toString(),
    summary:
        json['summary']?.toString() ??
        json['excerpt']?.toString() ??
        _pickSummary(json['structured_content']),
    status: (json['status'] ?? 'SPARK').toString(),
    promptConfigId: json['prompt_config_id']?.toString(),
    createdById: json['created_by_id']?.toString(),
    instanceId: json['instance_id']?.toString(),
    parentId: json['parent_id']?.toString(),
    commentCount: _asIntOr(json['comments_count'], 0),
    upvotes: _asIntOr(json['upvotes_count'], 0),
    downvotes: _asIntOr(json['downvotes_count'], 0),
    netScore: _asIntOr(json['net_votes'] ?? json['net_score'], 0),
    userVote: _asInt(json['user_vote']),
    createdAt: json['created_at']?.toString(),
    actionsRun: [for (final a in _asList(json['actions_run'])) a.toString()],
    pendingRuns: _asIntOr(json['pending_runs'], 0),
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
    @Default([]) List<String> runningActions,
    @Default([]) List<Map<String, dynamic>> editHistory,
  }) = _IdeaDetail;

  factory IdeaDetail.fromJson(Map<String, dynamic> json) {
    final actions = <ActionResult>[];
    for (final a in _asList(json['actions'])) {
      final map = _asMap(a);
      if (map != null) actions.add(ActionResult.fromJson(map));
    }
    final edits = <Map<String, dynamic>>[];
    for (final e in _asList(json['edit_history'])) {
      final map = _asMap(e);
      if (map != null) edits.add(map);
    }
    return IdeaDetail(
      idea: IdeaSummary.fromJson(_asMap(json['idea']) ?? json),
      actions: actions,
      runningActions: [for (final a in _asList(json['running_actions'])) a.toString()],
      editHistory: edits,
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
    String? targetId,
    Map<String, dynamic>? output,
  }) = _ActionResult;

  factory ActionResult.fromJson(Map<String, dynamic> json) => ActionResult(
    id: json['id'].toString(),
    actionType: (json['action_type'] ?? '').toString(),
    version: _asIntOr(json['version'], 1),
    isCurrent: _asBool(json['is_current']) ?? true,
    targetId: json['target_id']?.toString(),
    output: _asMap(json['output']),
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
    isIgnored: _asBool(json['is_ignored']),
    createdAt: json['created_at']?.toString(),
    replies: [
      for (final r in _asList(json['replies']))
        IdeaComment.fromJson(
          (r as Map).map((k, v) => MapEntry(k.toString(), v)),
        ),
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
  'SPARK',
  'SCOPE',
  'MAP',
  'SHIP',
  'SCALE',
  'DROP',
  'FREEZE',
  'ARCHIVE',
];

/// Authoritative vote result returned by the server (Jinja applies
/// `payload.net_votes` / `payload.current_user_vote` directly).
class VoteResult {
  const VoteResult({
    required this.netVotes,
    this.userVote,
    this.upvotes = 0,
    this.downvotes = 0,
  });

  final int netVotes;
  final int? userVote;
  final int upvotes;
  final int downvotes;

  factory VoteResult.fromJson(Map<String, dynamic> json) => VoteResult(
        netVotes: _asIntOr(json['net_votes'] ?? json['net_score'], 0),
        userVote: _asInt(json['current_user_vote'] ?? json['user_vote']),
        upvotes: _asIntOr(json['upvotes_count'], 0),
        downvotes: _asIntOr(json['downvotes_count'], 0),
      );
}
