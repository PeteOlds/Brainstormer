import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth_helpers.dart';
import '../providers.dart';
import '../theme/tokens.dart';

/// Top page header used on every screen — logo, main nav, user actions.
/// Replaces the previous Jinja _navbar.html visually for the web build.
class SiteHeader extends ConsumerWidget implements PreferredSizeWidget {
  const SiteHeader({super.key, required this.title});

  final String title;

  @override
  Size get preferredSize => const Size.fromHeight(56);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(currentUserProvider);
    final current = ref.watch(currentInstanceProvider);
    final label = ref.watch(currentInstanceLabelProvider);
    final selectedInstance = current?.toString();
    final canAdmin =
        currentUserCanAdminInstance(user, selectedInstance);
    final canViewPrompts =
        currentUserCanViewPrompts(user, selectedInstance);

    Widget navLink(String label, String route) {
      final active =
          ModalRoute.of(context)?.settings.name?.startsWith(route) == true;
      return TextButton(
        onPressed: () => Navigator.of(context).pushReplacementNamed(route),
        child: Text(
          label,
          style: TextStyle(
            fontWeight: active ? FontWeight.w700 : FontWeight.w500,
          ),
        ),
      );
    }

    return AppBar(
      automaticallyImplyLeading: false,
      // The app previously had no way back from pushed screens (idea detail,
      // prompt form) because the implicit arrow was disabled globally.
      leading: Navigator.of(context).canPop()
          ? IconButton(
              key: const Key('site_header_back'),
              icon: const Icon(Icons.arrow_back),
              tooltip: 'Back',
              onPressed: () => Navigator.of(context).maybePop(),
            )
          : null,
      title: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.lightbulb_outline,
            color: Theme.of(context).colorScheme.primary,
          ),
          const SizedBox(width: AppSpacing.sm),
          Text(
            'Brainstormer',
            style: TextStyle(
              fontWeight: FontWeight.w800,
              color: Theme.of(context).colorScheme.onSurface,
            ),
          ),
        ],
      ),
      centerTitle: false,
      actions: [
        if (MediaQuery.of(context).size.width >= 900) ...[
          navLink('Dashboard', '/dashboard'),
          navLink('Ideas', '/ideas'),
          if (canViewPrompts) navLink('Prompts', '/prompts'),
          if (canAdmin) navLink('Admin', '/admin'),
        ],
        if (current != null || label != null)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
            child: Chip(
              label: Text(label ?? 'Selected site'),
              avatar: const Icon(Icons.language, size: 18),
            ),
          ),
        if (user != null)
          Builder(
            builder: (context) {
              final name = (user['name'] as String?)?.trim();
              final labelText = (name?.isNotEmpty == true)
                  ? name!
                  : (user['email'] as String? ?? 'User');
              final initial = (labelText.isNotEmpty)
                  ? labelText[0].toUpperCase()
                  : 'U';
              return Tooltip(
                message: labelText,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    CircleAvatar(
                      radius: 16,
                      backgroundColor: Theme.of(
                        context,
                      ).colorScheme.primaryContainer,
                      child: Text(
                        initial,
                        style: const TextStyle(fontSize: 14),
                      ),
                    ),
                    if (MediaQuery.of(context).size.width >= 900) ...[
                      const SizedBox(width: AppSpacing.xs),
                      ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 160),
                        child: Text(
                          labelText,
                          style: const TextStyle(fontWeight: FontWeight.w500),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ],
                ),
              );
            },
          ),
        if (user != null)
          PopupMenuButton<String>(
            tooltip: 'Account',
            icon: const CircleAvatar(child: Icon(Icons.person)),
            onSelected: (value) async {
              if (value == '__logout') {
                await ref.read(authStoreProvider).clear();
                ref.read(currentUserProvider.notifier).state = null;
                ref.read(currentInstanceProvider.notifier).state = null;
                ref.read(currentInstanceLabelProvider.notifier).state = null;
                if (context.mounted) {
                  await Navigator.of(
                    context,
                  ).pushNamedAndRemoveUntil('/login', (_) => false);
                }
              } else {
                await Navigator.of(context).pushReplacementNamed(value);
              }
            },
            itemBuilder: (context) => [
              PopupMenuItem(
                enabled: false,
                child: Text(
                  (user['name'] as String?)?.trim().isNotEmpty == true
                      ? user['name'] as String
                      : (user['email'] as String?) ?? '',
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
              ),
              const PopupMenuDivider(),
              const PopupMenuItem(value: '/ideas', child: Text('Ideas')),
              if (canViewPrompts)
                const PopupMenuItem(value: '/prompts', child: Text('Prompts')),
              if (canAdmin)
                const PopupMenuItem(
                  value: '/admin',
                  child: Text('Admin Panel'),
                ),
              const PopupMenuItem(value: '__logout', child: Text('Logout')),
            ],
          ),
      ],
    );
  }
}
