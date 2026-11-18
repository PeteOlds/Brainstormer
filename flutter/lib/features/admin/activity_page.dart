import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/tokens.dart';
import '../../core/widgets/app_shell.dart';
import 'admin_repository.dart';

/// Live ops view: workers/queues, summary tiles, live runs, recent runs
/// with drill-down, filters and pagination, plus prompt health cards that
/// open the per-prompt dashboard.
class AdminActivityPage extends ConsumerStatefulWidget {
  const AdminActivityPage({
    super.key,
    this.initialPrompt,
    this.initialRunStatus,
    this.initialModel,
  });

  final String? initialPrompt;
  final String? initialRunStatus;
  final String? initialModel;

  @override
  ConsumerState<AdminActivityPage> createState() => _AdminActivityPageState();
}

class _AdminActivityPageState extends ConsumerState<AdminActivityPage> {
  late String? _promptId = widget.initialPrompt;
  late String _runStatus = widget.initialRunStatus ?? '';
  late String _model = widget.initialModel ?? '';
  String _jobType = 'all';
  int _page = 1;
  int _days = 30;

  ({
    int page,
    String status,
    String model,
    String jobType,
    int days,
    String? promptId,
  })
  get _query => (
    page: _page,
    status: _runStatus,
    model: _model,
    jobType: _jobType,
    days: _days,
    promptId: _promptId,
  );

  void _update(VoidCallback change) {
    setState(() {
      change();
      _page = 1;
    });
  }

  void _openRun(Map<String, dynamic> run) {
    final ideaId = run['idea_id']?.toString();
    if (ideaId != null && ideaId.isNotEmpty) {
      Navigator.of(context).pushNamed('/ideas/detail', arguments: ideaId);
      return;
    }
    final promptId = run['prompt_config_id']?.toString();
    if (promptId != null && promptId.isNotEmpty) {
      Navigator.of(context).pushNamed('/prompts/form', arguments: promptId);
    }
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(activityProvider(_query));
    return AppShell(
      title: 'Activity',
      child: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Failed to load: $e')),
        data: (data) {
          final perf = data['performance'] as Map? ?? {};
          final byStatus = perf['by_status'] as Map? ?? {};
          final workers = data['workers_alive'];
          final queues = data['queues'] as Map? ?? {};
          final pageInfo = data['recent_runs_pagination'] as Map? ?? const {};
          final runs = (data['recent_runs'] as List? ?? [])
              .map((e) => (e as Map).map((k, v) => MapEntry(k.toString(), v)))
              .toList();
          final pending = (data['pending_runs'] as List? ?? [])
              .map((e) => (e as Map).map((k, v) => MapEntry(k.toString(), v)))
              .toList();
          final health = (data['prompt_health'] as List? ?? [])
              .map((e) => (e as Map).map((k, v) => MapEntry(k.toString(), v)))
              .toList();
          final models = [
            for (final entry in (perf['per_model'] as List? ?? []))
              if (entry is Map) (entry['model'] ?? '').toString(),
          ].where((e) => e.isNotEmpty).toList();
          String? promptTitle;
          for (final p in health) {
            if (p['id']?.toString() == _promptId) {
              promptTitle = (p['title'] ?? '').toString();
              break;
            }
          }
          final running = (byStatus['RUNNING'] as num?)?.toInt() ?? 0;
          final queued = (byStatus['PENDING'] as num?)?.toInt() ?? 0;

          return RefreshIndicator(
            onRefresh: () async => ref.invalidate(activityProvider),
            child: ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.all(AppSpacing.md),
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        'Activity & performance',
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                    ),
                    SegmentedButton<int>(
                      key: const Key('activity_days'),
                      segments: const [
                        ButtonSegment(value: 7, label: Text('7d')),
                        ButtonSegment(value: 30, label: Text('30d')),
                        ButtonSegment(value: 90, label: Text('90d')),
                      ],
                      selected: {_days},
                      onSelectionChanged: (v) => _update(() => _days = v.first),
                    ),
                    IconButton(
                      key: const Key('activity_refresh'),
                      icon: const Icon(Icons.refresh),
                      tooltip: 'Refresh now',
                      onPressed: () => ref.invalidate(activityProvider),
                    ),
                  ],
                ),
                const SizedBox(height: AppSpacing.sm),
                _WorkersStrip(workers: workers, queues: queues),
                if (_promptId != null) ...[
                  const SizedBox(height: AppSpacing.sm),
                  Card(
                    color: Theme.of(context).colorScheme.primaryContainer,
                    child: Padding(
                      padding: const EdgeInsets.symmetric(
                        horizontal: AppSpacing.md,
                        vertical: AppSpacing.xs,
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.filter_alt_outlined, size: 18),
                          const SizedBox(width: AppSpacing.sm),
                          Expanded(
                            child: Text(
                              'Filtered to prompt: '
                              '${promptTitle ?? _promptId}',
                              key: const Key('activity_prompt_filter'),
                            ),
                          ),
                          TextButton(
                            key: const Key('activity_clear_prompt'),
                            onPressed: () => _update(() => _promptId = null),
                            child: const Text('Clear'),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
                const SizedBox(height: AppSpacing.md),
                Wrap(
                  spacing: AppSpacing.sm,
                  runSpacing: AppSpacing.sm,
                  children: [
                    _StatCard(
                      label: 'Runs',
                      value: '${perf['total_runs'] ?? 0}',
                      hint: 'last $_days days',
                    ),
                    _StatCard(
                      label: 'Success rate',
                      value: _percent(perf['success_rate']),
                      hint:
                          '${byStatus['SUCCESS'] ?? 0} ok · ${byStatus['FAILED'] ?? 0} failed',
                      onTap: () => _update(() => _runStatus = 'FAILED'),
                    ),
                    _StatCard(
                      label: 'Live now',
                      value: '${running + queued}',
                      hint: '$running running · $queued queued',
                    ),
                    _StatCard(
                      label: 'Average time',
                      value: _seconds(perf['avg_seconds']),
                      hint: 'successful runs',
                    ),
                  ],
                ),
                const SizedBox(height: AppSpacing.md),
                _Section(
                  title: 'Live now',
                  subtitle: 'Queued or running jobs',
                  child: pending.isEmpty
                      ? const Text('Nothing queued or running.')
                      : Column(
                          children: [
                            for (final run in pending)
                              _RunTile(
                                key: Key('live_run_${run['id']}'),
                                run: run,
                                onTap: () => _openRun(run),
                              ),
                          ],
                        ),
                ),
                _Section(
                  title: 'Recent runs',
                  subtitle: 'Newest first · tap a run for details',
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _RunFilters(
                        runStatus: _runStatus,
                        jobType: _jobType,
                        model: _model,
                        models: models,
                        onStatus: (v) => _update(() => _runStatus = v ?? ''),
                        onJobType: (v) => _update(() => _jobType = v ?? 'all'),
                        onModel: (v) => _update(() => _model = v ?? ''),
                      ),
                      const SizedBox(height: AppSpacing.sm),
                      if (runs.isEmpty)
                        const Text('No runs match these filters.')
                      else
                        Column(
                          children: [
                            for (final run in runs)
                              _RunTile(
                                key: Key('run_${run['id']}'),
                                run: run,
                                onTap: () => _openRun(run),
                              ),
                            const SizedBox(height: AppSpacing.sm),
                            Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                IconButton(
                                  key: const Key('activity_prev_page'),
                                  icon: const Icon(Icons.chevron_left),
                                  onPressed: pageInfo['has_prev'] == true
                                      ? () => setState(() => _page -= 1)
                                      : null,
                                ),
                                Text(
                                  'Page ${pageInfo['page'] ?? 1} of '
                                  '${pageInfo['pages'] ?? 1} · '
                                  '${pageInfo['total'] ?? runs.length} runs',
                                ),
                                IconButton(
                                  key: const Key('activity_next_page'),
                                  icon: const Icon(Icons.chevron_right),
                                  onPressed: pageInfo['has_next'] == true
                                      ? () => setState(() => _page += 1)
                                      : null,
                                ),
                              ],
                            ),
                          ],
                        ),
                    ],
                  ),
                ),
                _Section(
                  title: 'Prompt health',
                  subtitle:
                      'Trailing 7 days · tap a card for the prompt dashboard',
                  child: health.isEmpty
                      ? const Text('No prompts yet.')
                      : Column(
                          children: [
                            for (final prompt in health)
                              _PromptHealthCard(
                                prompt: prompt,
                                onOpen: () => Navigator.of(context).pushNamed(
                                  '/admin/prompts/detail',
                                  arguments: prompt['id']?.toString(),
                                ),
                                onEdit: () => Navigator.of(context).pushNamed(
                                  '/prompts/form',
                                  arguments: prompt['id']?.toString(),
                                ),
                                onIdeas: () => Navigator.of(context).pushNamed(
                                  '/ideas',
                                  arguments: {
                                    'prompt': prompt['id']?.toString(),
                                    'status': 'ALL',
                                  },
                                ),
                              ),
                          ],
                        ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _WorkersStrip extends StatelessWidget {
  const _WorkersStrip({required this.workers, required this.queues});

  final dynamic workers;
  final Map queues;

  @override
  Widget build(BuildContext context) {
    final alive = workers is num ? workers.toInt() : null;
    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.sm,
        ),
        child: Wrap(
          spacing: AppSpacing.md,
          runSpacing: AppSpacing.xs,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.circle,
                  size: 10,
                  color: alive == null
                      ? Colors.grey
                      : alive > 0
                      ? const Color(0xFF10B981)
                      : Theme.of(context).colorScheme.error,
                ),
                const SizedBox(width: AppSpacing.xs),
                Text(
                  alive == null
                      ? 'Workers unknown'
                      : '$alive worker${alive == 1 ? '' : 's'} alive',
                ),
              ],
            ),
            if (queues.isNotEmpty)
              for (final entry in queues.entries)
                Chip(
                  visualDensity: VisualDensity.compact,
                  label: Text('${entry.key}: ${entry.value}'),
                ),
          ],
        ),
      ),
    );
  }
}

class _RunFilters extends StatelessWidget {
  const _RunFilters({
    required this.runStatus,
    required this.jobType,
    required this.model,
    required this.models,
    required this.onStatus,
    required this.onJobType,
    required this.onModel,
  });

  final String runStatus;
  final String jobType;
  final String model;
  final List<String> models;
  final ValueChanged<String?> onStatus;
  final ValueChanged<String?> onJobType;
  final ValueChanged<String?> onModel;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: AppSpacing.sm,
      runSpacing: AppSpacing.sm,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        DropdownButton<String>(
          key: const Key('activity_status_filter'),
          value: runStatus,
          hint: const Text('All outcomes'),
          items: const [
            DropdownMenuItem(value: '', child: Text('All outcomes')),
            DropdownMenuItem(value: 'SUCCESS', child: Text('Success')),
            DropdownMenuItem(value: 'FAILED', child: Text('Failed')),
            DropdownMenuItem(value: 'RUNNING', child: Text('Running')),
            DropdownMenuItem(value: 'PENDING', child: Text('Queued')),
          ],
          onChanged: onStatus,
        ),
        DropdownButton<String>(
          key: const Key('activity_job_filter'),
          value: jobType,
          items: const [
            DropdownMenuItem(value: 'all', child: Text('All jobs')),
            DropdownMenuItem(value: 'ai', child: Text('AI')),
            DropdownMenuItem(value: 'app', child: Text('App')),
          ],
          onChanged: onJobType,
        ),
        DropdownButton<String>(
          key: const Key('activity_model_filter'),
          value: model,
          hint: const Text('All models'),
          items: [
            const DropdownMenuItem(value: '', child: Text('All models')),
            for (final m in <String>{...models, if (model.isNotEmpty) model})
              DropdownMenuItem(value: m, child: Text(m)),
          ],
          onChanged: onModel,
        ),
      ],
    );
  }
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
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      if (subtitle != null)
                        Text(
                          subtitle!,
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                    ],
                  ),
                ),
              ],
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

class _RunTile extends StatelessWidget {
  const _RunTile({super.key, required this.run, required this.onTap});

  final Map<String, dynamic> run;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final status = (run['status'] ?? '').toString();
    final failed = status == 'FAILED';
    final title = (run['prompt_title'] ?? run['action_type'] ?? 'Generation')
        .toString();
    final ideaRef = run['idea_reference']?.toString();
    final model = [
      run['provider'],
      run['model'],
    ].where((e) => e != null && e.toString().isNotEmpty).join('/');
    final details = [
      status,
      run['triggered_by'],
      if (model.isNotEmpty) model,
      _seconds(run['duration_seconds']),
      _relative(run['created_at']),
    ].where((e) => e != null && e.toString().isNotEmpty).join(' · ');
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
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(details, maxLines: 1, overflow: TextOverflow.ellipsis),
          if (failed && run['error'] != null)
            Text(
              '${run['error_category'] ?? 'error'}: ${run['error']}',
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
        ],
      ),
      trailing: const Icon(Icons.chevron_right),
      onTap: onTap,
    );
  }
}

class _PromptHealthCard extends StatelessWidget {
  const _PromptHealthCard({
    required this.prompt,
    required this.onOpen,
    required this.onEdit,
    required this.onIdeas,
  });

  final Map<String, dynamic> prompt;
  final VoidCallback onOpen;
  final VoidCallback onEdit;
  final VoidCallback onIdeas;

  @override
  Widget build(BuildContext context) {
    final flags = (prompt['flags'] as List? ?? [])
        .map((e) => (e as Map).map((k, v) => MapEntry(k.toString(), v)))
        .toList();
    return Card(
      key: Key('prompt_health_${prompt['id']}'),
      margin: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Semantics(
        button: true,
        label: 'Prompt health ${prompt['title'] ?? ''}',
        child: InkWell(
          onTap: onOpen,
          borderRadius: BorderRadius.circular(12),
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.sm),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            (prompt['title'] ?? '').toString(),
                            style: const TextStyle(fontWeight: FontWeight.bold),
                          ),
                          Text(
                            '${prompt['runs_7d'] ?? 0} runs · '
                            '${prompt['ideas_7d'] ?? 0} ideas '
                            '(7d) · ${prompt['runs_success'] ?? 0} ok · '
                            '${prompt['runs_failed'] ?? 0} failed',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ],
                      ),
                    ),
                    const Icon(Icons.chevron_right),
                  ],
                ),
                for (final flag in flags)
                  Padding(
                    padding: const EdgeInsets.only(top: AppSpacing.xs),
                    child: Text(
                      '${flag['message'] ?? flag['code']}',
                      style: TextStyle(
                        fontSize: 12,
                        color: Theme.of(context).colorScheme.error,
                      ),
                    ),
                  ),
                if (flags.isNotEmpty)
                  Row(
                    children: [
                      TextButton(
                        onPressed: onEdit,
                        child: const Text('Edit prompt'),
                      ),
                      TextButton(
                        onPressed: onIdeas,
                        child: const Text('View ideas'),
                      ),
                    ],
                  ),
              ],
            ),
          ),
        ),
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
  return '';
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

final activityProvider = FutureProvider.autoDispose
    .family<
      Map<String, dynamic>,
      ({
        int page,
        String status,
        String model,
        String jobType,
        int days,
        String? promptId,
      })
    >((ref, q) {
      return ref
          .watch(adminRepositoryProvider)
          .activity(
            page: q.page,
            runStatus: q.status,
            model: q.model,
            jobType: q.jobType,
            days: q.days,
            promptId: q.promptId,
          );
    });
