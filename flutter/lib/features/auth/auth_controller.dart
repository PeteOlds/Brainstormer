import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_client.dart';
import '../../core/providers.dart';
import 'auth_models.dart';
import 'auth_repository.dart';

final authRepositoryProvider = Provider<AuthRepository>((ref) => AuthRepository(
      api: ref.watch(apiClientProvider),
      store: ref.watch(authStoreProvider),
    ));

/// Auth form state. Widgets stay dumb: all transitions live here.
class AuthState {
  const AuthState({this.loading = false, this.error, this.session});

  final bool loading;
  final String? error;
  final AuthSession? session;

  AuthState copyWith({bool? loading, String? error, AuthSession? session}) =>
      AuthState(
        loading: loading ?? this.loading,
        error: error,
        session: session ?? this.session,
      );
}

class AuthController extends StateNotifier<AuthState> {
  AuthController(this._repo, this._ref) : super(const AuthState());

  final AuthRepository _repo;
  final Ref _ref;

  Future<bool> login(String email, String password,
      {bool remember = false, String? instanceId}) async {
    state = state.copyWith(loading: true, error: null);
    try {
      final session = await _repo.login(email, password,
          remember: remember, instanceId: instanceId);
      _ref.read(currentUserProvider.notifier).state = session.user.toJson();
      _ref.read(currentInstanceProvider.notifier).state = instanceId;
      state = state.copyWith(loading: false, session: session);
      return true;
    } on ApiException catch (e) {
      state = state.copyWith(loading: false, error: e.message);
      return false;
    }
  }

  Future<bool> register(String email, String password, String? name) async {
    state = state.copyWith(loading: true, error: null);
    try {
      final session = await _repo.register(email, password, name: name);
      _ref.read(currentUserProvider.notifier).state = session.user.toJson();
      state = state.copyWith(loading: false, session: session);
      return true;
    } on ApiException catch (e) {
      state = state.copyWith(loading: false, error: e.message);
      return false;
    }
  }

  Future<void> logout() async {
    await _repo.logout();
    _ref.read(currentUserProvider.notifier).state = null;
    _ref.read(currentInstanceProvider.notifier).state = null;
    state = const AuthState();
  }

  Future<List<InstanceSummary>> instances() => _repo.instances();
}

final authControllerProvider =
    StateNotifierProvider<AuthController, AuthState>(
        (ref) => AuthController(ref.watch(authRepositoryProvider), ref));
