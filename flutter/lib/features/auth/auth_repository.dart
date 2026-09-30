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
    await store.saveSession(
      accessToken: session.accessToken,
      refreshToken: session.refreshToken,
      user: session.user.toJson(),
      instanceId: instanceId,
    );
    return session;
  }

  Future<AuthSession> login(String email, String password,
      {bool remember = false, String? instanceId}) async {
    final data = await api.post('/api/v1/login', body: {
      'email': email,
      'password': password,
      'remember': remember,
      if (instanceId case final i?) 'instance_id': i,
    }) as Map<String, dynamic>;
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

  Future<void> logout() async {
    try {
      await api.post('/api/v1/logout');
    } catch (_) {
      // Best effort: local session dies regardless.
    }
    await store.clear();
  }
}
