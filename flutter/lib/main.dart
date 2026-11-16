import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app_router.dart';
import 'features/auth/auth_controller.dart';
import 'features/auth/auth_models.dart';
import 'core/providers.dart';
import 'core/theme/tokens.dart';

void main() {
  runApp(const ProviderScope(child: BrainstormerApp()));
}

class BrainstormerApp extends ConsumerStatefulWidget {
  const BrainstormerApp({super.key});

  @override
  ConsumerState<BrainstormerApp> createState() => _BrainstormerAppState();
}

class _BrainstormerAppState extends ConsumerState<BrainstormerApp> {
  final _navigatorKey = GlobalKey<NavigatorState>();
  bool _deepLinkDone = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _restoreSession());
  }

  /// Warm the signed-in user from secure storage, then honour web
  /// deep links (?status&prompt&model&idea, ?run_status, ?edit=).
  Future<void> _restoreSession() async {
    final store = ref.read(authStoreProvider);
    final user = await store.readUser();
    final token = await store.readAccessToken();
    if (token != null && user != null) {
      // Refresh profile from /me so role/admin ids are always current.
      Map<String, dynamic>? me;
      try {
        final raw = await ref.read(apiClientProvider).get('/api/v1/me');
        if (raw is Map<String, dynamic>) {
          final data = raw['data'] as Map<String, dynamic>? ?? raw;
          me = data['user'] as Map<String, dynamic>?;
        }
      } catch (_) {
        // Keep cached user if /me is unavailable.
      }
      final restored = me ?? user;
      await store.saveSession(
        accessToken: token,
        refreshToken: (await store.readRefreshToken()) ?? '',
        user: restored,
        instanceId: await store.readInstanceId(),
        instanceLabel: await store.readInstanceLabel(),
      );
      ref.read(currentUserProvider.notifier).state = restored;
      ref.read(currentInstanceProvider.notifier).state =
          await store.readInstanceId();
      ref.read(currentInstanceLabelProvider.notifier).state =
          await store.readInstanceLabel();
    }

    // Web deep-link auto-scope: honour ?instance=90 (or instance UUID/name) on entry.
    await _maybeScopeFromQuery();

    if (kIsWeb && !_deepLinkDone) {
      _deepLinkDone = true;
      _applyDeepLink(Uri.base);
    }
    if (mounted) setState(() {});
  }

  Future<void> _maybeScopeFromQuery() async {
    if (!kIsWeb) return;
    final raw = Uri.base.queryParameters['instance'];
    if (raw == null || raw.trim().isEmpty) return;
    final q = raw.trim().toLowerCase();
    final list = await ref.read(authControllerProvider.notifier).instances();
    InstanceSummary? match;
    for (final inst in list) {
      final name = inst.name.toLowerCase();
      if (inst.id.toLowerCase() == q || inst.number.toString() == q || name == q) {
        match = inst;
        break;
      }
    }
    if (match == null) return;
    final label = 'Site ${match.number} · ${match.name}';
    await ref.read(authRepositoryProvider).switchInstance(match.id);
    final stored = await ref.read(authStoreProvider).readUser();
    if (!mounted) return;
    ref.read(currentUserProvider.notifier).state = stored;
    ref.read(currentInstanceProvider.notifier).state = match.id;
    ref.read(currentInstanceLabelProvider.notifier).state = label;
  }


  void _applyDeepLink(Uri uri) {
    final q = uri.queryParameters;
    final nav = _navigatorKey.currentState;
    if (nav == null) return;
    if (q.containsKey('idea')) {
      nav.pushNamed('/ideas/detail', arguments: q['idea']);
    } else if (q.containsKey('edit')) {
      nav.pushNamed('/prompts/form', arguments: q['edit']);
    } else if (q.containsKey('run_status') || q.containsKey('model')) {
      nav.pushNamed('/admin/activity');
    } else if (q.containsKey('status') ||
        q.containsKey('prompt') ||
        q.containsKey('model')) {
      nav.pushNamed('/ideas', arguments: {'status': q['status']});
    }
  }

  String _initialRoute() {
    if (kIsWeb) {
      final frag = Uri.base.fragment;
      if (frag.startsWith('/')) return frag;
      final path = Uri.base.path;
      if (path.isNotEmpty && path != '/') return path;
    }
    return '/login';
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Brainstormer',
      theme: buildTheme(dark: false),
      darkTheme: buildTheme(dark: true),
      navigatorKey: _navigatorKey,
      initialRoute: _initialRoute(),
      onGenerateRoute: generateRoute,
    );
  }
}
