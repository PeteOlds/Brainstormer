import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/tokens.dart';
import '../../core/widgets/app_shell.dart';
import 'admin_repository.dart';

/// Admin dashboard: stat cards, breakdowns linking into filtered Ideas.
class AdminPage extends ConsumerWidget {
  const AdminPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final stats = ref.watch(adminStatsProvider);
    return AppShell(
      title: 'Admin',
      child: stats.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Failed to load: $e')),
        data: (s) {
          final ideas = s['ideas'] as Map? ?? {};
          final prompts = s['prompts'] as Map? ?? {};
          final users = s['users'] as Map? ?? {};
          return ListView(
            padding: const EdgeInsets.all(AppSpacing.md),
            children: [
              Wrap(
                spacing: AppSpacing.sm,
                runSpacing: AppSpacing.sm,
                children: [
                  _StatCard(
                      label: 'Ideas',
                      value: '${ideas['total'] ?? 0}',
                      onTap: () => Navigator.of(context).pushNamed('/ideas'),
                  ),
                  _StatCard(
                      label: 'Prompts',
                      value:
                          '${prompts['active'] ?? 0} / ${prompts['total'] ?? 0}',
                      onTap: () => Navigator.of(context).pushNamed('/prompts'),
                  ),
                  _StatCard(
                      label: 'Users',
                      value: '${users['total'] ?? 0}',
                      onTap: () => Navigator.of(context).pushNamed('/admin/users'),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.lg),
              const Text('Go to',
                  style: TextStyle(fontWeight: FontWeight.bold)),
              ListTile(
                leading: const Icon(Icons.lightbulb_outline),
                title: const Text('Ideas'),
                onTap: () => Navigator.of(context).pushNamed('/ideas'),
              ),
              ListTile(
                leading: const Icon(Icons.description_outlined),
                title: const Text('Prompts'),
                onTap: () => Navigator.of(context).pushNamed('/prompts'),
              ),
              ListTile(
                leading: const Icon(Icons.people),
                title: const Text('Users'),
                onTap: () =>
                    Navigator.of(context).pushNamed('/admin/users'),
              ),
              ListTile(
                leading: const Icon(Icons.monitor_heart),
                title: const Text('Activity'),
                onTap: () =>
                    Navigator.of(context).pushNamed('/admin/activity'),
              ),
              ListTile(
                leading: const Icon(Icons.data_object),
                title: const Text('Internal AI Prompts'),
                subtitle: const Text('Shared prompt templates (site admin)'),
                onTap: () => Navigator.of(context)
                    .pushNamed('/admin/internal-prompts'),
              ),
              ListTile(
                leading: const Icon(Icons.settings),
                title: const Text('Instance settings'),
                onTap: () =>
                    Navigator.of(context).pushNamed('/settings'),
              ),
              const SizedBox(height: AppSpacing.lg),
              const Text('System health',
                  style: TextStyle(fontWeight: FontWeight.bold)),
              Consumer(builder: (context, ref, _) {
                final health = ref.watch(adminHealthProvider);
                return health.when(
                  loading: () =>
                      const Center(child: CircularProgressIndicator()),
                  error: (e, _) =>
                      Text('Health check failed: $e'),
                  data: (h) {
                    final checks = (h['checks'] as Map?) ?? {};
                    final workers = (h['workers_ollama'] ?? 0) +
                        (h['workers_default'] ?? 0) +
                        (h['workers_opencode'] ?? 0);
                    final rows = <MapEntry<String, bool>>[
                      MapEntry('Ollama', checks['ollama'] == true),
                      MapEntry('Database', checks['database'] == true),
                      MapEntry('Redis', checks['redis'] == true),
                      MapEntry('Celery Workers', workers > 0),
                    ];
                    return Column(
                      children: [
                        for (final r in rows)
                          ListTile(
                            leading: Icon(
                              Icons.circle,
                              size: 12,
                              color: r.value ? Colors.green : Colors.red,
                            ),
                            title: Text(r.key),
                            trailing: Text(r.value ? 'OK' : 'Down'),
                          ),
                      ],
                    );
                  },
                );
              }),
            ],
          );
        },
      ),
    );
  }
}

class _StatCard extends StatelessWidget {
  const _StatCard(
      {required this.label, required this.value, this.onTap});

  final String label;
  final String value;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Column(
            children: [
              Text(value,
                  style: Theme.of(context).textTheme.headlineSmall),
              Text(label),
            ],
          ),
        ),
      ),
    );
  }
}