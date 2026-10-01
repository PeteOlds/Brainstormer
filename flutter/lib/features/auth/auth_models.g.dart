// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'auth_models.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

_$AuthUserImpl _$$AuthUserImplFromJson(Map<String, dynamic> json) =>
    _$AuthUserImpl(
      id: json['id'] as String,
      email: json['email'] as String,
      name: json['name'] as String?,
      role: json['role'] as String,
      canCreateIdeas: json['canCreateIdeas'] as bool? ?? true,
    );

Map<String, dynamic> _$$AuthUserImplToJson(_$AuthUserImpl instance) =>
    <String, dynamic>{
      'id': instance.id,
      'email': instance.email,
      'name': instance.name,
      'role': instance.role,
      'canCreateIdeas': instance.canCreateIdeas,
    };

_$InstanceSummaryImpl _$$InstanceSummaryImplFromJson(
  Map<String, dynamic> json,
) => _$InstanceSummaryImpl(
  id: json['id'] as String,
  number: (json['number'] as num).toInt(),
  name: json['name'] as String,
);

Map<String, dynamic> _$$InstanceSummaryImplToJson(
  _$InstanceSummaryImpl instance,
) => <String, dynamic>{
  'id': instance.id,
  'number': instance.number,
  'name': instance.name,
};
