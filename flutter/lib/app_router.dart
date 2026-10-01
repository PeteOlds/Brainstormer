import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../core/widgets/app_shell.dart';
import '../features/admin/admin_pages.dart';
import '../features/admin/users_page.dart';
import '../features/auth/login_page.dart';
import '../features/auth/register_page.dart';import '../features/ideas/idea_detail_page.dart';
import '../features/ideas/ideas_page.dart';
import '../features/prompts/prompt_form_page.dart';
import '../features/prompts/prompts_page.dart';
import '../features/settings/settings_page.dart';

/// Named routes with auth/admin guards. Deep-link parity with the web
/// UI: /ideas understands ?status&prompt&model&idea, /admin/activity
/// ?run_status&model, /prompts ?edit= (consumed in main via Uri.base).
Route<dynamic>? generateRoute(RouteSettings settings) {
  Widget page;
  switch (settings.name) {
    case '/login':
      page = const LoginPage();
    case '/register':
      page = const RegisterPage();
    case '/instances':
      page = const _AuthGate(child: InstancePickerPage());
    case '/ideas':
      final args = settings.arguments;
      page = _AuthGate(
          child: IdeasPage(
              initialStatus:
                  args is Map ? args['status']?.toString() : null));
    case '/ideas/detail':
      final id = settings.arguments?.toString() ?? '';
      page = _AuthGate(child: IdeaDetailPage(ideaId: id));
    case '/prompts':
      page = _AuthGate(child: const PromptsPage());
    case '/prompts/form':
      page = _AuthGate(
          child: PromptFormPage(
              promptId: settings.arguments?.toString()));
    case '/admin':
      page = const _AdminGate(child: AdminPage());
    case '/admin/users':
      page = const _AdminGate(child: UsersPage());
    case '/admin/activity':
      page = const _AdminGate(child: AdminActivityPage());
    case '/settings':
      page = const _AuthGate(child: SettingsPage());
    default:
      page = const LoginPage();
  }
  return MaterialPageRoute(
      settings: settings, builder: (context) => page);
}

/// Redirects anonymous users to /login (mirrors authFetch 401 → login).
class _AuthGate extends ConsumerWidget {
  const _AuthGate({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final token = ref.watch(_tokenProvider);
    return token.when(
      loading: () => const Scaffold(
          body: Center(child: CircularProgressIndicator())),
      error: (_, err) => const LoginPage(),
      data: (t) => t == null ? const LoginPage() : child,
    );
  }
}

/// Admin probe (mirrors the web /admin/stats probe → /ideas fallback).
class _AdminGate extends ConsumerWidget {
  const _AdminGate({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(currentUserProvider);
    if (user == null) return const LoginPage();
    if ((user['role'] as String?) != 'ADMIN') {
      return const AppShell(title: 'Ideas', child: IdeasPage());
    }
    return child;
  }
}

final _tokenProvider = FutureProvider<String?>((ref) async {
  return ref.watch(authStoreProvider).readAccessToken();
});
