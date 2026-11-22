import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../core/theme/tokens.dart';
import '../../core/widgets/app_shell.dart';

class DashboardPage extends ConsumerStatefulWidget {
  const DashboardPage({super.key});

  @override
  ConsumerState<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends ConsumerState<DashboardPage> {
  Map<String, dynamic>? _data;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await ref.read(apiClientProvider).get('/api/v1/dashboard');
      if (mounted) setState(() => _data = data as Map<String, dynamic>);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  String _formatDate(String? iso) {
    if (iso == null || iso.isEmpty) return '';
    try {
      final d = DateTime.parse(iso);
      return '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
    } catch (_) {
      return iso;
    }
  }

  Color _statusColor(String status) {
    switch (status) {
      case 'SPARK':
        return Colors.blue;
      case 'SCOPE':
        return Colors.indigo;
      case 'MAP':
        return Colors.teal;
      case 'SHIP':
        return Colors.orange;
      case 'SCALE':
        return Colors.green;
      case 'DROP':
        return Colors.red;
      case 'FREEZE':
        return Colors.grey;
      case 'ARCHIVE':
        return Colors.brown;
      default:
        return Colors.blueGrey;
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppShell(
      title: 'Dashboard',
      child: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Text('Failed: $_error'))
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView(
                    padding: const EdgeInsets.all(AppSpacing.md),
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text('Dashboard',
                                style: Theme.of(context).textTheme.headlineMedium),
                          ),
                          IconButton(
                            icon: const Icon(Icons.refresh),
                            tooltip: 'Refresh',
                            onPressed: _load,
                          ),
                        ],
                      ),
                      const SizedBox(height: AppSpacing.md),
                      Text('Ideas by stage',
                          style: Theme.of(context).textTheme.titleLarge),
                      const SizedBox(height: AppSpacing.sm),
                      SizedBox(
                        height: 220,
                        child: PieChart(
                          PieChartData(
                            pieTouchData: PieTouchData(
                              touchCallback: (event, response) {
                                if (event is FlTapUpEvent &&
                                    response?.touchedSection != null) {
                                  final idx =
                                      response!.touchedSection!.touchedSectionIndex;
                                  final keys = (_data?['by_status'] as Map? ?? {})
                                      .keys
                                      .toList();
                                  if (idx >= 0 && idx < keys.length) {
                                    Navigator.of(context).pushNamed(
                                      '/ideas',
                                      arguments: {'status': keys[idx]},
                                    );
                                  }
                                }
                              },
                            ),
                            sections: [
                              for (final e
                                  in (_data?['by_status'] as Map? ?? {})
                                      .entries)
                                PieChartSectionData(
                                  value: (e.value as num?)?.toDouble() ?? 0,
                                  title: '${e.value}',
                                  color: _statusColor(e.key.toString()),
                                  radius: 80,
                                ),
                            ],
                            sectionsSpace: 2,
                            centerSpaceRadius: 30,
                          ),
                        ),
                      ),
                      const SizedBox(height: AppSpacing.sm),
                      Wrap(
                        spacing: AppSpacing.sm,
                        children: [
                          for (final e
                              in (_data?['by_status'] as Map? ?? {}).entries)
                            Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Container(
                                  width: 10,
                                  height: 10,
                                  color: _statusColor(e.key.toString()),
                                ),
                                const SizedBox(width: 4),
                                Text('${e.key}: ${e.value}',
                                    style: const TextStyle(fontSize: 11)),
                              ],
                            ),
                        ],
                      ),
                      const SizedBox(height: AppSpacing.lg),
                      Text('Total ideas: ${_data?['total_ideas'] ?? 0}',
                          style: Theme.of(context).textTheme.titleMedium),
                      const SizedBox(height: AppSpacing.lg),
                      Text('Most voted',
                          style: Theme.of(context).textTheme.titleLarge),
                      const SizedBox(height: AppSpacing.sm),
                      for (final m in (_data?['most_voted'] as List? ?? []))
                        ListTile(
                          title: Text(
                              '${m['reference_code']}: ${m['prompt_title']}'),
                          subtitle: Text(
                              '${m['status'] ?? ''} · '
                              '↑${m['upvotes_count'] ?? 0} '
                              '↓${m['downvotes_count'] ?? 0}'),
                          trailing: Text('${m['net_score']}'),
                          onTap: () => Navigator.of(context).pushNamed(
                            '/ideas/detail',
                            arguments: m['id'],
                          ),
                        ),
                      const SizedBox(height: AppSpacing.lg),
                      Text('Most commented',
                          style: Theme.of(context).textTheme.titleLarge),
                      const SizedBox(height: AppSpacing.sm),
                      for (final m in (_data?['most_commented'] as List? ?? []))
                        ListTile(
                          title: Text(
                              '${m['reference_code']}: ${m['prompt_title']}'),
                          subtitle: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              if (m['latest_comment'] != null)
                                Text(
                                    '${_formatDate(m['latest_comment']['created_at'])} · ${m['latest_comment']['author'] ?? ''}: ${m['latest_comment']['body'] ?? ''}'),
                              if (m['latest_comment'] == null)
                                Text('No comments'),
                            ],
                          ),
                          trailing: Text('${m['comment_count']}'),
                          onTap: () => Navigator.of(context).pushNamed(
                            '/ideas/detail',
                            arguments: m['id'],
                          ),
                        ),
                      const SizedBox(height: AppSpacing.lg),
                      Text('Recent runs',
                          style: Theme.of(context).textTheme.titleLarge),
                      const SizedBox(height: AppSpacing.sm),
                      for (final r in (_data?['recent_runs'] as List? ?? []))
                        ListTile(
                          title: Text(
                              '${r['idea_reference'] ?? r['id']}: ${r['idea_title'] ?? ''}${r['prompt_title'] != null && r['prompt_title'] != r['idea_title'] ? ' · ${r['prompt_title']}' : ''}'),
                          subtitle: Text(
                              '${r['status'] ?? ''} ${_formatDate(r['created_at'])} ${r['duration_seconds'] != null ? '${(r['duration_seconds'] as num).toStringAsFixed(1)}s' : ''}'),
                          trailing: Text(r['status']?.toString() ?? ''),
                          onTap: r['idea_id'] != null
                              ? () => Navigator.of(context).pushNamed(
                                    '/ideas/detail',
                                    arguments: r['idea_id'],
                                  )
                              : null,
                        ),
                    ],
                  ),
                ),
    );
  }
}