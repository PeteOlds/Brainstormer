import '../../core/network/api_client.dart';
import '../../core/network/auth_store.dart';
import 'auth_models.dart';

/// All auth traffic flows through the shared ApiClient — never raw http.
class AuthRepository {
  AuthRepository({required this.api, required this.store});

  final ApiClient api;
  final AuthStore store;

  Future<AuthSession> _save(Map<String, dynamic> data, String? instanceId) async {
    final session = AuthSession.fromJson(data);
    final userMap = (data['user'] is Map<String, dynamic>) ? data['user'] as Map<String, dynamic> : session.user.toJson();
    await store.saveSession(
      accessToken: session.accessToken,
      refreshToken: session.refreshToken,
      user: Map<String, dynamic>.from(userMap),
      instanceId: instanceId,
    );
    return session;
  }

  Future<Map<String, dynamic>> loginRaw(String email, String password,
      {bool remember = false, String? instanceId}) async {
    final payload = <String, dynamic>{
      'email': email,
      'password': password,
      'remember': remember,
    };
    if (instanceId != null) payload['instance_id'] = instanceId;
    final data =
        await api.post('/api/v1/login', body: payload) as Map<String, dynamic>;
    return Map<String, dynamic>.from(data);
  }

  Future<AuthSession> login(String email, String password,
      {bool remember = false, String? instanceId}) async {
    final payload = <String, dynamic>{
      'email': email,
      'password': password,
      'remember': remember,
    };
    if (instanceId != null) payload['instance_id'] = instanceId;
    final data =
        await api.post('/api/v1/login', body: payload) as Map<String, dynamic>;
    return _save(data, instanceId);
  }

  Future<AuthSession> register(String email, String password,
      {String? name}) async {
    final trimmedName = (name ?? '').trim();
    final data = await api.post('/api/v1/register', body: {
      'email': email,
      'password': password,
      if (trimmedName.isNotEmpty) 'name': trimmedName,
    }) as Map<String, dynamic>;
    return _save(data, null);
  }

  Future<List<InstanceSummary>> instances() async {
    final data = await api.get('/api/v1/instances');
    final list = (data as Map<String, dynamic>)['instances'] as List;
    return list
        .map((e) => InstanceSummary.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<void> switchInstance(String instanceId) async {
    final data =
        await api.post('/api/v1/switch-instance', body: {'instance_id': instanceId})
            as Map<String, dynamic>;
    final json = data['data'] as Map<String, dynamic>? ?? data;
    final user = (json['user'] as Map<String, dynamic>?) ?? const <String, dynamic>{};
    await store.saveSession(
      accessToken: json['access_token']?.toString() ?? '',
      refreshToken: json['refresh_token']?.toString() ?? '',
      user: Map<String, dynamic>.from(user),
      instanceId: instanceId,
    );
  }

  Future<void> logout() async {
    try {
      await api.post('/api/v1/logout');
    } catch (_) {
      // Best effort: local session dies regardless.
    }
    await store.clear();
  }
}
