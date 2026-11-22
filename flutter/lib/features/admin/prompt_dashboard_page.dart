import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/tokens.dart';
import '../../core/widgets/app_shell.dart';
import '../ideas/idea_models.dart';
import 'admin_repository.dart';

/// Per-prompt dashboard: idea pipeline, run outcomes, timings, trend and
/// recent runs. Every count drills into the matching filtered list.
class PromptDashboardPage extends ConsumerStatefulWidget {
  const PromptDashboardPage({super.key, required this.promptId});

  final String promptId;

  @override
  ConsumerState<PromptDashboardPage> createState() =>
      _PromptDashboardPageState();
}

class _PromptDashboardPageState extends ConsumerState<PromptDashboardPage> {
  int _days = 30;

  void _openIdeas({String status = 'ALL'}) {
    Navigator.of(context).pushNamed(
      '/ideas',
      arguments: {'prompt': widget.promptId, 'status': status},
    );
  }

  void _openRuns({String? runStatus, String? model}) {
    Navigator.of(context).pushNamed(
      '/admin/activity',
      arguments: {
        'prompt': widget.promptId,
        'run_status': ?runStatus,
        'model': ?model,
      },
    );
  }

  void _openRun(Map<String, dynamic> run) {
    final ideaId = run['idea_id']?.toString();
    if (ideaId != null && ideaId.isNotEmpty) {
      Navigator.of(context).pushNamed('/ideas/detail', arguments: ideaId);
      return;
    }
    _editPrompt();
  }

  void _editPrompt() {
    Navigator.of(
      context,
    ).pushNamed('/prompts/form', arguments: widget.promptId);
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(
      promptStatsProvider((id: widget.promptId, days: _days)),
    );
    return AppShell(
      title: 'Prompt dashboard',
      child: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Failed to load: $e')),
        data: (data) {
          final prompt = data['prompt'] as Map? ?? {};
          final ideas = data['ideas'] as Map? ?? {};
          final runs = data['runs'] as Map? ?? {};
          final byStatus = ideas['by_status'] as Map? ?? {};
          final runStatus = runs['by_status'] as Map? ?? {};
          final byModel = (data['by_model'] as List? ?? [])
              .map((e) => (e as Map).map((k, v) => MapEntry(k.toString(), v)))
              .toList();
          final daily = (data['daily'] as List? ?? [])
              .map((e) => (e as Map).map((k, v) => MapEntry(k.toString(), v)))
              .toList();
          final recentRuns = (data['recent_runs'] as List? ?? [])
              .map((e) => (e as Map).map((k, v) => MapEntry(k.toString(), v)))
              .toList();
          final flags = (data['flags'] as List? ?? [])
              .map((e) => (e as Map).map((k, v) => MapEntry(k.toString(), v)))
              .toList();
          final lastError = runs['last_error'] as Map?;

          return ListView(
            padding: const EdgeInsets.all(AppSpacing.md),
            children: [
              Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          (prompt['title'] ?? 'Prompt').toString(),
                          style: Theme.of(context).textTheme.titleLarge,
                        ),
                        Text(
                          '${prompt['provider'] ?? ''} · ${prompt['model_name'] ?? ''}',
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    key: const Key('prompt_dashboard_edit'),
                    icon: const Icon(Icons.edit_outlined),
                    tooltip: 'Edit prompt',
                    onPressed: _editPrompt,
                  ),
                  SegmentedButton<int>(
                    key: const Key('prompt_dashboard_days'),
                    segments: const [
                      ButtonSegment(value: 7, label: Text('7d')),
                      ButtonSegment(value: 30, label: Text('30d')),
                      ButtonSegment(value: 90, label: Text('90d')),
                    ],
                    selected: {_days},
                    onSelectionChanged: (v) => setState(() => _days = v.first),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.md),
              if (flags.isNotEmpty) ...[
                Card(
                  color: Theme.of(context).colorScheme.errorContainer,
                  child: Padding(
                    padding: const EdgeInsets.all(AppSpacing.md),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'Health flags',
                          style: TextStyle(fontWeight: FontWeight.bold),
                        ),
                        for (final flag in flags)
                          Padding(
                            padding: const EdgeInsets.only(top: AppSpacing.xs),
                            child: Text(
                              '${flag['message'] ?? flag['code']}',
                              style: const TextStyle(fontSize: 13),
                            ),
                          ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: AppSpacing.md),
              ],
              Wrap(
                spacing: AppSpacing.sm,
                runSpacing: AppSpacing.sm,
                children: [
                  _StatCard(
                    label: 'Ideas',
                    value: '${ideas['total'] ?? 0}',
                    hint: '${ideas['created_in_window'] ?? 0} in $_days days',
                    onTap: () => _openIdeas(),
                  ),
                  _StatCard(
                    label: 'Runs',
                    value: '${runs['in_window'] ?? 0}',
                    hint: '${runs['total'] ?? 0} all time',
                    onTap: () => _openRuns(),
                  ),
                  _StatCard(
                    label: 'Success rate',
                    value: _percent(runs['success_rate']),
                    hint: 'finished runs, $_days days',
                    onTap: () => _openRuns(runStatus: 'FAILED'),
                  ),
                  _StatCard(
                    label: 'Average time',
                    value: _seconds(runs['avg_seconds']),
                    hint: 'successful runs',
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.md),
              _Section(
                title: 'Ideas by state',
                subtitle: 'Tap a state to list those ideas',
                child: _BarChart(
                  key: const Key('prompt_dashboard_ideas'),
                  rows: [
                    for (final status in ideaStatuses)
                      _Bar(
                        label: status,
                        value: (byStatus[status] as num?)?.toDouble() ?? 0,
                        colour: AppColors.statusColor(status),
                        onTap: () => _openIdeas(status: status),
                      ),
                  ],
                ),
              ),
              _Section(
                title: 'Run outcomes',
                subtitle: 'Tap an outcome to list those runs',
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _StackedOutcomeBar(
                      key: const Key('prompt_dashboard_outcomes'),
                      counts: {
                        for (final entry in runStatus.entries)
                          entry.key.toString():
                              (entry.value as num?)?.toInt() ?? 0,
                      },
                      onTap: (status) => _openRuns(runStatus: status),
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    Wrap(
                      spacing: AppSpacing.sm,
                      runSpacing: AppSpacing.xs,
                      children: [
                        for (final status in const [
                          'SUCCESS',
                          'FAILED',
                          'RUNNING',
                          'PENDING',
                        ])
                          ActionChip(
                            label: Text('$status ${runStatus[status] ?? 0}'),
                            onPressed: () => _openRuns(runStatus: status),
                          ),
                      ],
                    ),
                    if (lastError != null) ...[
                      const SizedBox(height: AppSpacing.sm),
                      Text(
                        'Last failure (${lastError['error_category'] ?? 'error'}): '
                        '${lastError['error'] ?? ''}',
                        style: TextStyle(
                          fontSize: 12,
                          color: Theme.of(context).colorScheme.error,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              _Section(
                title: 'Time by model',
                subtitle: 'Average successful run, $_days days',
                child: byModel.isEmpty
                    ? const Text('No runs in this window.')
                    : _BarChart(
                        key: const Key('prompt_dashboard_models'),
                        valueLabel: (value) => _seconds(value),
                        rows: [
                          for (final model in byModel)
                            _Bar(
                              label: '${model['provider']}/${model['model']}',
                              caption:
                                  '${model['runs']} runs · ${model['success']} ok · ${model['failed']} failed',
                              value:
                                  (model['avg_seconds'] as num?)?.toDouble() ??
                                  0,
                              colour: AppColors.primary600,
                              onTap: () =>
                                  _openRuns(model: model['model']?.toString()),
                            ),
                        ],
                      ),
              ),
              _Section(
                title: 'Last 14 days',
                subtitle: 'Runs and ideas created per day',
                child: _TrendChart(
                  key: const Key('prompt_dashboard_trend'),
                  days: daily,
                ),
              ),
              _Section(
                title: 'Recent runs',
                subtitle: 'Tap a run to open its idea or the prompt editor',
                child: recentRuns.isEmpty
                    ? const Text('No runs yet.')
                    : Column(
                        children: [
                          for (final run in recentRuns)
                            _RunTile(run: run, onTap: () => _openRun(run)),
                        ],
                      ),
              ),
            ],
          );
        },
      ),
    );
  }
}

String _percent(dynamic value) {
  if (value is num) return '${(value * 100).round()}%';
  return '–';
}

String _seconds(dynamic value) {
  if (value is num) {
    if (value >= 60) return '${(value / 60).toStringAsFixed(1)}m';
    return '${value.toStringAsFixed(1)}s';
  }
  return '–';
}

String _relative(dynamic iso) {
  if (iso == null) return '';
  final when = DateTime.tryParse(iso.toString());
  if (when == null) return iso.toString();
  final diff = DateTime.now().toUtc().difference(when.toUtc());
  if (diff.inMinutes < 1) return 'just now';
  if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
  if (diff.inHours < 24) return '${diff.inHours}h ago';
  return '${diff.inDays}d ago';
}

class _Section extends StatelessWidget {
  const _Section({required this.title, required this.child, this.subtitle});

  final String title;
  final String? subtitle;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: AppSpacing.md),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.titleMedium),
            if (subtitle != null)
              Padding(
                padding: const EdgeInsets.only(top: AppSpacing.xs),
                child: Text(
                  subtitle!,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
            const SizedBox(height: AppSpacing.sm),
            child,
          ],
        ),
      ),
    );
  }
}

class _StatCard extends StatelessWidget {
  const _StatCard({
    required this.label,
    required this.value,
    this.hint,
    this.onTap,
  });

  final String label;
  final String value;
  final String? hint;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(value, style: Theme.of(context).textTheme.headlineSmall),
              Text(label),
              if (hint != null)
                Text(hint!, style: Theme.of(context).textTheme.bodySmall),
            ],
          ),
        ),
      ),
    );
  }
}

class _Bar {
  const _Bar({
    required this.label,
    required this.value,
    required this.colour,
    this.caption,
    this.onTap,
  });

  final String label;
  final double value;
  final Color colour;
  final String? caption;
  final VoidCallback? onTap;
}

class _BarChart extends StatelessWidget {
  const _BarChart({super.key, required this.rows, this.valueLabel});

  final List<_Bar> rows;
  final String Function(double)? valueLabel;

  @override
  Widget build(BuildContext context) {
    final maxValue = rows.fold<double>(0, (m, r) => r.value > m ? r.value : m);
    return Column(
      children: [
        for (final row in rows)
          InkWell(
            onTap: row.onTap,
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          row.caption == null
                              ? row.label
                              : '${row.label} · ${row.caption}',
                          style: const TextStyle(fontSize: 12),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      const SizedBox(width: AppSpacing.sm),
                      Text(
                        valueLabel?.call(row.value) ??
                            row.value.round().toString(),
                        style: const TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 2),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(4),
                    child: LinearProgressIndicator(
                      value: maxValue == 0 ? 0 : row.value / maxValue,
                      minHeight: 8,
                      backgroundColor: Theme.of(
                        context,
                      ).colorScheme.surfaceContainerHighest,
                      valueColor: AlwaysStoppedAnimation(row.colour),
                    ),
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }
}

class _StackedOutcomeBar extends StatelessWidget {
  const _StackedOutcomeBar({
    super.key,
    required this.counts,
    required this.onTap,
  });

  final Map<String, int> counts;
  final ValueChanged<String> onTap;

  static const _colours = {
    'SUCCESS': Color(0xFF10B981),
    'FAILED': Color(0xFFEF4444),
    'RUNNING': Color(0xFF3B82F6),
    'PENDING': Color(0xFFF59E0B),
  };

  @override
  Widget build(BuildContext context) {
    final total = counts.values.fold<int>(0, (a, b) => a + b);
    if (total == 0) return const Text('No runs in this window.');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(6),
          child: SizedBox(
            height: 20,
            child: Row(
              children: [
                for (final status in _colours.keys)
                  if ((counts[status] ?? 0) > 0)
                    Expanded(
                      flex: counts[status]!,
                      child: Semantics(
                        label: '$status ${counts[status]}',
                        button: true,
                        child: GestureDetector(
                          onTap: () => onTap(status),
                          child: ColoredBox(color: _colours[status]!),
                        ),
                      ),
                    ),
              ],
            ),
          ),
        ),
        const SizedBox(height: AppSpacing.xs),
        Text(
          '$total runs in this window',
          style: Theme.of(context).textTheme.bodySmall,
        ),
      ],
    );
  }
}

class _TrendChart extends StatelessWidget {
  const _TrendChart({super.key, required this.days});

  final List<Map<String, dynamic>> days;

  @override
  Widget build(BuildContext context) {
    final maxValue = days.fold<int>(1, (m, d) {
      for (final key in const ['success', 'failed', 'ideas']) {
        final value = (d[key] as num?)?.toInt() ?? 0;
        if (value > m) m = value;
      }
      return m;
    });
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          height: 96,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              for (final day in days)
                Expanded(
                  child: Semantics(
                    label:
                        '${day['date']}: ${day['success']} success, '
                        '${day['failed']} failed, ${day['ideas']} ideas',
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 2),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          _trendBar(
                            day['success'],
                            maxValue,
                            const Color(0xFF10B981),
                          ),
                          _trendBar(
                            day['failed'],
                            maxValue,
                            const Color(0xFFEF4444),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.xs),
        Wrap(
          spacing: AppSpacing.md,
          children: const [
            _LegendDot(colour: Color(0xFF10B981), label: 'Success'),
            _LegendDot(colour: Color(0xFFEF4444), label: 'Failed'),
          ],
        ),
      ],
    );
  }

  Widget _trendBar(dynamic raw, int maxValue, Color colour) {
    final value = (raw as num?)?.toInt() ?? 0;
    return Expanded(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 1),
        child: Container(
          height: value == 0 ? 2 : (84 * value / maxValue).clamp(4, 84),
          decoration: BoxDecoration(
            color: colour,
            borderRadius: BorderRadius.circular(2),
          ),
        ),
      ),
    );
  }
}

class _LegendDot extends StatelessWidget {
  const _LegendDot({required this.colour, required this.label});

  final Color colour;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 8,
          height: 8,
          decoration: BoxDecoration(color: colour, shape: BoxShape.circle),
        ),
        const SizedBox(width: AppSpacing.xs),
        Text(label, style: const TextStyle(fontSize: 11)),
      ],
    );
  }
}

class _RunTile extends StatelessWidget {
  const _RunTile({required this.run, required this.onTap});

  final Map<String, dynamic> run;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final status = (run['status'] ?? '').toString();
    final failed = status == 'FAILED';
    final title = (run['action_type'] ?? 'Generation').toString();
    final ideaRef = run['idea_reference']?.toString();
    final model = [
      run['provider'],
      run['model'],
    ].where((e) => e != null && e.toString().isNotEmpty).join('/');
    final duration = _seconds(run['duration_seconds']);
    return ListTile(
      dense: true,
      contentPadding: EdgeInsets.zero,
      leading: Icon(
        failed
            ? Icons.error_outline
            : status == 'SUCCESS'
            ? Icons.check_circle_outline
            : Icons.schedule,
        color: failed
            ? Theme.of(context).colorScheme.error
            : status == 'SUCCESS'
            ? const Color(0xFF10B981)
            : null,
      ),
      title: Text(
        ideaRef == null ? title : '$title · $ideaRef',
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
      subtitle: Text(
        [
          if (model.isNotEmpty) model,
          duration,
          _relative(run['created_at']),
          if (failed && run['error'] != null)
            '${run['error_category'] ?? 'error'}: ${run['error']}',
        ].join(' · '),
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
      ),
      trailing: const Icon(Icons.chevron_right),
      onTap: onTap,
    );
  }
}

final promptStatsProvider = FutureProvider.autoDispose
    .family<Map<String, dynamic>, ({String id, int days})>(
      (ref, args) => ref
          .watch(adminRepositoryProvider)
          .promptStats(args.id, days: args.days),
    );
