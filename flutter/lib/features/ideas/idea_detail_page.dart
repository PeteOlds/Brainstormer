import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/auth_helpers.dart';
import '../../core/widgets/pipeline_status_banner.dart';
import '../../core/widgets/site_header.dart';
import '../chat/chat_models.dart';

import '../../core/network/api_client.dart';
import '../../core/pipeline/pipeline_status_provider.dart';
import '../../core/providers.dart';
import '../../core/theme/tokens.dart';
import '../chat/chat_repository.dart';
import 'idea_models.dart';
import 'ideas_controller.dart';
// (removed unused)
import 'widgets/vote_control.dart';

final _detailProvider =
    FutureProvider.family<IdeaDetail, String>((ref, id) async {
  return ref.watch(ideasRepositoryProvider).detail(id);
});

final _commentsProvider = FutureProvider.family
    .autoDispose<List<IdeaComment>, ({String id, String? phase})>(
  (ref, args) async {
    return ref.watch(ideasRepositoryProvider).comments(args.id, phase: args.phase);
  },
);

final _chatSessionsProvider =
    FutureProvider.family.autoDispose<List<ChatSessionModel>, String>(
  (ref, id) async {
    return ref.watch(chatRepositoryProvider).sessions(id);
  },
);

final _actionsProvider =
    FutureProvider.family.autoDispose<Map<String, dynamic>, String>(
  (ref, id) async {
    return ref.watch(ideasRepositoryProvider).availableActions(id);
  },
);

/// Idea detail: overview, action result tabs, threaded comments with
/// phase filter, voting, admin status change, and the Chat tab.
class IdeaDetailPage extends ConsumerStatefulWidget {
  const IdeaDetailPage({super.key, required this.ideaId});

  final String ideaId;

  @override
  ConsumerState<IdeaDetailPage> createState() => _IdeaDetailPageState();
}

class _IdeaDetailPageState extends ConsumerState<IdeaDetailPage> {
  @override
  Widget build(BuildContext context) {
    // SiteHeader lives only once, inside _IdeaTabsWidget. This page just
    // hosts the tabs widget to avoid rendering the header twice (BUG.059).
    return _IdeaTabsWidget(ideaId: widget.ideaId);
  }
}

/// Stateful widget that manages its own TabController so tab selection
/// persists across detail provider rebuilds.
class _IdeaTabsWidget extends ConsumerStatefulWidget {
  final String ideaId;

  const _IdeaTabsWidget({required this.ideaId});

  @override
  ConsumerState<_IdeaTabsWidget> createState() => _IdeaTabsWidgetState();
}

class _IdeaTabsWidgetState extends ConsumerState<_IdeaTabsWidget>
    with SingleTickerProviderStateMixin {
  late TabController _tabs;
  IdeaDetail? _detail;
  bool _loading = true;
  String? _error;
  String? _phaseFilter;
  final _commentDraft = TextEditingController();
  final _chatDraft = TextEditingController();
  bool _sendingChat = false;
  bool _sendingVote = false;
  Timer? _pollTimer;
  Timer? _scalePollTimer;
  String? _selectedBriefVersion;
  String? _selectedDesignVersion;
  String? _selectedBuildVersion;
  bool _testsRunning = false;
  bool _testsDiagnosing = false;
  int _testRunProgress = 0;
  String? _testsDiagnosis;
  String _testStatusFilter = 'all';
  final _newTestName = TextEditingController();
  String _newTestType = 'unit';
  String? _appLogs;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 3, vsync: this);
    _loadDetail();
    ref.listen(_detailProvider(widget.ideaId), (prev, next) {
      next.whenData((detail) {
        if (mounted) {
          setState(() {
            _detail = detail;
            if (prev?.valueOrNull?.idea.status != detail.idea.status) {
              _rebuildTabs(detail);
            }
            _managePoll(detail);
          });
        }
      });
    });
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _scalePollTimer?.cancel();
    _tabs.dispose();
    _commentDraft.dispose();
    _chatDraft.dispose();
    _newTestName.dispose();
    super.dispose();
  }

  Future<void> _loadDetail() async {
    try {
      final detail = await ref.read(ideasRepositoryProvider).detail(widget.ideaId);
      if (mounted) {
        setState(() {
          _detail = detail;
          _loading = false;
          _rebuildTabs(detail);
          _managePoll(detail);
          _manageScalePoll(detail);
        });
      }
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _loading = false; });
    }
  }

  bool get _fullPipelineRunning =>
      _detail?.runningActions.contains('FULL_PIPELINE') ?? false;

  void _managePoll(IdeaDetail detail) {
    if (detail.runningActions.isNotEmpty) {
      _pollTimer ??= Timer.periodic(const Duration(seconds: 5), (_) => _loadDetail());
    } else {
      _pollTimer?.cancel();
      _pollTimer = null;
    }
  }

  /// Refresh the Scale tab while it is open so a release pipeline's phase
  /// and counts keep moving without a manual reload.
  void _manageScalePoll(IdeaDetail detail) {
    _scalePollTimer?.cancel();
    if (detail.idea.status != 'SCALE' || detail.idea.parentId != null) return;
    _scalePollTimer = Timer.periodic(const Duration(seconds: 5), (_) {
      if (!mounted) return;
      final tabs = _buildTabs(_detail ?? detail);
      if (_tabs.index < tabs.length && tabs[_tabs.index].text == 'Scale') {
        unawaited(_loadDetail());
      }
    });
  }

  void _rebuildTabs(IdeaDetail detail) {
    final newCount = _tabCount(detail);
    if (newCount == _tabs.length) return;
    final oldIndex = _tabs.index;
    _tabs.dispose();
    _tabs = TabController(length: newCount, vsync: this);
    if (oldIndex < newCount) _tabs.index = oldIndex;
  }

  // Secondary (non-lifecycle) analyses.
  List<ActionResult> _secondaryAnalyses(IdeaDetail detail) {
    const lifecycle = {
      'PRD_DOC',
      'DESIGN_DOC',
      'BUILD_CODE',
      'REFINE',
      'FULL_PIPELINE',
    };
    return detail.actions.where((a) => !lifecycle.contains(a.actionType)).toList();
  }

  bool _hasResult(IdeaDetail detail, String type) =>
      detail.actions.any((a) => a.actionType == type) ||
      detail.runningActions.contains(type);

  int _tabCount(IdeaDetail detail) {
    int count = 1; // Idea
    if (_secondaryAnalyses(detail).isNotEmpty) count++; // Analysis
    if (_hasResult(detail, 'PRD_DOC')) count++; // Brief
    if (_hasResult(detail, 'DESIGN_DOC')) count++; // Design
    if (_hasResult(detail, 'BUILD_CODE')) {
      count++; // Build
      count++; // Tests
    }
    if (detail.idea.status == 'SCALE' && detail.idea.parentId == null) count++; // Scale
    count++; // Chat
    return count;
  }

  List<Tab> _buildTabs(IdeaDetail detail) {
    final tabs = <Tab>[const Tab(text: 'Idea')];
    if (_secondaryAnalyses(detail).isNotEmpty) tabs.add(const Tab(text: 'Analysis'));
    if (_hasResult(detail, 'PRD_DOC')) tabs.add(const Tab(text: 'Brief'));
    if (_hasResult(detail, 'DESIGN_DOC')) tabs.add(const Tab(text: 'Design'));
    if (_hasResult(detail, 'BUILD_CODE')) {
      tabs.add(const Tab(text: 'Build'));
      tabs.add(const Tab(text: 'Tests'));
    }
    if (detail.idea.status == 'SCALE' && detail.idea.parentId == null) {
      tabs.add(const Tab(text: 'Scale'));
    }
    tabs.add(const Tab(text: 'Chat'));
    return tabs;
  }

  List<Widget> _buildViews(IdeaDetail detail, bool isAdmin) {
    final views = <Widget>[_overviewTab(context, detail, isAdmin)];
    if (_secondaryAnalyses(detail).isNotEmpty) {
      views.add(_analysisTab(context, detail));
    }
    if (_hasResult(detail, 'PRD_DOC')) views.add(_briefTab(context, detail));
    if (_hasResult(detail, 'DESIGN_DOC')) views.add(_designTab(context, detail));
    if (_hasResult(detail, 'BUILD_CODE')) {
      views.add(_buildTab(context, detail));
      views.add(_testsTab(context, detail));
    }
    if (detail.idea.status == 'SCALE' && detail.idea.parentId == null) {
      views.add(_scaleTab(context, detail, isAdmin));
    }
    views.add(_chatTab(context, detail));
    return views;
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (_error != null || _detail == null) {
      return Scaffold(body: Center(child: Text('Failed to load: $_error')));
    }
    final detail = _detail!;
    final user = ref.watch(currentUserProvider);
    final isAdmin = currentUserIsAdmin(user);
    return Scaffold(
      appBar: PreferredSize(
        preferredSize: const Size.fromHeight(104),
        child: Column(
          children: [
            SiteHeader(title: 'Brainstormer'),
            TabBar(controller: _tabs, tabs: _buildTabs(detail)),
          ],
        ),
      ),
      body: TabBarView(controller: _tabs, children: _buildViews(detail, isAdmin)),
      bottomNavigationBar: const PipelineStatusBanner(),
    );
  }

  // ---------- Overview ----------

  Widget _overviewTab(BuildContext context, IdeaDetail detail, bool isAdmin) {
    final idea = detail.idea;
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.md),
      children: [
        Text(
          '${idea.referenceCode}: ${idea.promptTitle}',
          key: const Key('idea_detail_title'),
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        const SizedBox(height: AppSpacing.sm),
        Text(idea.summary ?? '(no summary)',
            style: Theme.of(context).textTheme.bodyLarge),
        if (isAdmin)
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              key: const Key('idea_edit_title'),
              icon: const Icon(Icons.edit, size: 18),
              label: const Text('Edit title'),
              onPressed: () => _editTitle(idea),
            ),
          ),
        const SizedBox(height: AppSpacing.md),
        Row(
          children: [
            VoteControl(
              idea: idea,
              busy: _sendingVote,
              onVote: (d) => _vote(idea.id, d),
            ),
            if (isAdmin && idea.status != 'DROP' && idea.status != 'ARCHIVE' && idea.status != 'FREEZE') ...[
              const SizedBox(width: AppSpacing.md),
              if (_fullPipelineRunning)
                const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
                    SizedBox(width: AppSpacing.sm),
                    Text('Pipeline running...'),
                  ],
                )
              else
                FilledButton.icon(
                  key: const Key('idea_run_full'),
                  onPressed: () => _runFull(idea.id),
                  icon: const Icon(Icons.play_arrow),
                  label: const Text('Run full pipeline'),
                ),
            ],
          ],
        ),
        const SizedBox(height: AppSpacing.md),
        // Status change
        if (isAdmin)
          Row(
            children: [
              const Text('Status: '),
              DropdownButton<String>(
                value: idea.status,
                items: (allowedTransitions[idea.status] ?? const <String>[])
                    .map((s) => DropdownMenuItem(value: s, child: Text(s)))
                    .toList(),
                onChanged: (s) { if (s != null) _changeStatus(idea.id, s); },
              ),
            ],
          ),
        const SizedBox(height: AppSpacing.md),
        _actionsSection(context),
        const SizedBox(height: AppSpacing.md),
        Text('Comments', style: Theme.of(context).textTheme.titleMedium),
        _commentsList(),
      ],
    );
  }

  // ---------- Brief / Design ----------

  Widget _briefTab(BuildContext context, IdeaDetail detail) {
    final briefResults = detail.actions.where((a) => a.actionType == 'PRD_DOC').toList();
    final isRunning = detail.runningActions.contains('PRD_DOC');
    final current = briefResults.isNotEmpty ? briefResults.first : null;
    final selectedVer = _selectedBriefVersion ?? (current?.version.toString());
    final selected = briefResults.where((r) => r.version.toString() == selectedVer).firstOrNull ?? current;
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.md),
      children: [
        Row(
          children: [
            Text('Brief', style: Theme.of(context).textTheme.headlineSmall),
            const Spacer(),
            if (briefResults.length > 1)
              DropdownButton<String>(
                value: selectedVer,
                items: briefResults.map((r) => DropdownMenuItem(value: r.version.toString(), child: Text('v${r.version}${r.isCurrent ? ' (current)' : ''}'))).toList(),
                onChanged: (v) => setState(() => _selectedBriefVersion = v),
              ),
          ],
        ),
        const SizedBox(height: AppSpacing.md),
        if (isRunning)
          const Row(children: [SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)), SizedBox(width: AppSpacing.sm), Text('Running...')])
        else if (briefResults.isEmpty)
          Text('No brief yet. Run "Brief" from the actions section.'),
        if (selected != null) ...[
          Card(child: ListTile(
            title: Text('Brief v${selected.version}'),
            subtitle: Text(_analysisSummary(selected.output)),
            onTap: () => _showAnalysis(context, selected),
          )),
          const SizedBox(height: AppSpacing.sm),
          Row(children: [
            TextButton(onPressed: () => _showAnalysis(context, selected), child: const Text('View details')),
            TextButton(onPressed: () => _copyMarkdown(selected), child: const Text('Copy MD')),
          ]),
        ],
        const SizedBox(height: AppSpacing.md),
        _actionsSection(context),
      ],
    );
  }

  Widget _designTab(BuildContext context, IdeaDetail detail) {
    final designResults = detail.actions.where((a) => a.actionType == 'DESIGN_DOC').toList();
    final isRunning = detail.runningActions.contains('DESIGN_DOC');
    final current = designResults.isNotEmpty ? designResults.first : null;
    final selectedVer = _selectedDesignVersion ?? (current?.version.toString());
    final selected = designResults.where((r) => r.version.toString() == selectedVer).firstOrNull ?? current;
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.md),
      children: [
        Row(
          children: [
            Text('Design', style: Theme.of(context).textTheme.headlineSmall),
            const Spacer(),
            if (designResults.length > 1)
              DropdownButton<String>(
                value: selectedVer,
                items: designResults.map((r) => DropdownMenuItem(value: r.version.toString(), child: Text('v${r.version}${r.isCurrent ? ' (current)' : ''}'))).toList(),
                onChanged: (v) => setState(() => _selectedDesignVersion = v),
              ),
          ],
        ),
        const SizedBox(height: AppSpacing.md),
        if (isRunning)
          const Row(children: [SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)), SizedBox(width: AppSpacing.sm), Text('Running...')])
        else if (designResults.isEmpty)
          Text('No design yet. Run "Design" from the actions section.'),
        if (selected != null) ...[
          Card(child: ListTile(
            title: Text('Design v${selected.version}'),
            subtitle: Text(_analysisSummary(selected.output)),
            onTap: () => _showAnalysis(context, selected),
          )),
          const SizedBox(height: AppSpacing.sm),
          Row(children: [
            TextButton(onPressed: () => _showAnalysis(context, selected), child: const Text('View details')),
            TextButton(onPressed: () => _copyMarkdown(selected), child: const Text('Copy MD')),
          ]),
        ],
        const SizedBox(height: AppSpacing.md),
        _actionsSection(context),
      ],
    );
  }

  // ---------- Build ----------

  Widget _buildTab(BuildContext context, IdeaDetail detail) {
    final buildResults = detail.actions.where((a) => a.actionType == 'BUILD_CODE').toList();
    final isRunning = detail.runningActions.contains('BUILD_CODE');
    final current = buildResults.isNotEmpty ? buildResults.first : null;
    final selectedVer = _selectedBuildVersion ?? (current?.version.toString());
    final selected = buildResults.where((r) => r.version.toString() == selectedVer).firstOrNull ?? current;
    final runbook = selected?.output?['runbook'] as Map<String, dynamic>?;
    final written = selected?.output?['written'] == true;
    final buildPreview = selected?.output?['output']?['files'] as List?;
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.md),
      children: [
        Row(
          children: [
            Text('Build', style: Theme.of(context).textTheme.headlineSmall),
            const Spacer(),
            if (buildResults.length > 1)
              DropdownButton<String>(
                value: selectedVer,
                items: buildResults.map((r) => DropdownMenuItem(value: r.version.toString(), child: Text('v${r.version}${r.isCurrent ? ' (current)' : ''}'))).toList(),
                onChanged: (v) => setState(() => _selectedBuildVersion = v),
              ),
          ],
        ),
        const SizedBox(height: AppSpacing.md),
        if (isRunning)
          const Row(children: [SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)), SizedBox(width: AppSpacing.sm), Text('Running...')]),
        if (buildResults.isEmpty && !isRunning)
          Text('No build results yet. Run "Build" from the actions section.'),
        if (selected != null) ...[
          Card(child: ListTile(
            title: Text('Build v${selected.version}'),
            subtitle: Text('Target: ${selected.output?['target_name'] ?? 'N/A'}\nURL: ${selected.output?['app_url'] ?? 'N/A'}'),
            isThreeLine: true,
            onTap: () => _showAnalysis(context, selected),
          )),
          if (selected.output?['written'] != true && buildPreview != null && buildPreview.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.md),
            Container(
              padding: const EdgeInsets.all(AppSpacing.sm),
              decoration: BoxDecoration(color: Colors.amber.shade50, border: Border.all(color: Colors.amber.shade300), borderRadius: BorderRadius.circular(8)),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Build preview — files to write', style: const TextStyle(fontWeight: FontWeight.bold)),
                  Text('Target: ${selected.output?['target_name'] ?? 'unknown'} · nothing written yet', style: const TextStyle(fontSize: 12)),
                  ...buildPreview.map((f) => Text('${f['path']} (${(f['content'] as String?)?.length ?? 0} chars)', style: const TextStyle(fontFamily: 'monospace', fontSize: 12))),
                ],
              ),
            ),
          ],
          if (selected.output?['written'] != true) ...[
            const SizedBox(height: AppSpacing.sm),
            FilledButton(
              onPressed: () => _writeBuildFiles(detail.idea.id, selected),
              child: const Text('Write files'),
            ),
          ],
          if (selected.output?['write_report'] != null) ...[
            const SizedBox(height: AppSpacing.md),
            Text('Write report', style: Theme.of(context).textTheme.titleSmall),
            Text(selected.output!['write_report'].toString()),
          ],
        ],
        if (selected != null) ...[
          const SizedBox(height: AppSpacing.md),
          Text('Write report', style: Theme.of(context).textTheme.titleSmall),
          const SizedBox(height: AppSpacing.xs),
          Text('Written: ${written ? "yes" : "preview only"}'),
          if (selected.output?['write_report'] != null)
            Text(selected.output!['write_report'].toString()),
        ],
        if (runbook != null) ...[
          const SizedBox(height: AppSpacing.md),
          Text('How to run', style: Theme.of(context).textTheme.titleSmall),
          const SizedBox(height: AppSpacing.xs),
          Text('Setup: ${(runbook['setup_argv'] as List?)?.join(' ') ?? '—'}'),
          Text('Run: ${(runbook['run_argv'] as List?)?.join(' ') ?? '—'}'),
          Text('Workdir: ${runbook['workdir'] ?? '—'}'),
          Text('Port: ${runbook['port'] ?? '—'}'),
        ],
        const SizedBox(height: AppSpacing.md),
        _managedAppSection(context, detail),
        const SizedBox(height: AppSpacing.md),
        _actionsSection(context),
      ],
    );
  }

  // ---------- Tests ----------

  Widget _testsTab(BuildContext context, IdeaDetail detail) {
    return FutureBuilder<Map<String, dynamic>>(
      future: _loadTestsAndSummary(detail.idea.id),
      builder: (ctx, snap) {
        final data = snap.data ?? const {};
        final tests = (data['tests'] as List? ?? const []).whereType<Map<String, dynamic>>().toList();
        final summary = (data['summary'] as Map<String, dynamic>?) ?? const {};
        final counts = (summary['counts'] as Map<String, dynamic>?) ?? const {};
        final filtered = tests.where((t) {
          if (_testStatusFilter == 'all') return true;
          return (t['status']?.toString() ?? '') == _testStatusFilter;
        }).toList();
        final manualPending = tests.where((t) => t['test_type'] == 'manual' && (t['status']?.toString() ?? '') != 'passed').length;
        final autoPassed = tests.where((t) => t['test_type'] != 'manual' && (t['status']?.toString() ?? '') == 'passed').length;
        final autoTotal = tests.where((t) => t['test_type'] != 'manual').length;
        final releaseReady = autoTotal > 0 && autoPassed == autoTotal && manualPending == 0;
        return ListView(
          padding: const EdgeInsets.all(AppSpacing.md),
          children: [
            Text('Tests', style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: AppSpacing.md),
            // Summary stats
            Wrap(spacing: AppSpacing.md, children: [
              Text('${summary['total'] ?? tests.length} tests'),
              Text('${counts['passed'] ?? 0} passed', style: const TextStyle(color: Colors.green)),
              Text('${counts['failed'] ?? 0} failed', style: const TextStyle(color: Colors.red)),
              Text('${counts['not_run'] ?? 0} not run'),
              if (summary['coverage_pct'] != null)
                Text('coverage ${(summary['coverage_pct'] as num).toStringAsFixed(0)}%'),
            ]),
            const SizedBox(height: AppSpacing.sm),
            // Release ready indicator
            Container(
              padding: const EdgeInsets.all(AppSpacing.sm),
              decoration: BoxDecoration(
                color: releaseReady ? Colors.green.shade50 : Colors.amber.shade50,
                border: Border.all(color: releaseReady ? Colors.green.shade300 : Colors.amber.shade300),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(releaseReady ? 'Ready to release' : 'Not ready to release',
                      style: const TextStyle(fontWeight: FontWeight.bold)),
                  if (manualPending > 0)
                    Text('Manual checks: $manualPending still need your verification'),
                  if (!releaseReady && autoTotal > autoPassed)
                    Text('Automated checks: $autoPassed/$autoTotal passed'),
                ],
              ),
            ),
            const SizedBox(height: AppSpacing.sm),
            // Run / diagnose buttons
            Wrap(spacing: AppSpacing.sm, children: [
              FilledButton(
                onPressed: _testsRunning ? null : () => _runIdeaTests(detail.idea.id, const []),
                child: Text(_testsRunning ? 'Running tests...' : 'Run all tests'),
              ),
              FilledButton.tonal(
                onPressed: _testsRunning ? null : () => _runIdeaTests(detail.idea.id, _selectedTestIds.toList()),
                child: const Text('Run selected'),
              ),
              FilledButton.tonal(
                onPressed: _testsDiagnosing ? null : () => _diagnoseTests(detail.idea.id),
                child: Text(_testsDiagnosing ? 'Diagnosing...' : 'Diagnose failures'),
              ),
            ]),
            if (_testsRunning)
              Padding(
                padding: const EdgeInsets.only(top: AppSpacing.sm),
                child: LinearProgressIndicator(value: _testRunProgress / 100.0),
              ),
            if (_testsDiagnosis != null)
              Padding(
                padding: const EdgeInsets.only(top: AppSpacing.sm),
                child: Text(_testsDiagnosis!, style: const TextStyle(fontSize: 12)),
              ),
            const SizedBox(height: AppSpacing.sm),
            // Filter buttons
            Wrap(spacing: AppSpacing.xs, children: [
              for (final f in ['all', 'passed', 'failed', 'not_run', 'skipped'])
                OutlinedButton(
                  style: OutlinedButton.styleFrom(
                    backgroundColor: _testStatusFilter == f ? Colors.indigo : null,
                  ),
                  onPressed: () => setState(() => _testStatusFilter = f),
                  child: Text(f.replaceAll('_', ' '), style: TextStyle(color: _testStatusFilter == f ? Colors.white : null)),
                ),
            ]),
            const SizedBox(height: AppSpacing.sm),
            // Add test
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _newTestName,
                    decoration: const InputDecoration(hintText: 'Test name'),
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                DropdownButton<String>(
                  value: _newTestType,
                  items: ['unit', 'integration', 'e2e', 'manual', 'performance']
                      .map((t) => DropdownMenuItem(value: t, child: Text(t)))
                      .toList(),
                  onChanged: (v) { if (v != null) setState(() => _newTestType = v); },
                ),
                const SizedBox(width: AppSpacing.sm),
                FilledButton(
                  onPressed: () => _addTest(detail.idea.id),
                  child: const Text('Add'),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.sm),
            if (tests.isEmpty)
              const Text('No tests recorded yet. Run a build to generate them, or add one manually.'),
            if (filtered.isEmpty && tests.isNotEmpty)
              const Text('No tests match this filter.'),
            // Test table
            if (filtered.isNotEmpty)
              DataTable(
                columns: const [
                  DataColumn(label: Text('')),
                  DataColumn(label: Text('Name')),
                  DataColumn(label: Text('Type')),
                  DataColumn(label: Text('Status')),
                  DataColumn(label: Text('')),
                ],
                rows: filtered.map((t) {
                  final testId = t['id']?.toString() ?? '';
                  return DataRow(cells: [
                    DataCell(Checkbox(
                      value: _selectedTestIds.contains(testId),
                      onChanged: (v) {
                        setState(() {
                          if (v == true) {
                            _selectedTestIds.add(testId);
                          } else {
                            _selectedTestIds.remove(testId);
                          }
                        });
                      },
                    )),
                    DataCell(Text(t['name']?.toString() ?? '')),
                    DataCell(Text(t['test_type']?.toString() ?? '')),
                    DataCell(DropdownButton<String>(
                      value: t['status']?.toString() ?? 'not_run',
                      items: ['not_run', 'passed', 'failed', 'skipped']
                          .map((s) => DropdownMenuItem(value: s, child: Text(s)))
                          .toList(),
                      onChanged: (v) {
                        if (v != null) _updateTestStatus(detail.idea.id, testId, v);
                      },
                    )),
                    DataCell(Row(
                      children: [
                        if (t['last_run_output'] != null)
                          TextButton(
                            onPressed: () => _showTestDetails(t),
                            child: const Text('Details'),
                          ),
                        TextButton(
                          onPressed: () => _rerunTest(detail.idea.id, testId),
                          child: const Text('Rerun'),
                        ),
                        TextButton(
                          onPressed: () => _deleteTest(detail.idea.id, testId),
                          child: const Text('Delete'),
                        ),
                      ],
                    )),
                  ]);
                }).toList(),
              ),
            const SizedBox(height: AppSpacing.md),
            _actionsSection(context),
          ],
        );
      },
    );
  }

  final Set<String> _selectedTestIds = {};

  Future<Map<String, dynamic>> _loadTestsAndSummary(String id) async {
    try {
      final testsData = await ref.read(apiClientProvider).get('/api/v1/ideas/$id/tests');
      final summaryData = await ref.read(apiClientProvider).get('/api/v1/ideas/$id/tests/summary');
      return {
        'tests': (testsData is Map ? testsData['tests'] : null) as List? ?? const [],
        'summary': (summaryData is Map ? summaryData['data'] ?? summaryData : summaryData) as Map<String, dynamic>? ?? const {},
      };
    } catch (_) {
      return const {'tests': [], 'summary': {}};
    }
  }

  Future<void> _runIdeaTests(String id, List<String> testIds) async {
    try {
      setState(() => _testsRunning = true);
      await ref.read(apiClientProvider).post('/api/v1/ideas/$id/tests/run', body: {'test_ids': testIds});
      // Poll for completion
      for (var i = 0; i < 30; i++) {
        await Future.delayed(const Duration(seconds: 2));
        if (!mounted) break;
        final status = await ref.read(apiClientProvider).get('/api/v1/ideas/$id/tests/run-status');
        final run = (status is Map ? status['run'] : null) as Map<String, dynamic>?;
        if (run != null) {
          final statusStr = run['status']?.toString() ?? '';
          final progress = (run['progress'] as num?)?.toInt() ?? 0;
          if (mounted) setState(() => _testRunProgress = progress);
          if (statusStr == 'completed' || statusStr == 'failed') break;
        }
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
    } finally {
      if (mounted) {
        setState(() { _testsRunning = false; _testRunProgress = 0; });
        _loadDetail();
      }
    }
  }

  Future<void> _diagnoseTests(String id) async {
    try {
      setState(() => _testsDiagnosing = true);
      final data = await ref.read(apiClientProvider).post('/api/v1/ideas/$id/tests/diagnose');
      final diagnosis = (data is Map ? data['diagnosis'] ?? data['message'] : null)?.toString();
      if (mounted) setState(() => _testsDiagnosis = diagnosis);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
    } finally {
      if (mounted) setState(() => _testsDiagnosing = false);
    }
  }

  Future<void> _addTest(String id) async {
    final name = _newTestName.text.trim();
    if (name.isEmpty) return;
    try {
      await ref.read(apiClientProvider).post('/api/v1/ideas/$id/tests', body: {
        'name': name,
        'test_type': _newTestType,
      });
      _newTestName.clear();
      if (mounted) _loadDetail();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
    }
  }

  Future<void> _updateTestStatus(String ideaId, String testId, String status) async {
    try {
      await ref.read(apiClientProvider).patch('/api/v1/ideas/$ideaId/tests/$testId', body: {'status': status});
      if (mounted) _loadDetail();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
    }
  }

  Future<void> _deleteTest(String ideaId, String testId) async {
    try {
      await ref.read(apiClientProvider).delete('/api/v1/ideas/$ideaId/tests/$testId');
      if (mounted) _loadDetail();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
    }
  }

  Future<void> _rerunTest(String ideaId, String testId) async {
    try {
      await ref.read(apiClientProvider).post('/api/v1/ideas/$ideaId/tests/run', body: {'test_ids': [testId]});
      if (mounted) _loadDetail();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
    }
  }

  void _showTestDetails(Map<String, dynamic> test) {
    showDialog<void>(context: context, builder: (ctx) => AlertDialog(
      title: Text(test['name']?.toString() ?? ''),
      content: SizedBox(width: 600, child: SingleChildScrollView(child: SelectableText(test['last_run_output']?.toString() ?? 'No output'))),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Close'))],
    ));
  }

  // ---------- Scale ----------

  Widget _scaleTab(BuildContext context, IdeaDetail detail, bool isAdmin) {
    final idea = detail.idea;
    return FutureBuilder<Map<String, dynamic>>(
      future: _loadScaleData(idea.id),
      builder: (ctx, snap) {
        final data = snap.data ?? const {};
        final children = (data['children'] as List? ?? const []).whereType<Map<String, dynamic>>().toList();
        final releases = (data['releases'] as List? ?? const []).whereType<Map<String, dynamic>>().toList();
        final unassigned = children.where((k) => k['release_id'] == null).toList();
        return ListView(
          padding: const EdgeInsets.all(AppSpacing.md),
          children: [
            Text('Scale', style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: AppSpacing.md),
            Text('Release management and updates.'),
            const SizedBox(height: AppSpacing.md),
            if (isAdmin) ...[
              Wrap(spacing: AppSpacing.sm, children: [
                FilledButton.tonal(
                  onPressed: () => _createChild(idea.id, 'enhancement'),
                  child: const Text('Suggest an improvement'),
                ),
                FilledButton.tonal(
                  onPressed: () => _createChild(idea.id, 'bugfix'),
                  child: const Text('Report a problem'),
                ),
                FilledButton.tonal(
                  onPressed: () => _createRelease(idea.id),
                  child: const Text('New release'),
                ),
              ]),
              const SizedBox(height: AppSpacing.md),
            ],
            if (children.isEmpty)
              const Text('No suggestions yet — be the first.'),
            // Unassigned children
            if (unassigned.isNotEmpty) ...[
              Text('No release yet (${unassigned.length} unassigned)', style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: AppSpacing.xs),
              for (final k in unassigned) _scaleChildCard(k, idea.id, isAdmin, releases),
              const SizedBox(height: AppSpacing.md),
            ],
            // Releases
            for (final r in releases) ...[
              if (r['id'] != null) ...[
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(AppSpacing.sm),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Text(r['name']?.toString() ?? '', style: Theme.of(context).textTheme.titleSmall),
                            const SizedBox(width: AppSpacing.sm),
                            Text('${r['status']} · ${r['child_count']} ideas', style: Theme.of(context).textTheme.bodySmall),
                            if (isAdmin && r['id'] != null) ...[
                              const Spacer(),
                              TextButton(
                                onPressed: _releasePipelineActive(r)
                                    ? null
                                    : () => _runReleasePipeline(idea.id, r['id'].toString()),
                                child: const Text('Run pipeline'),
                              ),
                              if (_releasePipelineActive(r))
                                TextButton(
                                  key: Key('release_pipeline_stop_${r['id']}'),
                                  onPressed: () => _stopReleasePipeline(r['id'].toString()),
                                  child: const Text('Stop'),
                                ),
                              TextButton(
                                onPressed: () => _completeRelease(r['id'].toString()),
                                child: const Text('Mark done'),
                              ),
                              TextButton(
                                onPressed: () => _deleteRelease(r['id'].toString()),
                                child: const Text('Delete'),
                              ),
                            ],
                          ],
                        ),
                        _releasePipelineStatus(context, r),
                        if (r['notes'] != null) ...[
                          const SizedBox(height: AppSpacing.xs),
                          Text(r['notes'].toString(), style: const TextStyle(fontSize: 12)),
                        ],
                        const SizedBox(height: AppSpacing.xs),
                        Text('Builds into: ${r['build_target']?['name'] ?? 'no repo yet'}', style: Theme.of(context).textTheme.bodySmall),
                        // Children in this release
                        ...children.where((k) => k['release_id']?.toString() == r['id']?.toString()).map((k) => Padding(
                          padding: const EdgeInsets.only(top: AppSpacing.xs),
                          child: _scaleChildCard(k, idea.id, isAdmin, releases),
                        )),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: AppSpacing.sm),
              ],
            ],
            const SizedBox(height: AppSpacing.md),
            _actionsSection(context),
          ],
        );
      },
    );
  }

  Map<String, dynamic> _releasePipeline(Map<String, dynamic> release) {
    final pipeline = release['pipeline'];
    if (pipeline is Map) return Map<String, dynamic>.from(pipeline);
    return const <String, dynamic>{};
  }

  bool _releasePipelineActive(Map<String, dynamic> release) {
    final status = _releasePipeline(release)['status']?.toString() ?? 'idle';
    return status == 'running' || status == 'stopping';
  }

  Widget _releasePipelineStatus(
    BuildContext context,
    Map<String, dynamic> release,
  ) {
    final pipeline = _releasePipeline(release);
    final status = pipeline['status']?.toString() ?? 'idle';
    if (status == 'idle') return const SizedBox.shrink();

    const phaseLabels = {
      'prd': 'Brief',
      'design': 'Design',
      'build': 'Build',
      'test': 'Test',
    };
    final phase = pipeline['phase']?.toString() ?? '';
    final phaseLabel = phaseLabels[phase] ?? (phase.isEmpty ? 'Starting' : phase);
    final active = status == 'running' || status == 'stopping';
    final label = switch (status) {
      'running' => 'Running',
      'stopping' => 'Stopping',
      'done' => 'Done',
      'failed' => 'Failed',
      _ => status.toUpperCase(),
    };
    final headline = active ? '$label · $phaseLabel' : label;
    final color = switch (status) {
      'running' || 'stopping' => Colors.blue.shade700,
      'done' => Colors.green.shade700,
      'failed' => Colors.red.shade700,
      _ => Colors.grey.shade700,
    };

    final counts = pipeline['counts'] is Map
        ? Map<String, dynamic>.from(pipeline['counts'] as Map)
        : const <String, dynamic>{};
    final total = (pipeline['total'] as num?)?.toInt() ?? 0;
    final done = (counts[phase] as num?)?.toInt() ?? 0;
    final showProgress =
        active && total > 0 && ['prd', 'design', 'build'].contains(phase);
    final error = pipeline['error']?.toString();

    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.xs),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                key: Key('release_pipeline_status_${release['id']}'),
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.10),
                  border: Border.all(color: color),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(
                  headline,
                  style: TextStyle(fontSize: 11, color: color),
                ),
              ),
              if (showProgress) ...[
                const SizedBox(width: AppSpacing.sm),
                Text(
                  '$done/$total ${phaseLabel}s',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ],
          ),
          if (status == 'failed' && error != null && error.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.xs),
              child: Text(
                error,
                style: TextStyle(fontSize: 11, color: Colors.red.shade700),
              ),
            ),
        ],
      ),
    );
  }

  Widget _scaleChildCard(Map<String, dynamic> k, String parentId, bool isAdmin, List<Map<String, dynamic>> releases) {
    return Card(
      margin: const EdgeInsets.only(bottom: AppSpacing.xs),
      child: ListTile(
        title: Text('${k['reference_code']}: ${k['prompt_title']}'),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${k['status']} · ${k['child_kind']} · 💬 ${k['comments_count'] ?? 0}'),
            Wrap(spacing: AppSpacing.xs, children: [
              _buildPill('Brief', (k['actions_run'] as List?)?.contains('PRD_DOC') ?? false),
              _buildPill('Design', (k['actions_run'] as List?)?.contains('DESIGN_DOC') ?? false),
              _buildPill('Built', (k['actions_run'] as List?)?.contains('BUILD_CODE') ?? false),
              if (k['build_status'] != null)
                _buildPill('Build: ${k['build_status']['status']}', true),
            ]),
          ],
        ),
        trailing: isAdmin
            ? DropdownButton<String>(
                hint: const Text('Move to...'),
                items: [
                  ...releases.where((r) => r['id'] != null).map((r) =>
                      DropdownMenuItem(value: r['id'].toString(), child: Text(r['name']?.toString() ?? ''))),
                ],
                onChanged: (v) {
                  if (v != null) _moveChildToRelease(k['id'].toString(), v);
                },
              )
            : null,
      ),
    );
  }

  Widget _buildPill(String label, bool done) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: done ? Colors.green.shade50 : Colors.grey.shade100,
        border: Border.all(color: done ? Colors.green.shade300 : Colors.grey.shade300),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(label, style: TextStyle(fontSize: 10, color: done ? Colors.green.shade700 : Colors.grey.shade600)),
    );
  }

  Future<Map<String, dynamic>> _loadScaleData(String id) async {
    try {
      final children = await ref.read(apiClientProvider).get('/api/v1/ideas/$id/children');
      final releases = await ref.read(apiClientProvider).get('/api/v1/ideas/$id/releases');
      return {
        'children': (children is Map ? children['ideas'] : null) as List? ?? const [],
        'releases': (releases is Map ? releases['releases'] : null) as List? ?? const [],
        'build_targets': (releases is Map ? releases['build_targets'] : null) as List? ?? const [],
      };
    } catch (_) {
      return const {'children': [], 'releases': [], 'build_targets': []};
    }
  }

  Future<void> _createRelease(String parentId) async {
    final nameCtrl = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('New release'),
        content: TextField(controller: nameCtrl, decoration: const InputDecoration(labelText: 'Name')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Create')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ref.read(apiClientProvider).post('/api/v1/ideas/$parentId/releases', body: {'name': nameCtrl.text.trim()});
      if (mounted) _loadDetail();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
    }
  }

  Future<void> _moveChildToRelease(String childId, String releaseId) async {
    try {
      await ref.read(apiClientProvider).patch('/api/v1/releases/$releaseId/assign', body: {'idea_id': childId});
      if (mounted) _loadDetail();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
    }
  }

  Future<void> _completeRelease(String releaseId) async {
    try {
      await ref.read(apiClientProvider).post('/api/v1/releases/$releaseId/complete');
      if (mounted) _loadDetail();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
    }
  }

  Future<void> _deleteRelease(String releaseId) async {
    try {
      await ref.read(apiClientProvider).delete('/api/v1/releases/$releaseId');
      if (mounted) _loadDetail();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
    }
  }

  Future<void> _runReleasePipeline(String parentId, String releaseId) async {
    try {
      await ref.read(apiClientProvider).post('/api/v1/releases/$releaseId/pipeline');
      ref.invalidate(pipelineStatusProvider);
      if (mounted) _loadDetail();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
    }
  }

  Future<void> _stopReleasePipeline(String releaseId) async {
    try {
      await ref.read(apiClientProvider).post('/api/v1/releases/$releaseId/pipeline/stop');
      ref.invalidate(pipelineStatusProvider);
      if (mounted) _loadDetail();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
    }
  }

  Future<void> _createChild(String parentId, String kind) async {
    final titleCtrl = TextEditingController();
    final bodyCtrl = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(kind == 'enhancement' ? 'Suggest an improvement' : 'Report a problem'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(controller: titleCtrl, decoration: const InputDecoration(labelText: 'Title')),
          TextField(controller: bodyCtrl, decoration: const InputDecoration(labelText: 'Description'), maxLines: 3),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Create')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ref.read(apiClientProvider).post('/api/v1/ideas', body: {
        'prompt_title': titleCtrl.text.trim(),
        'raw_content': bodyCtrl.text.trim().isEmpty ? titleCtrl.text.trim() : bodyCtrl.text.trim(),
        'parent_id': parentId,
        'child_kind': kind,
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Created.')));
        _loadDetail();
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
    }
  }

  // ---------- Managed app section (Build) ----------

  Widget _managedAppSection(BuildContext context, IdeaDetail detail) {
    final idea = detail.idea;
    final instanceId = idea.instanceId;
    if (instanceId == null) return const SizedBox.shrink();
    return FutureBuilder<Map<String, dynamic>?>(
      future: _loadManagedApp(instanceId, idea.id),
      builder: (ctx, snap) {
        final app = snap.data;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('One-click run', style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: AppSpacing.xs),
            if (app == null)
              FilledButton.tonal(
                onPressed: () => _configureManagedApp(instanceId, idea.id),
                child: const Text('Enable one-click run'),
              )
            else ...[
              Text('Status: ${app['live']?['state'] ?? app['state']}'),
              if (app['health_url'] != null) Text('Health: ${app['health_url']}'),
              const SizedBox(height: AppSpacing.xs),
              Wrap(spacing: AppSpacing.sm, runSpacing: AppSpacing.xs, children: [
                if ((app['live']?['state'] ?? app['state']) != 'running')
                  FilledButton(
                    onPressed: () => _startManagedApp(instanceId, app['id'].toString()),
                    child: const Text('Start'),
                  )
                else
                  FilledButton(
                    style: FilledButton.styleFrom(backgroundColor: Colors.red),
                    onPressed: () => _stopManagedApp(instanceId, app['id'].toString()),
                    child: const Text('Stop'),
                  ),
                if (app['open_url'] != null)
                  OutlinedButton(
                    onPressed: () {
                      final url = app['open_url'].toString();
                      showDialog<void>(context: context, builder: (ctx) => AlertDialog(
                        title: const Text('App URL'),
                        content: SelectableText(url),
                        actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Close'))],
                      ));
                    },
                    child: const Text('Open app'),
                  ),
                OutlinedButton(
                  onPressed: () => _configureManagedApp(instanceId, idea.id),
                  child: const Text('Update setup'),
                ),
                OutlinedButton(
                  onPressed: () => _loadLogs(instanceId, app['id'].toString()),
                  child: const Text('Refresh logs'),
                ),
              ]),
              if (_appLogs != null) ...[
                const SizedBox(height: AppSpacing.xs),
                Container(
                  padding: const EdgeInsets.all(AppSpacing.sm),
                  decoration: BoxDecoration(
                    color: Colors.black87,
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: SelectableText(
                    _appLogs!,
                    style: const TextStyle(fontFamily: 'monospace', fontSize: 10, color: Colors.greenAccent),
                  ),
                ),
              ],
            ],
          ],
        );
      },
    );
  }

  Future<void> _loadLogs(String instanceId, String appId) async {
    try {
      final data = await ref.read(apiClientProvider).get('/api/v1/instances/$instanceId/managed-apps/$appId/logs');
      final logs = (data is Map ? (data['logs'] ?? data['data']) : data)?.toString() ?? '';
      if (mounted) setState(() => _appLogs = logs);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
    }
  }

  Future<void> _writeBuildFiles(String ideaId, ActionResult result) async {
    try {
      final targetId = result.targetId ?? result.output?['target_id']?.toString();
      if (targetId == null) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No build target found.')));
        return;
      }
      await ref.read(apiClientProvider).post('/api/v1/ideas/$ideaId/actions', body: {
        'action_type': 'BUILD_CODE',
        'target_id': targetId,
        'confirm_build': true,
      });
      final instanceId = _detail?.idea.instanceId;
      if (instanceId != null) {
        try {
          await ref.read(apiClientProvider).post('/api/v1/instances/$instanceId/managed-apps', body: {
            'idea_id': ideaId,
            'target_id': targetId,
          });
        } catch (_) {}
      }
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Build written.')));
        _loadDetail();
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
    }
  }

  Future<Map<String, dynamic>?> _loadManagedApp(String instanceId, String ideaId) async {
    try {
      final data = await ref.read(apiClientProvider).get('/api/v1/instances/$instanceId/managed-apps');
      final apps = (data is Map ? data['apps'] : null) as List? ?? const [];
      for (final a in apps) {
        if (a is Map && a['idea_id']?.toString() == ideaId) {
          return a.cast<String, dynamic>();
        }
      }
      return null;
    } catch (_) { return null; }
  }

  Future<void> _configureManagedApp(String instanceId, String ideaId) async {
    // Upsert using the latest written build's target.
    final detail = _detail;
    final buildResults = detail?.actions.where((a) => a.actionType == 'BUILD_CODE').toList() ?? const [];
    final targetId = buildResults.isNotEmpty ? buildResults.first.targetId : null;
    if (targetId == null) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Confirm a build first.')));
      return;
    }
    try {
      await ref.read(apiClientProvider).post('/api/v1/instances/$instanceId/managed-apps', body: {
        'idea_id': ideaId,
        'target_id': targetId,
      });
      if (mounted) { ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Configured.'))); _loadDetail(); }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
    }
  }

  Future<void> _startManagedApp(String instanceId, String appId) async {
    try {
      await ref.read(apiClientProvider).post('/api/v1/instances/$instanceId/managed-apps/$appId/start');
      if (mounted) { ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Started.'))); _loadDetail(); }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
    }
  }

  Future<void> _stopManagedApp(String instanceId, String appId) async {
    try {
      await ref.read(apiClientProvider).post('/api/v1/instances/$instanceId/managed-apps/$appId/stop');
      if (mounted) { ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Stopped.'))); _loadDetail(); }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
    }
  }

  // _loadLogs replaced by the _appLogs-setting version above.

  // ---------- Analysis ----------

  Widget _analysisTab(BuildContext context, IdeaDetail detail) {
    const lifecycle = {
      'PRD_DOC',
      'DESIGN_DOC',
      'BUILD_CODE',
      'REFINE',
      'FULL_PIPELINE',
    };
    final analysisActions = detail.actions.where((a) => !lifecycle.contains(a.actionType)).toList();
    if (analysisActions.isEmpty) {
      return const Center(child: Text('No analyses yet.'));
    }
    return ListView.builder(
      padding: const EdgeInsets.all(AppSpacing.md),
      itemCount: analysisActions.length,
      itemBuilder: (context, i) {
        final action = analysisActions[i];
        return Card(
          child: ListTile(
            title: Text('${_actionLabelMap[action.actionType] ?? action.actionType} v${action.version}${action.isCurrent ? ' (current)' : ''}'),
            subtitle: Text(_analysisSummary(action.output), maxLines: 2, overflow: TextOverflow.ellipsis),
            onTap: () => _showAnalysis(context, action),
          ),
        );
      },
    );
  }

  // ---------- Chat ----------

  Widget _chatTab(BuildContext context, IdeaDetail detail) {
    final sessions = ref.watch(_chatSessionsProvider(widget.ideaId));
    return sessions.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text('Chat failed: $e')),
      data: (list) => ListView(
        padding: const EdgeInsets.all(AppSpacing.md),
        children: [
          Text('Chat', style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: AppSpacing.md),
          if (list.isEmpty) const Text('No chat sessions yet.'),
          for (final s in list) ListTile(title: Text('Session ${s.id.substring(0, 8)} (${s.turns.length} turns)')),
          const SizedBox(height: AppSpacing.md),
          TextField(controller: _chatDraft, decoration: const InputDecoration(hintText: 'Message...')),
          const SizedBox(height: AppSpacing.sm),
          FilledButton(onPressed: _sendingChat ? null : _sendChat, child: const Text('Send')),
        ],
      ),
    );
  }

  // ---------- Actions section ----------

  Widget _actionsSection(BuildContext context) {
    final available = ref.watch(_actionsProvider(widget.ideaId));
    return available.when(
      loading: () => const Padding(padding: EdgeInsets.symmetric(vertical: AppSpacing.sm), child: LinearProgressIndicator()),
      error: (e, _) => Align(alignment: Alignment.centerLeft, child: Text('Actions unavailable: $e')),
      data: (payload) {
        final actions = (payload['actions'] as List? ?? const []).whereType<Map<String, dynamic>>().toList();
        if (actions.isEmpty) {
          return const Align(alignment: Alignment.centerLeft, child: Text('No actions available at this stage.'));
        }
        final lifecycleKeys = {'PRD_DOC', 'DESIGN_DOC', 'BUILD_CODE'};
        final lifecycleActions = actions.where((a) => lifecycleKeys.contains(a['key'])).toList();
        final analysisActions = actions.where((a) => !lifecycleKeys.contains(a['key'])).toList();
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (lifecycleActions.isNotEmpty) ...[
              Text('Key steps', style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: AppSpacing.xs),
              Wrap(spacing: AppSpacing.sm, runSpacing: AppSpacing.sm, children: [
                for (final action in lifecycleActions)
                  FilledButton(
                    key: Key('idea_action_${action['key']}'),
                    onPressed: () => _runAction((action['key'] ?? '').toString(), (action['label'] ?? action['key'] ?? '').toString()),
                    child: Text((action['label'] ?? action['key'] ?? '').toString()),
                  ),
              ]),
              const SizedBox(height: AppSpacing.md),
            ],
            if (analysisActions.isNotEmpty) ...[
              Text('Secondary analysis', style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: AppSpacing.xs),
              Wrap(spacing: AppSpacing.sm, runSpacing: AppSpacing.sm, children: [
                for (final action in analysisActions)
                  OutlinedButton(
                    key: Key('idea_action_${action['key']}'),
                    onPressed: () => _runAction((action['key'] ?? '').toString(), (action['label'] ?? action['key'] ?? '').toString()),
                    child: Text((action['label'] ?? action['key'] ?? '').toString()),
                  ),
              ]),
            ],
          ],
        );
      },
    );
  }

  // ---------- Helpers ----------

  Future<void> _runFull(String id) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Run full pipeline?'),
        content: const Text('This will run Brief, Design and Build (preview) automatically, skipping any that already exist. It may take several minutes.'),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.of(ctx).pop(true), child: const Text('Run')),
        ],
      ),
    );
    if (confirm != true) return;
    try {
      await ref.read(apiClientProvider).post('/api/v1/ideas/$id/run-full');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Full pipeline queued. Status is shown at the bottom.'),
          ),
        );
      }
      ref.invalidate(pipelineStatusProvider);
      await _loadDetail();
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _runAction(String key, String label) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Run $label?'),
        content: const Text('This queues a background AI run. Results show in the Analysis tab when it finishes.'),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('Cancel')),
          FilledButton(key: const Key('idea_action_confirm'), onPressed: () => Navigator.of(ctx).pop(true), child: const Text('Run')),
        ],
      ),
    );
    if (confirm != true) return;
    try {
      await ref.read(ideasRepositoryProvider).runAction(widget.ideaId, key);
      ref.invalidate(_actionsProvider(widget.ideaId));
      await _loadDetail();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$label started.')));
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _vote(String id, int direction) async {
    setState(() => _sendingVote = true);
    try {
      final result = await ref.read(ideasRepositoryProvider).vote(id, direction);
      if (mounted && _detail != null) {
        setState(() {
          _detail = _detail!.copyWith(
            idea: _detail!.idea.copyWith(
              netScore: result.netVotes,
              userVote: result.userVote,
              upvotes: result.upvotes,
              downvotes: result.downvotes,
            ),
          );
        });
      }
    } catch (_) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Vote failed — try again')));
    } finally {
      if (mounted) setState(() => _sendingVote = false);
    }
  }

  Future<void> _editTitle(IdeaSummary idea) async {
    final controller = TextEditingController(text: idea.promptTitle);
    final save = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Edit title'),
        content: TextField(controller: controller),
        actions: [
          TextButton(onPressed: () => Navigator.of(context).pop(false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.of(context).pop(true), child: const Text('Save')),
        ],
      ),
    );
    if (save != true) return;
    try {
      await ref.read(ideasRepositoryProvider).updateContent(idea.id, {'prompt_title': controller.text.trim()});
      await _loadDetail();
    } catch (_) {}
  }

  Future<void> _changeStatus(String id, String status) async {
    try {
      await ref.read(ideasRepositoryProvider).changeStatus(id, status);
      await _loadDetail();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
    }
  }

  Future<void> _postComment() async {
    final text = _commentDraft.text.trim();
    if (text.isEmpty) return;
    try {
      await ref.read(ideasRepositoryProvider).postComment(widget.ideaId, text);
      _commentDraft.clear();
      ref.invalidate(_commentsProvider((id: widget.ideaId, phase: _phaseFilter)));
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
    }
  }

  Future<void> _sendChat() async {
    final text = _chatDraft.text.trim();
    if (text.isEmpty) return;
    setState(() => _sendingChat = true);
    try {
      await ref.read(chatRepositoryProvider).send(widget.ideaId, text);
      _chatDraft.clear();
      ref.invalidate(_chatSessionsProvider(widget.ideaId));
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Chat failed: $e')));
    } finally {
      if (mounted) setState(() => _sendingChat = false);
    }
  }

  void _showAnalysis(BuildContext context, ActionResult action) {
    final md = _analysisToMarkdown(action.output);
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('${_actionLabelMap[action.actionType] ?? action.actionType} v${action.version}'),
        content: SizedBox(width: 600, child: SingleChildScrollView(child: SelectableText(md))),
        actions: [TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('Close'))],
      ),
    );
  }

  void _copyMarkdown(ActionResult action) {
    final md = _analysisToMarkdown(action.output);
    // Use clipboard
    // ignore: deprecated_member_use
    // We'll just show in a dialog since clipboard may not be available
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Markdown'),
        content: SizedBox(width: 600, child: SingleChildScrollView(child: SelectableText(md))),
        actions: [TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('Close'))],
      ),
    );
  }

  Widget _commentsList() {
    final comments = ref.watch(_commentsProvider((id: widget.ideaId, phase: _phaseFilter)));
    return comments.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Text('Comments failed: $e'),
      data: (items) => Column(
        children: [
          for (final c in items) _commentTile(c, 0),
          const SizedBox(height: AppSpacing.sm),
          TextField(controller: _commentDraft, decoration: const InputDecoration(hintText: 'Add a comment...')),
          const SizedBox(height: AppSpacing.sm),
          FilledButton(onPressed: _postComment, child: const Text('Post')),
        ],
      ),
    );
  }

  Widget _commentTile(IdeaComment comment, int depth) {
    return Padding(
      padding: EdgeInsets.only(left: depth * 16.0),
      child: ListTile(
        title: Text(comment.body),
        subtitle: Text(comment.author ?? 'Unknown'),
      ),
    );
  }

  static const _actionLabelMap = {
    'PRD_DOC': 'Brief',
    'DESIGN_DOC': 'Design',
    'BUILD_CODE': 'Build',
    'REFINE': 'Refine',
  };

  String _analysisSummary(Map<String, dynamic>? output) {
    if (output == null) return '';
    for (final k in ['summary', 'pitch', 'overview', 'description']) {
      final v = output[k];
      if (v is String && v.trim().isNotEmpty) return v.trim();
    }
    return '';
  }

  String _analysisToMarkdown(Map<String, dynamic>? output) {
    if (output == null) return '';
    const encoder = JsonEncoder.withIndent('  ');
    return encoder.convert(output);
  }
}

const allowedTransitions = <String, List<String>>{
  'SPARK': ['SCOPE', 'DROP', 'FREEZE', 'ARCHIVE'],
  'SCOPE': ['MAP', 'SPARK', 'DROP', 'FREEZE', 'ARCHIVE'],
  'MAP': ['SHIP', 'SCOPE', 'DROP', 'FREEZE', 'ARCHIVE'],
  'SHIP': ['SCALE', 'MAP', 'DROP', 'FREEZE', 'ARCHIVE'],
  'SCALE': ['SHIP', 'SCOPE', 'MAP', 'DROP', 'FREEZE', 'ARCHIVE'],
  'FREEZE': ['SCALE', 'SHIP', 'MAP', 'SCOPE', 'SPARK'],
  'ARCHIVE': ['SPARK'],
  'DROP': ['SCALE', 'SHIP', 'MAP', 'SCOPE', 'SPARK'],
};