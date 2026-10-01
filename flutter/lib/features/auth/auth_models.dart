import 'package:freezed_annotation/freezed_annotation.dart';

part 'auth_models.freezed.dart';
part 'auth_models.g.dart';

/// Strict domain models for the auth boundary. Validated before any
/// UI is built on them (backend contract first).
@freezed
class AuthUser with _$AuthUser {
  const AuthUser._();

  const factory AuthUser({
    required String id,
    required String email,
    String? name,
    required String role,
    @Default(true) bool canCreateIdeas,
  }) = _AuthUser;

  bool get isAdmin => role == 'ADMIN';

  factory AuthUser.fromJson(Map<String, dynamic> json) => AuthUser(
        id: json['id'].toString(),
        email: (json['email'] ?? '').toString(),
        name: json['name']?.toString(),
        role: (json['role'] ?? 'USER').toString(),
        canCreateIdeas: json['can_create_ideas'] as bool? ?? true,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'email': email,
        'name': name,
        'role': role,
        'can_create_ideas': canCreateIdeas,
      };
}

@freezed
class AuthSession with _$AuthSession {
  const factory AuthSession({
    required AuthUser user,
    required String accessToken,
    required String refreshToken,
  }) = _AuthSession;

  factory AuthSession.fromJson(Map<String, dynamic> json) {
    final userJson = json['user'];
    if (userJson is Map<String, dynamic>) {
      return AuthSession(
        user: AuthUser.fromJson(userJson),
        accessToken: json['access_token'].toString(),
        refreshToken: json['refresh_token'].toString(),
      );
    }
    throw const FormatException('Missing user in auth response');
  }
}

@freezed
class InstanceSummary with _$InstanceSummary {
  const factory InstanceSummary({
    required String id,
    required int number,
    required String name,
  }) = _InstanceSummary;

  factory InstanceSummary.fromJson(Map<String, dynamic> json) =>
      InstanceSummary(
        id: json['id'].toString(),
        number: (json['number'] as num).toInt(),
        name: (json['name'] ?? '').toString(),
      );
}
