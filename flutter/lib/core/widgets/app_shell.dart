import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../theme/tokens.dart';

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
    ('Settings', Icons.settings_outlined, '/settings'),
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final wide = constraints.maxWidth >= 900;
        final nav = NavigationRail(
          selectedIndex: _indexFor(context),
          onDestinationSelected: (i) => Navigator.of(context)
              .pushReplacementNamed(_destinations[i].$3),
          labelType: NavigationRailLabelType.all,
          destinations: [
            for (final d in _destinations)
              NavigationRailDestination(
                  icon: Icon(d.$2), label: Text(d.$1)),
          ],
        );
        final body = Column(
          children: [
            Expanded(child: child),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.md, vertical: AppSpacing.xs),
              color: Theme.of(context).colorScheme.surfaceContainerHighest,
              child: Text(
                'Brainstormer v$kAppVersion',
                key: const Key('app_version_footer'),
                style: Theme.of(context).textTheme.bodySmall,
                textAlign: TextAlign.center,
              ),
            ),
          ],
        );
        if (wide) {
          return Scaffold(
            appBar: AppBar(title: Text(title)),
            body: Row(children: [
              nav,
              const VerticalDivider(width: 1),
              Expanded(child: body),
            ]),
          );
        }
        return Scaffold(
          appBar: AppBar(title: Text(title)),
          drawer: Drawer(
            child: ListView(
              children: [
                const DrawerHeader(child: Text('Brainstormer')),
                for (var i = 0; i < _destinations.length; i++)
                  ListTile(
                    leading: Icon(_destinations[i].$2),
                    title: Text(_destinations[i].$1),
                    onTap: () {
                      Navigator.of(context).pop();
                      Navigator.of(context)
                          .pushReplacementNamed(_destinations[i].$3);
                    },
                  ),
              ],
            ),
          ),
          body: body,
        );
      },
    );
  }

  int _indexFor(BuildContext context) {
    final route = ModalRoute.of(context)?.settings.name ?? '/ideas';
    final i = _destinations.indexWhere((d) => route.startsWith(d.$3));
    return i < 0 ? 0 : i;
  }
}
