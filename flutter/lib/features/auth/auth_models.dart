/// Strict domain models for the auth boundary. Validated before any
/// UI is built on them (backend contract first).
class AuthUser {
  AuthUser({
    required this.id,
    required this.email,
    this.name,
    required this.role,
    this.canCreateIdeas = true,
  });

  final String id;
  final String email;
  final String? name;
  final String role;
  final bool canCreateIdeas;

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

class AuthSession {
  AuthSession({
    required this.user,
    required this.accessToken,
    required this.refreshToken,
  });

  final AuthUser user;
  final String accessToken;
  final String refreshToken;

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

class InstanceSummary {
  InstanceSummary({
    required this.id,
    required this.number,
    required this.name,
  });

  final String id;
  final int number;
  final String name;

  factory InstanceSummary.fromJson(Map<String, dynamic> json) =>
      InstanceSummary(
        id: json['id'].toString(),
        number: (json['number'] as num).toInt(),
        name: (json['name'] ?? '').toString(),
      );
}
