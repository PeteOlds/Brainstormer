import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app_router.dart';
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
      ref.read(currentUserProvider.notifier).state = user;
      ref.read(currentInstanceProvider.notifier).state =
          await store.readInstanceId();
    }
    if (kIsWeb && !_deepLinkDone) {
      _deepLinkDone = true;
      _applyDeepLink(Uri.base);
    }
    if (mounted) setState(() {});
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

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Brainstormer',
      theme: buildTheme(dark: false),
      darkTheme: buildTheme(dark: true),
      navigatorKey: _navigatorKey,
      initialRoute: '/login',
      onGenerateRoute: generateRoute,
    );
  }
}
