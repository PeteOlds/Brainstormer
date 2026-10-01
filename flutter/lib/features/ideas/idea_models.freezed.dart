// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'idea_models.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

T _$identity<T>(T value) => value;

final _privateConstructorUsedError = UnsupportedError(
  'It seems like you constructed your class using `MyClass._()`. This constructor is only meant to be used by freezed and you are not supposed to need it nor use it.\nPlease check the documentation here for more information: https://github.com/rrousselGit/freezed#adding-getters-and-methods-to-our-models',
);

IdeaSummary _$IdeaSummaryFromJson(Map<String, dynamic> json) {
  return _IdeaSummary.fromJson(json);
}

/// @nodoc
mixin _$IdeaSummary {
  String get id => throw _privateConstructorUsedError;
  String get referenceCode => throw _privateConstructorUsedError;
  String get promptTitle => throw _privateConstructorUsedError;
  String? get summary => throw _privateConstructorUsedError;
  String get status => throw _privateConstructorUsedError;
  String? get promptConfigId => throw _privateConstructorUsedError;
  String? get createdById => throw _privateConstructorUsedError;
  int get commentCount => throw _privateConstructorUsedError;
  int get upvotes => throw _privateConstructorUsedError;
  int get downvotes => throw _privateConstructorUsedError;
  int get netScore => throw _privateConstructorUsedError;
  int? get userVote => throw _privateConstructorUsedError;
  String? get createdAt => throw _privateConstructorUsedError;
  List<String> get actionsRun => throw _privateConstructorUsedError;

  /// Serializes this IdeaSummary to a JSON map.
  Map<String, dynamic> toJson() => throw _privateConstructorUsedError;

  /// Create a copy of IdeaSummary
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  $IdeaSummaryCopyWith<IdeaSummary> get copyWith =>
      throw _privateConstructorUsedError;
}

/// @nodoc
abstract class $IdeaSummaryCopyWith<$Res> {
  factory $IdeaSummaryCopyWith(
    IdeaSummary value,
    $Res Function(IdeaSummary) then,
  ) = _$IdeaSummaryCopyWithImpl<$Res, IdeaSummary>;
  @useResult
  $Res call({
    String id,
    String referenceCode,
    String promptTitle,
    String? summary,
    String status,
    String? promptConfigId,
    String? createdById,
    int commentCount,
    int upvotes,
    int downvotes,
    int netScore,
    int? userVote,
    String? createdAt,
    List<String> actionsRun,
  });
}

/// @nodoc
class _$IdeaSummaryCopyWithImpl<$Res, $Val extends IdeaSummary>
    implements $IdeaSummaryCopyWith<$Res> {
  _$IdeaSummaryCopyWithImpl(this._value, this._then);

  // ignore: unused_field
  final $Val _value;
  // ignore: unused_field
  final $Res Function($Val) _then;

  /// Create a copy of IdeaSummary
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? id = null,
    Object? referenceCode = null,
    Object? promptTitle = null,
    Object? summary = freezed,
    Object? status = null,
    Object? promptConfigId = freezed,
    Object? createdById = freezed,
    Object? commentCount = null,
    Object? upvotes = null,
    Object? downvotes = null,
    Object? netScore = null,
    Object? userVote = freezed,
    Object? createdAt = freezed,
    Object? actionsRun = null,
  }) {
    return _then(
      _value.copyWith(
            id: null == id
                ? _value.id
                : id // ignore: cast_nullable_to_non_nullable
                      as String,
            referenceCode: null == referenceCode
                ? _value.referenceCode
                : referenceCode // ignore: cast_nullable_to_non_nullable
                      as String,
            promptTitle: null == promptTitle
                ? _value.promptTitle
                : promptTitle // ignore: cast_nullable_to_non_nullable
                      as String,
            summary: freezed == summary
                ? _value.summary
                : summary // ignore: cast_nullable_to_non_nullable
                      as String?,
            status: null == status
                ? _value.status
                : status // ignore: cast_nullable_to_non_nullable
                      as String,
            promptConfigId: freezed == promptConfigId
                ? _value.promptConfigId
                : promptConfigId // ignore: cast_nullable_to_non_nullable
                      as String?,
            createdById: freezed == createdById
                ? _value.createdById
                : createdById // ignore: cast_nullable_to_non_nullable
                      as String?,
            commentCount: null == commentCount
                ? _value.commentCount
                : commentCount // ignore: cast_nullable_to_non_nullable
                      as int,
            upvotes: null == upvotes
                ? _value.upvotes
                : upvotes // ignore: cast_nullable_to_non_nullable
                      as int,
            downvotes: null == downvotes
                ? _value.downvotes
                : downvotes // ignore: cast_nullable_to_non_nullable
                      as int,
            netScore: null == netScore
                ? _value.netScore
                : netScore // ignore: cast_nullable_to_non_nullable
                      as int,
            userVote: freezed == userVote
                ? _value.userVote
                : userVote // ignore: cast_nullable_to_non_nullable
                      as int?,
            createdAt: freezed == createdAt
                ? _value.createdAt
                : createdAt // ignore: cast_nullable_to_non_nullable
                      as String?,
            actionsRun: null == actionsRun
                ? _value.actionsRun
                : actionsRun // ignore: cast_nullable_to_non_nullable
                      as List<String>,
          )
          as $Val,
    );
  }
}

/// @nodoc
abstract class _$$IdeaSummaryImplCopyWith<$Res>
    implements $IdeaSummaryCopyWith<$Res> {
  factory _$$IdeaSummaryImplCopyWith(
    _$IdeaSummaryImpl value,
    $Res Function(_$IdeaSummaryImpl) then,
  ) = __$$IdeaSummaryImplCopyWithImpl<$Res>;
  @override
  @useResult
  $Res call({
    String id,
    String referenceCode,
    String promptTitle,
    String? summary,
    String status,
    String? promptConfigId,
    String? createdById,
    int commentCount,
    int upvotes,
    int downvotes,
    int netScore,
    int? userVote,
    String? createdAt,
    List<String> actionsRun,
  });
}

/// @nodoc
class __$$IdeaSummaryImplCopyWithImpl<$Res>
    extends _$IdeaSummaryCopyWithImpl<$Res, _$IdeaSummaryImpl>
    implements _$$IdeaSummaryImplCopyWith<$Res> {
  __$$IdeaSummaryImplCopyWithImpl(
    _$IdeaSummaryImpl _value,
    $Res Function(_$IdeaSummaryImpl) _then,
  ) : super(_value, _then);

  /// Create a copy of IdeaSummary
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? id = null,
    Object? referenceCode = null,
    Object? promptTitle = null,
    Object? summary = freezed,
    Object? status = null,
    Object? promptConfigId = freezed,
    Object? createdById = freezed,
    Object? commentCount = null,
    Object? upvotes = null,
    Object? downvotes = null,
    Object? netScore = null,
    Object? userVote = freezed,
    Object? createdAt = freezed,
    Object? actionsRun = null,
  }) {
    return _then(
      _$IdeaSummaryImpl(
        id: null == id
            ? _value.id
            : id // ignore: cast_nullable_to_non_nullable
                  as String,
        referenceCode: null == referenceCode
            ? _value.referenceCode
            : referenceCode // ignore: cast_nullable_to_non_nullable
                  as String,
        promptTitle: null == promptTitle
            ? _value.promptTitle
            : promptTitle // ignore: cast_nullable_to_non_nullable
                  as String,
        summary: freezed == summary
            ? _value.summary
            : summary // ignore: cast_nullable_to_non_nullable
                  as String?,
        status: null == status
            ? _value.status
            : status // ignore: cast_nullable_to_non_nullable
                  as String,
        promptConfigId: freezed == promptConfigId
            ? _value.promptConfigId
            : promptConfigId // ignore: cast_nullable_to_non_nullable
                  as String?,
        createdById: freezed == createdById
            ? _value.createdById
            : createdById // ignore: cast_nullable_to_non_nullable
                  as String?,
        commentCount: null == commentCount
            ? _value.commentCount
            : commentCount // ignore: cast_nullable_to_non_nullable
                  as int,
        upvotes: null == upvotes
            ? _value.upvotes
            : upvotes // ignore: cast_nullable_to_non_nullable
                  as int,
        downvotes: null == downvotes
            ? _value.downvotes
            : downvotes // ignore: cast_nullable_to_non_nullable
                  as int,
        netScore: null == netScore
            ? _value.netScore
            : netScore // ignore: cast_nullable_to_non_nullable
                  as int,
        userVote: freezed == userVote
            ? _value.userVote
            : userVote // ignore: cast_nullable_to_non_nullable
                  as int?,
        createdAt: freezed == createdAt
            ? _value.createdAt
            : createdAt // ignore: cast_nullable_to_non_nullable
                  as String?,
        actionsRun: null == actionsRun
            ? _value._actionsRun
            : actionsRun // ignore: cast_nullable_to_non_nullable
                  as List<String>,
      ),
    );
  }
}

/// @nodoc
@JsonSerializable()
class _$IdeaSummaryImpl implements _IdeaSummary {
  const _$IdeaSummaryImpl({
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
    final List<String> actionsRun = const [],
  }) : _actionsRun = actionsRun;

  factory _$IdeaSummaryImpl.fromJson(Map<String, dynamic> json) =>
      _$$IdeaSummaryImplFromJson(json);

  @override
  final String id;
  @override
  final String referenceCode;
  @override
  final String promptTitle;
  @override
  final String? summary;
  @override
  final String status;
  @override
  final String? promptConfigId;
  @override
  final String? createdById;
  @override
  @JsonKey()
  final int commentCount;
  @override
  @JsonKey()
  final int upvotes;
  @override
  @JsonKey()
  final int downvotes;
  @override
  @JsonKey()
  final int netScore;
  @override
  final int? userVote;
  @override
  final String? createdAt;
  final List<String> _actionsRun;
  @override
  @JsonKey()
  List<String> get actionsRun {
    if (_actionsRun is EqualUnmodifiableListView) return _actionsRun;
    // ignore: implicit_dynamic_type
    return EqualUnmodifiableListView(_actionsRun);
  }

  @override
  String toString() {
    return 'IdeaSummary(id: $id, referenceCode: $referenceCode, promptTitle: $promptTitle, summary: $summary, status: $status, promptConfigId: $promptConfigId, createdById: $createdById, commentCount: $commentCount, upvotes: $upvotes, downvotes: $downvotes, netScore: $netScore, userVote: $userVote, createdAt: $createdAt, actionsRun: $actionsRun)';
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is _$IdeaSummaryImpl &&
            (identical(other.id, id) || other.id == id) &&
            (identical(other.referenceCode, referenceCode) ||
                other.referenceCode == referenceCode) &&
            (identical(other.promptTitle, promptTitle) ||
                other.promptTitle == promptTitle) &&
            (identical(other.summary, summary) || other.summary == summary) &&
            (identical(other.status, status) || other.status == status) &&
            (identical(other.promptConfigId, promptConfigId) ||
                other.promptConfigId == promptConfigId) &&
            (identical(other.createdById, createdById) ||
                other.createdById == createdById) &&
            (identical(other.commentCount, commentCount) ||
                other.commentCount == commentCount) &&
            (identical(other.upvotes, upvotes) || other.upvotes == upvotes) &&
            (identical(other.downvotes, downvotes) ||
                other.downvotes == downvotes) &&
            (identical(other.netScore, netScore) ||
                other.netScore == netScore) &&
            (identical(other.userVote, userVote) ||
                other.userVote == userVote) &&
            (identical(other.createdAt, createdAt) ||
                other.createdAt == createdAt) &&
            const DeepCollectionEquality().equals(
              other._actionsRun,
              _actionsRun,
            ));
  }

  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  int get hashCode => Object.hash(
    runtimeType,
    id,
    referenceCode,
    promptTitle,
    summary,
    status,
    promptConfigId,
    createdById,
    commentCount,
    upvotes,
    downvotes,
    netScore,
    userVote,
    createdAt,
    const DeepCollectionEquality().hash(_actionsRun),
  );

  /// Create a copy of IdeaSummary
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  @pragma('vm:prefer-inline')
  _$$IdeaSummaryImplCopyWith<_$IdeaSummaryImpl> get copyWith =>
      __$$IdeaSummaryImplCopyWithImpl<_$IdeaSummaryImpl>(this, _$identity);

  @override
  Map<String, dynamic> toJson() {
    return _$$IdeaSummaryImplToJson(this);
  }
}

abstract class _IdeaSummary implements IdeaSummary {
  const factory _IdeaSummary({
    required final String id,
    required final String referenceCode,
    required final String promptTitle,
    final String? summary,
    required final String status,
    final String? promptConfigId,
    final String? createdById,
    final int commentCount,
    final int upvotes,
    final int downvotes,
    final int netScore,
    final int? userVote,
    final String? createdAt,
    final List<String> actionsRun,
  }) = _$IdeaSummaryImpl;

  factory _IdeaSummary.fromJson(Map<String, dynamic> json) =
      _$IdeaSummaryImpl.fromJson;

  @override
  String get id;
  @override
  String get referenceCode;
  @override
  String get promptTitle;
  @override
  String? get summary;
  @override
  String get status;
  @override
  String? get promptConfigId;
  @override
  String? get createdById;
  @override
  int get commentCount;
  @override
  int get upvotes;
  @override
  int get downvotes;
  @override
  int get netScore;
  @override
  int? get userVote;
  @override
  String? get createdAt;
  @override
  List<String> get actionsRun;

  /// Create a copy of IdeaSummary
  /// with the given fields replaced by the non-null parameter values.
  @override
  @JsonKey(includeFromJson: false, includeToJson: false)
  _$$IdeaSummaryImplCopyWith<_$IdeaSummaryImpl> get copyWith =>
      throw _privateConstructorUsedError;
}

/// @nodoc
mixin _$IdeaDetail {
  IdeaSummary get idea => throw _privateConstructorUsedError;
  List<ActionResult> get actions => throw _privateConstructorUsedError;
  List<Map<String, dynamic>> get editHistory =>
      throw _privateConstructorUsedError;

  /// Create a copy of IdeaDetail
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  $IdeaDetailCopyWith<IdeaDetail> get copyWith =>
      throw _privateConstructorUsedError;
}

/// @nodoc
abstract class $IdeaDetailCopyWith<$Res> {
  factory $IdeaDetailCopyWith(
    IdeaDetail value,
    $Res Function(IdeaDetail) then,
  ) = _$IdeaDetailCopyWithImpl<$Res, IdeaDetail>;
  @useResult
  $Res call({
    IdeaSummary idea,
    List<ActionResult> actions,
    List<Map<String, dynamic>> editHistory,
  });

  $IdeaSummaryCopyWith<$Res> get idea;
}

/// @nodoc
class _$IdeaDetailCopyWithImpl<$Res, $Val extends IdeaDetail>
    implements $IdeaDetailCopyWith<$Res> {
  _$IdeaDetailCopyWithImpl(this._value, this._then);

  // ignore: unused_field
  final $Val _value;
  // ignore: unused_field
  final $Res Function($Val) _then;

  /// Create a copy of IdeaDetail
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? idea = null,
    Object? actions = null,
    Object? editHistory = null,
  }) {
    return _then(
      _value.copyWith(
            idea: null == idea
                ? _value.idea
                : idea // ignore: cast_nullable_to_non_nullable
                      as IdeaSummary,
            actions: null == actions
                ? _value.actions
                : actions // ignore: cast_nullable_to_non_nullable
                      as List<ActionResult>,
            editHistory: null == editHistory
                ? _value.editHistory
                : editHistory // ignore: cast_nullable_to_non_nullable
                      as List<Map<String, dynamic>>,
          )
          as $Val,
    );
  }

  /// Create a copy of IdeaDetail
  /// with the given fields replaced by the non-null parameter values.
  @override
  @pragma('vm:prefer-inline')
  $IdeaSummaryCopyWith<$Res> get idea {
    return $IdeaSummaryCopyWith<$Res>(_value.idea, (value) {
      return _then(_value.copyWith(idea: value) as $Val);
    });
  }
}

/// @nodoc
abstract class _$$IdeaDetailImplCopyWith<$Res>
    implements $IdeaDetailCopyWith<$Res> {
  factory _$$IdeaDetailImplCopyWith(
    _$IdeaDetailImpl value,
    $Res Function(_$IdeaDetailImpl) then,
  ) = __$$IdeaDetailImplCopyWithImpl<$Res>;
  @override
  @useResult
  $Res call({
    IdeaSummary idea,
    List<ActionResult> actions,
    List<Map<String, dynamic>> editHistory,
  });

  @override
  $IdeaSummaryCopyWith<$Res> get idea;
}

/// @nodoc
class __$$IdeaDetailImplCopyWithImpl<$Res>
    extends _$IdeaDetailCopyWithImpl<$Res, _$IdeaDetailImpl>
    implements _$$IdeaDetailImplCopyWith<$Res> {
  __$$IdeaDetailImplCopyWithImpl(
    _$IdeaDetailImpl _value,
    $Res Function(_$IdeaDetailImpl) _then,
  ) : super(_value, _then);

  /// Create a copy of IdeaDetail
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? idea = null,
    Object? actions = null,
    Object? editHistory = null,
  }) {
    return _then(
      _$IdeaDetailImpl(
        idea: null == idea
            ? _value.idea
            : idea // ignore: cast_nullable_to_non_nullable
                  as IdeaSummary,
        actions: null == actions
            ? _value._actions
            : actions // ignore: cast_nullable_to_non_nullable
                  as List<ActionResult>,
        editHistory: null == editHistory
            ? _value._editHistory
            : editHistory // ignore: cast_nullable_to_non_nullable
                  as List<Map<String, dynamic>>,
      ),
    );
  }
}

/// @nodoc

class _$IdeaDetailImpl implements _IdeaDetail {
  const _$IdeaDetailImpl({
    required this.idea,
    final List<ActionResult> actions = const [],
    final List<Map<String, dynamic>> editHistory = const [],
  }) : _actions = actions,
       _editHistory = editHistory;

  @override
  final IdeaSummary idea;
  final List<ActionResult> _actions;
  @override
  @JsonKey()
  List<ActionResult> get actions {
    if (_actions is EqualUnmodifiableListView) return _actions;
    // ignore: implicit_dynamic_type
    return EqualUnmodifiableListView(_actions);
  }

  final List<Map<String, dynamic>> _editHistory;
  @override
  @JsonKey()
  List<Map<String, dynamic>> get editHistory {
    if (_editHistory is EqualUnmodifiableListView) return _editHistory;
    // ignore: implicit_dynamic_type
    return EqualUnmodifiableListView(_editHistory);
  }

  @override
  String toString() {
    return 'IdeaDetail(idea: $idea, actions: $actions, editHistory: $editHistory)';
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is _$IdeaDetailImpl &&
            (identical(other.idea, idea) || other.idea == idea) &&
            const DeepCollectionEquality().equals(other._actions, _actions) &&
            const DeepCollectionEquality().equals(
              other._editHistory,
              _editHistory,
            ));
  }

  @override
  int get hashCode => Object.hash(
    runtimeType,
    idea,
    const DeepCollectionEquality().hash(_actions),
    const DeepCollectionEquality().hash(_editHistory),
  );

  /// Create a copy of IdeaDetail
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  @pragma('vm:prefer-inline')
  _$$IdeaDetailImplCopyWith<_$IdeaDetailImpl> get copyWith =>
      __$$IdeaDetailImplCopyWithImpl<_$IdeaDetailImpl>(this, _$identity);
}

abstract class _IdeaDetail implements IdeaDetail {
  const factory _IdeaDetail({
    required final IdeaSummary idea,
    final List<ActionResult> actions,
    final List<Map<String, dynamic>> editHistory,
  }) = _$IdeaDetailImpl;

  @override
  IdeaSummary get idea;
  @override
  List<ActionResult> get actions;
  @override
  List<Map<String, dynamic>> get editHistory;

  /// Create a copy of IdeaDetail
  /// with the given fields replaced by the non-null parameter values.
  @override
  @JsonKey(includeFromJson: false, includeToJson: false)
  _$$IdeaDetailImplCopyWith<_$IdeaDetailImpl> get copyWith =>
      throw _privateConstructorUsedError;
}

ActionResult _$ActionResultFromJson(Map<String, dynamic> json) {
  return _ActionResult.fromJson(json);
}

/// @nodoc
mixin _$ActionResult {
  String get id => throw _privateConstructorUsedError;
  String get actionType => throw _privateConstructorUsedError;
  int get version => throw _privateConstructorUsedError;
  bool get isCurrent => throw _privateConstructorUsedError;
  Map<String, dynamic>? get output => throw _privateConstructorUsedError;

  /// Serializes this ActionResult to a JSON map.
  Map<String, dynamic> toJson() => throw _privateConstructorUsedError;

  /// Create a copy of ActionResult
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  $ActionResultCopyWith<ActionResult> get copyWith =>
      throw _privateConstructorUsedError;
}

/// @nodoc
abstract class $ActionResultCopyWith<$Res> {
  factory $ActionResultCopyWith(
    ActionResult value,
    $Res Function(ActionResult) then,
  ) = _$ActionResultCopyWithImpl<$Res, ActionResult>;
  @useResult
  $Res call({
    String id,
    String actionType,
    int version,
    bool isCurrent,
    Map<String, dynamic>? output,
  });
}

/// @nodoc
class _$ActionResultCopyWithImpl<$Res, $Val extends ActionResult>
    implements $ActionResultCopyWith<$Res> {
  _$ActionResultCopyWithImpl(this._value, this._then);

  // ignore: unused_field
  final $Val _value;
  // ignore: unused_field
  final $Res Function($Val) _then;

  /// Create a copy of ActionResult
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? id = null,
    Object? actionType = null,
    Object? version = null,
    Object? isCurrent = null,
    Object? output = freezed,
  }) {
    return _then(
      _value.copyWith(
            id: null == id
                ? _value.id
                : id // ignore: cast_nullable_to_non_nullable
                      as String,
            actionType: null == actionType
                ? _value.actionType
                : actionType // ignore: cast_nullable_to_non_nullable
                      as String,
            version: null == version
                ? _value.version
                : version // ignore: cast_nullable_to_non_nullable
                      as int,
            isCurrent: null == isCurrent
                ? _value.isCurrent
                : isCurrent // ignore: cast_nullable_to_non_nullable
                      as bool,
            output: freezed == output
                ? _value.output
                : output // ignore: cast_nullable_to_non_nullable
                      as Map<String, dynamic>?,
          )
          as $Val,
    );
  }
}

/// @nodoc
abstract class _$$ActionResultImplCopyWith<$Res>
    implements $ActionResultCopyWith<$Res> {
  factory _$$ActionResultImplCopyWith(
    _$ActionResultImpl value,
    $Res Function(_$ActionResultImpl) then,
  ) = __$$ActionResultImplCopyWithImpl<$Res>;
  @override
  @useResult
  $Res call({
    String id,
    String actionType,
    int version,
    bool isCurrent,
    Map<String, dynamic>? output,
  });
}

/// @nodoc
class __$$ActionResultImplCopyWithImpl<$Res>
    extends _$ActionResultCopyWithImpl<$Res, _$ActionResultImpl>
    implements _$$ActionResultImplCopyWith<$Res> {
  __$$ActionResultImplCopyWithImpl(
    _$ActionResultImpl _value,
    $Res Function(_$ActionResultImpl) _then,
  ) : super(_value, _then);

  /// Create a copy of ActionResult
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? id = null,
    Object? actionType = null,
    Object? version = null,
    Object? isCurrent = null,
    Object? output = freezed,
  }) {
    return _then(
      _$ActionResultImpl(
        id: null == id
            ? _value.id
            : id // ignore: cast_nullable_to_non_nullable
                  as String,
        actionType: null == actionType
            ? _value.actionType
            : actionType // ignore: cast_nullable_to_non_nullable
                  as String,
        version: null == version
            ? _value.version
            : version // ignore: cast_nullable_to_non_nullable
                  as int,
        isCurrent: null == isCurrent
            ? _value.isCurrent
            : isCurrent // ignore: cast_nullable_to_non_nullable
                  as bool,
        output: freezed == output
            ? _value._output
            : output // ignore: cast_nullable_to_non_nullable
                  as Map<String, dynamic>?,
      ),
    );
  }
}

/// @nodoc
@JsonSerializable()
class _$ActionResultImpl implements _ActionResult {
  const _$ActionResultImpl({
    required this.id,
    required this.actionType,
    this.version = 1,
    this.isCurrent = true,
    final Map<String, dynamic>? output,
  }) : _output = output;

  factory _$ActionResultImpl.fromJson(Map<String, dynamic> json) =>
      _$$ActionResultImplFromJson(json);

  @override
  final String id;
  @override
  final String actionType;
  @override
  @JsonKey()
  final int version;
  @override
  @JsonKey()
  final bool isCurrent;
  final Map<String, dynamic>? _output;
  @override
  Map<String, dynamic>? get output {
    final value = _output;
    if (value == null) return null;
    if (_output is EqualUnmodifiableMapView) return _output;
    // ignore: implicit_dynamic_type
    return EqualUnmodifiableMapView(value);
  }

  @override
  String toString() {
    return 'ActionResult(id: $id, actionType: $actionType, version: $version, isCurrent: $isCurrent, output: $output)';
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is _$ActionResultImpl &&
            (identical(other.id, id) || other.id == id) &&
            (identical(other.actionType, actionType) ||
                other.actionType == actionType) &&
            (identical(other.version, version) || other.version == version) &&
            (identical(other.isCurrent, isCurrent) ||
                other.isCurrent == isCurrent) &&
            const DeepCollectionEquality().equals(other._output, _output));
  }

  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  int get hashCode => Object.hash(
    runtimeType,
    id,
    actionType,
    version,
    isCurrent,
    const DeepCollectionEquality().hash(_output),
  );

  /// Create a copy of ActionResult
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  @pragma('vm:prefer-inline')
  _$$ActionResultImplCopyWith<_$ActionResultImpl> get copyWith =>
      __$$ActionResultImplCopyWithImpl<_$ActionResultImpl>(this, _$identity);

  @override
  Map<String, dynamic> toJson() {
    return _$$ActionResultImplToJson(this);
  }
}

abstract class _ActionResult implements ActionResult {
  const factory _ActionResult({
    required final String id,
    required final String actionType,
    final int version,
    final bool isCurrent,
    final Map<String, dynamic>? output,
  }) = _$ActionResultImpl;

  factory _ActionResult.fromJson(Map<String, dynamic> json) =
      _$ActionResultImpl.fromJson;

  @override
  String get id;
  @override
  String get actionType;
  @override
  int get version;
  @override
  bool get isCurrent;
  @override
  Map<String, dynamic>? get output;

  /// Create a copy of ActionResult
  /// with the given fields replaced by the non-null parameter values.
  @override
  @JsonKey(includeFromJson: false, includeToJson: false)
  _$$ActionResultImplCopyWith<_$ActionResultImpl> get copyWith =>
      throw _privateConstructorUsedError;
}

IdeaComment _$IdeaCommentFromJson(Map<String, dynamic> json) {
  return _IdeaComment.fromJson(json);
}

/// @nodoc
mixin _$IdeaComment {
  String get id => throw _privateConstructorUsedError;
  String get body => throw _privateConstructorUsedError;
  String? get author => throw _privateConstructorUsedError;
  String? get parentId => throw _privateConstructorUsedError;
  String? get phase => throw _privateConstructorUsedError;
  bool? get isIgnored => throw _privateConstructorUsedError;
  String? get createdAt => throw _privateConstructorUsedError;
  List<IdeaComment> get replies => throw _privateConstructorUsedError;

  /// Serializes this IdeaComment to a JSON map.
  Map<String, dynamic> toJson() => throw _privateConstructorUsedError;

  /// Create a copy of IdeaComment
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  $IdeaCommentCopyWith<IdeaComment> get copyWith =>
      throw _privateConstructorUsedError;
}

/// @nodoc
abstract class $IdeaCommentCopyWith<$Res> {
  factory $IdeaCommentCopyWith(
    IdeaComment value,
    $Res Function(IdeaComment) then,
  ) = _$IdeaCommentCopyWithImpl<$Res, IdeaComment>;
  @useResult
  $Res call({
    String id,
    String body,
    String? author,
    String? parentId,
    String? phase,
    bool? isIgnored,
    String? createdAt,
    List<IdeaComment> replies,
  });
}

/// @nodoc
class _$IdeaCommentCopyWithImpl<$Res, $Val extends IdeaComment>
    implements $IdeaCommentCopyWith<$Res> {
  _$IdeaCommentCopyWithImpl(this._value, this._then);

  // ignore: unused_field
  final $Val _value;
  // ignore: unused_field
  final $Res Function($Val) _then;

  /// Create a copy of IdeaComment
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? id = null,
    Object? body = null,
    Object? author = freezed,
    Object? parentId = freezed,
    Object? phase = freezed,
    Object? isIgnored = freezed,
    Object? createdAt = freezed,
    Object? replies = null,
  }) {
    return _then(
      _value.copyWith(
            id: null == id
                ? _value.id
                : id // ignore: cast_nullable_to_non_nullable
                      as String,
            body: null == body
                ? _value.body
                : body // ignore: cast_nullable_to_non_nullable
                      as String,
            author: freezed == author
                ? _value.author
                : author // ignore: cast_nullable_to_non_nullable
                      as String?,
            parentId: freezed == parentId
                ? _value.parentId
                : parentId // ignore: cast_nullable_to_non_nullable
                      as String?,
            phase: freezed == phase
                ? _value.phase
                : phase // ignore: cast_nullable_to_non_nullable
                      as String?,
            isIgnored: freezed == isIgnored
                ? _value.isIgnored
                : isIgnored // ignore: cast_nullable_to_non_nullable
                      as bool?,
            createdAt: freezed == createdAt
                ? _value.createdAt
                : createdAt // ignore: cast_nullable_to_non_nullable
                      as String?,
            replies: null == replies
                ? _value.replies
                : replies // ignore: cast_nullable_to_non_nullable
                      as List<IdeaComment>,
          )
          as $Val,
    );
  }
}

/// @nodoc
abstract class _$$IdeaCommentImplCopyWith<$Res>
    implements $IdeaCommentCopyWith<$Res> {
  factory _$$IdeaCommentImplCopyWith(
    _$IdeaCommentImpl value,
    $Res Function(_$IdeaCommentImpl) then,
  ) = __$$IdeaCommentImplCopyWithImpl<$Res>;
  @override
  @useResult
  $Res call({
    String id,
    String body,
    String? author,
    String? parentId,
    String? phase,
    bool? isIgnored,
    String? createdAt,
    List<IdeaComment> replies,
  });
}

/// @nodoc
class __$$IdeaCommentImplCopyWithImpl<$Res>
    extends _$IdeaCommentCopyWithImpl<$Res, _$IdeaCommentImpl>
    implements _$$IdeaCommentImplCopyWith<$Res> {
  __$$IdeaCommentImplCopyWithImpl(
    _$IdeaCommentImpl _value,
    $Res Function(_$IdeaCommentImpl) _then,
  ) : super(_value, _then);

  /// Create a copy of IdeaComment
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? id = null,
    Object? body = null,
    Object? author = freezed,
    Object? parentId = freezed,
    Object? phase = freezed,
    Object? isIgnored = freezed,
    Object? createdAt = freezed,
    Object? replies = null,
  }) {
    return _then(
      _$IdeaCommentImpl(
        id: null == id
            ? _value.id
            : id // ignore: cast_nullable_to_non_nullable
                  as String,
        body: null == body
            ? _value.body
            : body // ignore: cast_nullable_to_non_nullable
                  as String,
        author: freezed == author
            ? _value.author
            : author // ignore: cast_nullable_to_non_nullable
                  as String?,
        parentId: freezed == parentId
            ? _value.parentId
            : parentId // ignore: cast_nullable_to_non_nullable
                  as String?,
        phase: freezed == phase
            ? _value.phase
            : phase // ignore: cast_nullable_to_non_nullable
                  as String?,
        isIgnored: freezed == isIgnored
            ? _value.isIgnored
            : isIgnored // ignore: cast_nullable_to_non_nullable
                  as bool?,
        createdAt: freezed == createdAt
            ? _value.createdAt
            : createdAt // ignore: cast_nullable_to_non_nullable
                  as String?,
        replies: null == replies
            ? _value._replies
            : replies // ignore: cast_nullable_to_non_nullable
                  as List<IdeaComment>,
      ),
    );
  }
}

/// @nodoc
@JsonSerializable()
class _$IdeaCommentImpl implements _IdeaComment {
  const _$IdeaCommentImpl({
    required this.id,
    required this.body,
    this.author,
    this.parentId,
    this.phase,
    this.isIgnored,
    this.createdAt,
    final List<IdeaComment> replies = const [],
  }) : _replies = replies;

  factory _$IdeaCommentImpl.fromJson(Map<String, dynamic> json) =>
      _$$IdeaCommentImplFromJson(json);

  @override
  final String id;
  @override
  final String body;
  @override
  final String? author;
  @override
  final String? parentId;
  @override
  final String? phase;
  @override
  final bool? isIgnored;
  @override
  final String? createdAt;
  final List<IdeaComment> _replies;
  @override
  @JsonKey()
  List<IdeaComment> get replies {
    if (_replies is EqualUnmodifiableListView) return _replies;
    // ignore: implicit_dynamic_type
    return EqualUnmodifiableListView(_replies);
  }

  @override
  String toString() {
    return 'IdeaComment(id: $id, body: $body, author: $author, parentId: $parentId, phase: $phase, isIgnored: $isIgnored, createdAt: $createdAt, replies: $replies)';
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is _$IdeaCommentImpl &&
            (identical(other.id, id) || other.id == id) &&
            (identical(other.body, body) || other.body == body) &&
            (identical(other.author, author) || other.author == author) &&
            (identical(other.parentId, parentId) ||
                other.parentId == parentId) &&
            (identical(other.phase, phase) || other.phase == phase) &&
            (identical(other.isIgnored, isIgnored) ||
                other.isIgnored == isIgnored) &&
            (identical(other.createdAt, createdAt) ||
                other.createdAt == createdAt) &&
            const DeepCollectionEquality().equals(other._replies, _replies));
  }

  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  int get hashCode => Object.hash(
    runtimeType,
    id,
    body,
    author,
    parentId,
    phase,
    isIgnored,
    createdAt,
    const DeepCollectionEquality().hash(_replies),
  );

  /// Create a copy of IdeaComment
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  @pragma('vm:prefer-inline')
  _$$IdeaCommentImplCopyWith<_$IdeaCommentImpl> get copyWith =>
      __$$IdeaCommentImplCopyWithImpl<_$IdeaCommentImpl>(this, _$identity);

  @override
  Map<String, dynamic> toJson() {
    return _$$IdeaCommentImplToJson(this);
  }
}

abstract class _IdeaComment implements IdeaComment {
  const factory _IdeaComment({
    required final String id,
    required final String body,
    final String? author,
    final String? parentId,
    final String? phase,
    final bool? isIgnored,
    final String? createdAt,
    final List<IdeaComment> replies,
  }) = _$IdeaCommentImpl;

  factory _IdeaComment.fromJson(Map<String, dynamic> json) =
      _$IdeaCommentImpl.fromJson;

  @override
  String get id;
  @override
  String get body;
  @override
  String? get author;
  @override
  String? get parentId;
  @override
  String? get phase;
  @override
  bool? get isIgnored;
  @override
  String? get createdAt;
  @override
  List<IdeaComment> get replies;

  /// Create a copy of IdeaComment
  /// with the given fields replaced by the non-null parameter values.
  @override
  @JsonKey(includeFromJson: false, includeToJson: false)
  _$$IdeaCommentImplCopyWith<_$IdeaCommentImpl> get copyWith =>
      throw _privateConstructorUsedError;
}
