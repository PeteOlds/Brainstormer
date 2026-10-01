// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'chat_models.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

_$ChatTurnModelImpl _$$ChatTurnModelImplFromJson(Map<String, dynamic> json) =>
    _$ChatTurnModelImpl(
      id: json['id'] as String,
      role: json['role'] as String,
      kind: json['kind'] as String,
      content: json['content'] as String,
    );

Map<String, dynamic> _$$ChatTurnModelImplToJson(_$ChatTurnModelImpl instance) =>
    <String, dynamic>{
      'id': instance.id,
      'role': instance.role,
      'kind': instance.kind,
      'content': instance.content,
    };

_$ChatSessionModelImpl _$$ChatSessionModelImplFromJson(
  Map<String, dynamic> json,
) => _$ChatSessionModelImpl(
  id: json['id'] as String,
  turns:
      (json['turns'] as List<dynamic>?)
          ?.map((e) => ChatTurnModel.fromJson(e as Map<String, dynamic>))
          .toList() ??
      const [],
);

Map<String, dynamic> _$$ChatSessionModelImplToJson(
  _$ChatSessionModelImpl instance,
) => <String, dynamic>{'id': instance.id, 'turns': instance.turns};
