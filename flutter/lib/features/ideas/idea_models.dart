/// Strict domain models for ideas, comments and action results.
class IdeaSummary {
  IdeaSummary({
    required this.id,
    required this.referenceCode,
    required this.promptTitle,
    this.summary,
    required this.status,
    this.promptConfigId,
    this.createdById,
    this.commentCount = 0,
    this.upvotes = 0,
    this.downvotes = 0,
    this.netScore = 0,
    this.userVote,
    this.createdAt,
    this.actionsRun = const [],
  });

  final String id;
  final String referenceCode;
  final String promptTitle;
  final String? summary;
  final String status;
  final String? promptConfigId;
  final String? createdById;
  final int commentCount;
  final int upvotes;
  final int downvotes;
  final int netScore;
  final int? userVote;
  final String? createdAt;
  final List<String> actionsRun;

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

class IdeaDetail {
  IdeaDetail({required this.idea, this.actions = const [], this.editHistory = const []});

  final IdeaSummary idea;
  final List<ActionResult> actions;
  final List<Map<String, dynamic>> editHistory;

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

class ActionResult {
  ActionResult({
    required this.id,
    required this.actionType,
    this.version = 1,
    this.isCurrent = true,
    this.output,
  });

  final String id;
  final String actionType;
  final int version;
  final bool isCurrent;
  final Map<String, dynamic>? output;

  factory ActionResult.fromJson(Map<String, dynamic> json) => ActionResult(
        id: json['id'].toString(),
        actionType: (json['action_type'] ?? '').toString(),
        version: (json['version'] as num?)?.toInt() ?? 1,
        isCurrent: json['is_current'] as bool? ?? true,
        output: json['output'] as Map<String, dynamic>?,
      );
}

class IdeaComment {
  IdeaComment({
    required this.id,
    required this.body,
    this.author,
    this.parentId,
    this.phase,
    this.isIgnored,
    this.createdAt,
    this.replies = const [],
  });

  final String id;
  final String body;
  final String? author;
  final String? parentId;
  final String? phase;
  final bool? isIgnored;
  final String? createdAt;
  final List<IdeaComment> replies;

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
