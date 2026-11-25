import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:brainstormer/core/auth_helpers.dart';

import '../providers.dart';
import '../theme/tokens.dart';
import 'connectivity_banner.dart';
import 'pipeline_status_banner.dart';
import 'package:brainstormer/core/widgets/site_header.dart';

/// App shell: nav rail/drawer, version footer (golden rule — the build
/// number is always available), and the routed child.
class AppShell extends ConsumerWidget {
  const AppShell({super.key, required this.child, required this.title});

  final Widget child;
  final String title;

  static const _destinations = [
    ('Ideas', Icons.lightbulb_outline, '/ideas'),
    ('Prompts', Icons.psychology_outlined, '/prompts'),
    ('Admin', Icons.admin_panel_settings_outlined, '/admin'),
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(currentUserProvider);
    final isAdmin = currentUserIsAdmin(user);
    final destinations = isAdmin
        ? _destinations
        : _destinations.where((d) => d.$3 != '/admin').toList();

    return Scaffold(
      appBar: SiteHeader(title: 'Brainstormer'),
      drawer: Drawer(
        child: ListView(
          children: [
            const DrawerHeader(child: Text('Menu')),
            for (var i = 0; i < destinations.length; i++)
              ListTile(
                leading: Icon(destinations[i].$2),
                title: Text(destinations[i].$1),
                onTap: () {
                  Navigator.of(context).pop();
                  Navigator.of(
                    context,
                  ).pushReplacementNamed(destinations[i].$3);
                },
              ),
          ],
        ),
      ),
      body: Column(
        children: [
          Expanded(child: ConnectivityBanner(child: child)),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.md,
              vertical: AppSpacing.xs,
            ),
            color: Theme.of(context).colorScheme.surfaceContainerHighest,
            child: Text(
              'Brainstormer v$kAppVersion',
              key: const Key('app_version_footer'),
              style: Theme.of(context).textTheme.bodySmall,
              textAlign: TextAlign.center,
            ),
          ),
        ],
      ),
      bottomNavigationBar: const PipelineStatusBanner(),
    );
  }
}
