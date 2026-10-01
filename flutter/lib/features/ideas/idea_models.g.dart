// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'idea_models.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

_$IdeaSummaryImpl _$$IdeaSummaryImplFromJson(Map<String, dynamic> json) =>
    _$IdeaSummaryImpl(
      id: json['id'] as String,
      referenceCode: json['referenceCode'] as String,
      promptTitle: json['promptTitle'] as String,
      summary: json['summary'] as String?,
      status: json['status'] as String,
      promptConfigId: json['promptConfigId'] as String?,
      createdById: json['createdById'] as String?,
      commentCount: (json['commentCount'] as num?)?.toInt() ?? 0,
      upvotes: (json['upvotes'] as num?)?.toInt() ?? 0,
      downvotes: (json['downvotes'] as num?)?.toInt() ?? 0,
      netScore: (json['netScore'] as num?)?.toInt() ?? 0,
      userVote: (json['userVote'] as num?)?.toInt(),
      createdAt: json['createdAt'] as String?,
      actionsRun:
          (json['actionsRun'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          const [],
    );

Map<String, dynamic> _$$IdeaSummaryImplToJson(_$IdeaSummaryImpl instance) =>
    <String, dynamic>{
      'id': instance.id,
      'referenceCode': instance.referenceCode,
      'promptTitle': instance.promptTitle,
      'summary': instance.summary,
      'status': instance.status,
      'promptConfigId': instance.promptConfigId,
      'createdById': instance.createdById,
      'commentCount': instance.commentCount,
      'upvotes': instance.upvotes,
      'downvotes': instance.downvotes,
      'netScore': instance.netScore,
      'userVote': instance.userVote,
      'createdAt': instance.createdAt,
      'actionsRun': instance.actionsRun,
    };

_$ActionResultImpl _$$ActionResultImplFromJson(Map<String, dynamic> json) =>
    _$ActionResultImpl(
      id: json['id'] as String,
      actionType: json['actionType'] as String,
      version: (json['version'] as num?)?.toInt() ?? 1,
      isCurrent: json['isCurrent'] as bool? ?? true,
      output: json['output'] as Map<String, dynamic>?,
    );

Map<String, dynamic> _$$ActionResultImplToJson(_$ActionResultImpl instance) =>
    <String, dynamic>{
      'id': instance.id,
      'actionType': instance.actionType,
      'version': instance.version,
      'isCurrent': instance.isCurrent,
      'output': instance.output,
    };

_$IdeaCommentImpl _$$IdeaCommentImplFromJson(Map<String, dynamic> json) =>
    _$IdeaCommentImpl(
      id: json['id'] as String,
      body: json['body'] as String,
      author: json['author'] as String?,
      parentId: json['parentId'] as String?,
      phase: json['phase'] as String?,
      isIgnored: json['isIgnored'] as bool?,
      createdAt: json['createdAt'] as String?,
      replies:
          (json['replies'] as List<dynamic>?)
              ?.map((e) => IdeaComment.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const [],
    );

Map<String, dynamic> _$$IdeaCommentImplToJson(_$IdeaCommentImpl instance) =>
    <String, dynamic>{
      'id': instance.id,
      'body': instance.body,
      'author': instance.author,
      'parentId': instance.parentId,
      'phase': instance.phase,
      'isIgnored': instance.isIgnored,
      'createdAt': instance.createdAt,
      'replies': instance.replies,
    };
