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
                      label: 'Ideas', value: '${ideas['total'] ?? 0}'),
                  _StatCard(
                      label: 'Prompts',
                      value:
                          '${prompts['active'] ?? 0} / ${prompts['total'] ?? 0}'),
                  _StatCard(
                      label: 'Users', value: '${users['total'] ?? 0}'),
                ],
              ),
              const SizedBox(height: AppSpacing.lg),
              const Text('Go to',
                  style: TextStyle(fontWeight: FontWeight.bold)),
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
                leading: const Icon(Icons.settings),
                title: const Text('Instance settings'),
                onTap: () =>
                    Navigator.of(context).pushNamed('/settings'),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _StatCard extends StatelessWidget {
  const _StatCard({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Card(
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
    );
  }
}

/// Live ops view: runs, queues, prompt health with edit/idea deep links.
class AdminActivityPage extends ConsumerWidget {
  const AdminActivityPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final activity = ref.watch(adminActivityProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Activity')),
      body: activity.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Failed to load: $e')),
        data: (a) {
          final perf = a['performance'] as Map? ?? {};
          final health = (a['prompt_health'] as List? ?? [])
              .map((e) => (e as Map)
                  .map((k, v) => MapEntry(k.toString(), v)))
              .toList();
          return ListView(
            padding: const EdgeInsets.all(AppSpacing.md),
            children: [
              Text(
                  'Runs: ${perf['total_runs'] ?? 0} · '
                  'Success: ${perf['success_rate'] ?? '–'} · '
                  'Pending: ${perf['pending_count'] ?? 0}'),
              const SizedBox(height: AppSpacing.md),
              const Text('Prompt health',
                  style: TextStyle(fontWeight: FontWeight.bold)),
              for (final p in health)
                Card(
                  child: ListTile(
                    title: Text((p['title'] ?? '').toString()),
                    subtitle: Text(
                        '${p['ideas_7d'] ?? 0} ideas / 7d · '
                        '${(p['flags'] as List? ?? []).length} flags'),
                  ),
                ),
            ],
          );
        },
      ),
    );
  }
}
