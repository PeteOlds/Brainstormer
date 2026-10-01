// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'chat_models.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

T _$identity<T>(T value) => value;

final _privateConstructorUsedError = UnsupportedError(
  'It seems like you constructed your class using `MyClass._()`. This constructor is only meant to be used by freezed and you are not supposed to need it nor use it.\nPlease check the documentation here for more information: https://github.com/rrousselGit/freezed#adding-getters-and-methods-to-our-models',
);

ChatTurnModel _$ChatTurnModelFromJson(Map<String, dynamic> json) {
  return _ChatTurnModel.fromJson(json);
}

/// @nodoc
mixin _$ChatTurnModel {
  String get id => throw _privateConstructorUsedError;
  String get role => throw _privateConstructorUsedError;
  String get kind => throw _privateConstructorUsedError;
  String get content => throw _privateConstructorUsedError;

  /// Serializes this ChatTurnModel to a JSON map.
  Map<String, dynamic> toJson() => throw _privateConstructorUsedError;

  /// Create a copy of ChatTurnModel
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  $ChatTurnModelCopyWith<ChatTurnModel> get copyWith =>
      throw _privateConstructorUsedError;
}

/// @nodoc
abstract class $ChatTurnModelCopyWith<$Res> {
  factory $ChatTurnModelCopyWith(
    ChatTurnModel value,
    $Res Function(ChatTurnModel) then,
  ) = _$ChatTurnModelCopyWithImpl<$Res, ChatTurnModel>;
  @useResult
  $Res call({String id, String role, String kind, String content});
}

/// @nodoc
class _$ChatTurnModelCopyWithImpl<$Res, $Val extends ChatTurnModel>
    implements $ChatTurnModelCopyWith<$Res> {
  _$ChatTurnModelCopyWithImpl(this._value, this._then);

  // ignore: unused_field
  final $Val _value;
  // ignore: unused_field
  final $Res Function($Val) _then;

  /// Create a copy of ChatTurnModel
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? id = null,
    Object? role = null,
    Object? kind = null,
    Object? content = null,
  }) {
    return _then(
      _value.copyWith(
            id: null == id
                ? _value.id
                : id // ignore: cast_nullable_to_non_nullable
                      as String,
            role: null == role
                ? _value.role
                : role // ignore: cast_nullable_to_non_nullable
                      as String,
            kind: null == kind
                ? _value.kind
                : kind // ignore: cast_nullable_to_non_nullable
                      as String,
            content: null == content
                ? _value.content
                : content // ignore: cast_nullable_to_non_nullable
                      as String,
          )
          as $Val,
    );
  }
}

/// @nodoc
abstract class _$$ChatTurnModelImplCopyWith<$Res>
    implements $ChatTurnModelCopyWith<$Res> {
  factory _$$ChatTurnModelImplCopyWith(
    _$ChatTurnModelImpl value,
    $Res Function(_$ChatTurnModelImpl) then,
  ) = __$$ChatTurnModelImplCopyWithImpl<$Res>;
  @override
  @useResult
  $Res call({String id, String role, String kind, String content});
}

/// @nodoc
class __$$ChatTurnModelImplCopyWithImpl<$Res>
    extends _$ChatTurnModelCopyWithImpl<$Res, _$ChatTurnModelImpl>
    implements _$$ChatTurnModelImplCopyWith<$Res> {
  __$$ChatTurnModelImplCopyWithImpl(
    _$ChatTurnModelImpl _value,
    $Res Function(_$ChatTurnModelImpl) _then,
  ) : super(_value, _then);

  /// Create a copy of ChatTurnModel
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? id = null,
    Object? role = null,
    Object? kind = null,
    Object? content = null,
  }) {
    return _then(
      _$ChatTurnModelImpl(
        id: null == id
            ? _value.id
            : id // ignore: cast_nullable_to_non_nullable
                  as String,
        role: null == role
            ? _value.role
            : role // ignore: cast_nullable_to_non_nullable
                  as String,
        kind: null == kind
            ? _value.kind
            : kind // ignore: cast_nullable_to_non_nullable
                  as String,
        content: null == content
            ? _value.content
            : content // ignore: cast_nullable_to_non_nullable
                  as String,
      ),
    );
  }
}

/// @nodoc
@JsonSerializable()
class _$ChatTurnModelImpl implements _ChatTurnModel {
  const _$ChatTurnModelImpl({
    required this.id,
    required this.role,
    required this.kind,
    required this.content,
  });

  factory _$ChatTurnModelImpl.fromJson(Map<String, dynamic> json) =>
      _$$ChatTurnModelImplFromJson(json);

  @override
  final String id;
  @override
  final String role;
  @override
  final String kind;
  @override
  final String content;

  @override
  String toString() {
    return 'ChatTurnModel(id: $id, role: $role, kind: $kind, content: $content)';
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is _$ChatTurnModelImpl &&
            (identical(other.id, id) || other.id == id) &&
            (identical(other.role, role) || other.role == role) &&
            (identical(other.kind, kind) || other.kind == kind) &&
            (identical(other.content, content) || other.content == content));
  }

  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  int get hashCode => Object.hash(runtimeType, id, role, kind, content);

  /// Create a copy of ChatTurnModel
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  @pragma('vm:prefer-inline')
  _$$ChatTurnModelImplCopyWith<_$ChatTurnModelImpl> get copyWith =>
      __$$ChatTurnModelImplCopyWithImpl<_$ChatTurnModelImpl>(this, _$identity);

  @override
  Map<String, dynamic> toJson() {
    return _$$ChatTurnModelImplToJson(this);
  }
}

abstract class _ChatTurnModel implements ChatTurnModel {
  const factory _ChatTurnModel({
    required final String id,
    required final String role,
    required final String kind,
    required final String content,
  }) = _$ChatTurnModelImpl;

  factory _ChatTurnModel.fromJson(Map<String, dynamic> json) =
      _$ChatTurnModelImpl.fromJson;

  @override
  String get id;
  @override
  String get role;
  @override
  String get kind;
  @override
  String get content;

  /// Create a copy of ChatTurnModel
  /// with the given fields replaced by the non-null parameter values.
  @override
  @JsonKey(includeFromJson: false, includeToJson: false)
  _$$ChatTurnModelImplCopyWith<_$ChatTurnModelImpl> get copyWith =>
      throw _privateConstructorUsedError;
}

ChatSessionModel _$ChatSessionModelFromJson(Map<String, dynamic> json) {
  return _ChatSessionModel.fromJson(json);
}

/// @nodoc
mixin _$ChatSessionModel {
  String get id => throw _privateConstructorUsedError;
  List<ChatTurnModel> get turns => throw _privateConstructorUsedError;

  /// Serializes this ChatSessionModel to a JSON map.
  Map<String, dynamic> toJson() => throw _privateConstructorUsedError;

  /// Create a copy of ChatSessionModel
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  $ChatSessionModelCopyWith<ChatSessionModel> get copyWith =>
      throw _privateConstructorUsedError;
}

/// @nodoc
abstract class $ChatSessionModelCopyWith<$Res> {
  factory $ChatSessionModelCopyWith(
    ChatSessionModel value,
    $Res Function(ChatSessionModel) then,
  ) = _$ChatSessionModelCopyWithImpl<$Res, ChatSessionModel>;
  @useResult
  $Res call({String id, List<ChatTurnModel> turns});
}

/// @nodoc
class _$ChatSessionModelCopyWithImpl<$Res, $Val extends ChatSessionModel>
    implements $ChatSessionModelCopyWith<$Res> {
  _$ChatSessionModelCopyWithImpl(this._value, this._then);

  // ignore: unused_field
  final $Val _value;
  // ignore: unused_field
  final $Res Function($Val) _then;

  /// Create a copy of ChatSessionModel
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({Object? id = null, Object? turns = null}) {
    return _then(
      _value.copyWith(
            id: null == id
                ? _value.id
                : id // ignore: cast_nullable_to_non_nullable
                      as String,
            turns: null == turns
                ? _value.turns
                : turns // ignore: cast_nullable_to_non_nullable
                      as List<ChatTurnModel>,
          )
          as $Val,
    );
  }
}

/// @nodoc
abstract class _$$ChatSessionModelImplCopyWith<$Res>
    implements $ChatSessionModelCopyWith<$Res> {
  factory _$$ChatSessionModelImplCopyWith(
    _$ChatSessionModelImpl value,
    $Res Function(_$ChatSessionModelImpl) then,
  ) = __$$ChatSessionModelImplCopyWithImpl<$Res>;
  @override
  @useResult
  $Res call({String id, List<ChatTurnModel> turns});
}

/// @nodoc
class __$$ChatSessionModelImplCopyWithImpl<$Res>
    extends _$ChatSessionModelCopyWithImpl<$Res, _$ChatSessionModelImpl>
    implements _$$ChatSessionModelImplCopyWith<$Res> {
  __$$ChatSessionModelImplCopyWithImpl(
    _$ChatSessionModelImpl _value,
    $Res Function(_$ChatSessionModelImpl) _then,
  ) : super(_value, _then);

  /// Create a copy of ChatSessionModel
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({Object? id = null, Object? turns = null}) {
    return _then(
      _$ChatSessionModelImpl(
        id: null == id
            ? _value.id
            : id // ignore: cast_nullable_to_non_nullable
                  as String,
        turns: null == turns
            ? _value._turns
            : turns // ignore: cast_nullable_to_non_nullable
                  as List<ChatTurnModel>,
      ),
    );
  }
}

/// @nodoc
@JsonSerializable()
class _$ChatSessionModelImpl implements _ChatSessionModel {
  const _$ChatSessionModelImpl({
    required this.id,
    final List<ChatTurnModel> turns = const [],
  }) : _turns = turns;

  factory _$ChatSessionModelImpl.fromJson(Map<String, dynamic> json) =>
      _$$ChatSessionModelImplFromJson(json);

  @override
  final String id;
  final List<ChatTurnModel> _turns;
  @override
  @JsonKey()
  List<ChatTurnModel> get turns {
    if (_turns is EqualUnmodifiableListView) return _turns;
    // ignore: implicit_dynamic_type
    return EqualUnmodifiableListView(_turns);
  }

  @override
  String toString() {
    return 'ChatSessionModel(id: $id, turns: $turns)';
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is _$ChatSessionModelImpl &&
            (identical(other.id, id) || other.id == id) &&
            const DeepCollectionEquality().equals(other._turns, _turns));
  }

  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  int get hashCode =>
      Object.hash(runtimeType, id, const DeepCollectionEquality().hash(_turns));

  /// Create a copy of ChatSessionModel
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  @pragma('vm:prefer-inline')
  _$$ChatSessionModelImplCopyWith<_$ChatSessionModelImpl> get copyWith =>
      __$$ChatSessionModelImplCopyWithImpl<_$ChatSessionModelImpl>(
        this,
        _$identity,
      );

  @override
  Map<String, dynamic> toJson() {
    return _$$ChatSessionModelImplToJson(this);
  }
}

abstract class _ChatSessionModel implements ChatSessionModel {
  const factory _ChatSessionModel({
    required final String id,
    final List<ChatTurnModel> turns,
  }) = _$ChatSessionModelImpl;

  factory _ChatSessionModel.fromJson(Map<String, dynamic> json) =
      _$ChatSessionModelImpl.fromJson;

  @override
  String get id;
  @override
  List<ChatTurnModel> get turns;

  /// Create a copy of ChatSessionModel
  /// with the given fields replaced by the non-null parameter values.
  @override
  @JsonKey(includeFromJson: false, includeToJson: false)
  _$$ChatSessionModelImplCopyWith<_$ChatSessionModelImpl> get copyWith =>
      throw _privateConstructorUsedError;
}
