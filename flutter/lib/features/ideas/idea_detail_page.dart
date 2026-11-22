import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/auth_helpers.dart';
import '../../core/widgets/site_header.dart';
import '../chat/chat_models.dart';

import '../../core/network/api_client.dart';
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
    final user = ref.watch(currentUserProvider);
    final isAdmin = currentUserIsAdmin(user);
    return Scaffold(
      appBar: const PreferredSize(
        preferredSize: Size.fromHeight(88),
        child: Column(
          children: [
            SiteHeader(title: 'Brainstormer'),
          ],
        ),
      ),
      body: _IdeaTabsWidget(ideaId: widget.ideaId, isAdmin: isAdmin),
    );
  }
}

/// Stateful widget that manages its own TabController so tab selection
/// persists across detail provider rebuilds.
class _IdeaTabsWidget extends ConsumerStatefulWidget {
  final String ideaId;
  final bool isAdmin;

  const _IdeaTabsWidget({required this.ideaId, required this.isAdmin});

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
  String? _chatError;
  bool _sendingVote = false;
  bool _pipelineRunning = false;
  Timer? _pollTimer;

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
    _tabs.dispose();
    _commentDraft.dispose();
    _chatDraft.dispose();
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
        });
      }
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _loading = false; });
    }
  }

  void _managePoll(IdeaDetail detail) {
    if (detail.runningActions.isNotEmpty) {
      _pollTimer ??= Timer.periodic(const Duration(seconds: 5), (_) => _loadDetail());
    } else {
      _pollTimer?.cancel();
      _pollTimer = null;
    }
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
    const lifecycle = {'PRD_DOC', 'DESIGN_DOC', 'BUILD_CODE', 'REFINE'};
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
        preferredSize: const Size.fromHeight(88),
        child: Column(
          children: [
            SiteHeader(title: 'Brainstormer'),
            TabBar(controller: _tabs, tabs: _buildTabs(detail)),
          ],
        ),
      ),
      body: TabBarView(controller: _tabs, children: _buildViews(detail, isAdmin)),
    );
  }

  // ---------- Overview ----------

  Widget _overviewTab(BuildContext context, IdeaDetail detail, bool isAdmin) {
    final idea = detail.idea;
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.md),
      children: [
        Text(idea.promptTitle, style: Theme.of(context).textTheme.headlineSmall),
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
              if (_pipelineRunning)
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
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.md),
      children: [
        Text('Brief', style: Theme.of(context).textTheme.headlineSmall),
        const SizedBox(height: AppSpacing.md),
        if (isRunning)
          const Row(children: [SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)), SizedBox(width: AppSpacing.sm), Text('Running...')])
        else if (briefResults.isEmpty)
          Text('No brief yet. Run "Brief" from the actions section.'),
        for (final r in briefResults) ...[
          Card(child: ListTile(title: Text('Brief v${r.version}'), subtitle: const Text('Click to view details'), onTap: () => _showAnalysis(context, r))),
        ],
        const SizedBox(height: AppSpacing.md),
        _actionsSection(context),
      ],
    );
  }

  Widget _designTab(BuildContext context, IdeaDetail detail) {
    final designResults = detail.actions.where((a) => a.actionType == 'DESIGN_DOC').toList();
    final isRunning = detail.runningActions.contains('DESIGN_DOC');
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.md),
      children: [
        Text('Design', style: Theme.of(context).textTheme.headlineSmall),
        const SizedBox(height: AppSpacing.md),
        if (isRunning)
          const Row(children: [SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)), SizedBox(width: AppSpacing.sm), Text('Running...')])
        else if (designResults.isEmpty)
          Text('No design yet. Run "Design" from the actions section.'),
        for (final r in designResults) ...[
          Card(child: ListTile(title: Text('Design v${r.version}'), subtitle: const Text('Click to view details'), onTap: () => _showAnalysis(context, r))),
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
    final latest = buildResults.isNotEmpty ? buildResults.first : null;
    final runbook = latest?.output?['runbook'] as Map<String, dynamic>?;
    final written = latest?.output?['written'] == true;
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.md),
      children: [
        Text('Build', style: Theme.of(context).textTheme.headlineSmall),
        const SizedBox(height: AppSpacing.md),
        if (isRunning)
          const Row(children: [SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)), SizedBox(width: AppSpacing.sm), Text('Running...')]),
        if (buildResults.isEmpty && !isRunning)
          Text('No build results yet. Run "Build" from the actions section.'),
        for (final r in buildResults) ...[
          Card(child: ListTile(
            title: Text('Build v${r.version}'),
            subtitle: Text('Target: ${r.output?['target_name'] ?? 'N/A'}\nURL: ${r.output?['app_url'] ?? 'N/A'}'),
            isThreeLine: true,
            onTap: () => _showAnalysis(context, r),
          )),
        ],
        if (latest != null) ...[
          const SizedBox(height: AppSpacing.md),
          Text('Write report', style: Theme.of(context).textTheme.titleSmall),
          const SizedBox(height: AppSpacing.xs),
          Text('Written: ${written ? "yes" : "preview only"}'),
          if (latest.output?['write_report'] != null)
            Text(latest.output!['write_report'].toString()),
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
    return FutureBuilder<List<Map<String, dynamic>>>(
      future: _loadTests(detail.idea.id),
      builder: (ctx, snap) {
        final tests = snap.data ?? const [];
        return ListView(
          padding: const EdgeInsets.all(AppSpacing.md),
          children: [
            Text('Tests', style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: AppSpacing.md),
            if (tests.isEmpty)
              const Text('No tests recorded yet. Run a build to generate them, or add one manually.'),
            for (final t in tests)
              ListTile(
                title: Text(t['name']?.toString() ?? ''),
                subtitle: Text('${t['status'] ?? ''} · ${t['coverage'] ?? ''}'),
                trailing: Text(t['last_run']?.toString() ?? ''),
              ),
            const SizedBox(height: AppSpacing.md),
            _actionsSection(context),
          ],
        );
      },
    );
  }

  Future<List<Map<String, dynamic>>> _loadTests(String id) async {
    try {
      final data = await ref.read(apiClientProvider).get('/api/v1/ideas/$id/tests');
      final list = (data is Map ? data['tests'] : null) as List? ?? const [];
      return list.whereType<Map<String, dynamic>>().toList();
    } catch (_) {
      return const [];
    }
  }

  // ---------- Scale ----------

  Widget _scaleTab(BuildContext context, IdeaDetail detail, bool isAdmin) {
    final idea = detail.idea;
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
          ]),
          const SizedBox(height: AppSpacing.md),
        ],
        FutureBuilder<List<Map<String, dynamic>>>(
          future: _loadChildren(idea.id),
          builder: (ctx, snap) {
            final kids = snap.data ?? const [];
            if (kids.isEmpty) {
              return const Text('No suggestions yet — be the first.');
            }
            return Column(
              children: [
                for (final k in kids)
                  Card(child: ListTile(
                    title: Text('${k['reference_code']}: ${k['prompt_title']}'),
                    subtitle: Text('${k['status']} · ${k['child_kind']}'),
                  )),
              ],
            );
          },
        ),
        const SizedBox(height: AppSpacing.md),
        FutureBuilder<List<Map<String, dynamic>>>(
          future: _loadReleases(idea.id),
          builder: (ctx, snap) {
            final rels = snap.data ?? const [];
            if (rels.isEmpty) return const SizedBox.shrink();
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Releases', style: Theme.of(context).textTheme.titleSmall),
                const SizedBox(height: AppSpacing.xs),
                for (final r in rels)
                  Card(child: ListTile(
                    title: Text(r['name']?.toString() ?? ''),
                    subtitle: Text('${r['status']} · ${r['child_count']} ideas'),
                    trailing: Text(r['id'] == null ? 'unassigned' : ''),
                  )),
              ],
            );
          },
        ),
        const SizedBox(height: AppSpacing.md),
        _actionsSection(context),
      ],
    );
  }

  Future<List<Map<String, dynamic>>> _loadChildren(String id) async {
    try {
      final data = await ref.read(apiClientProvider).get('/api/v1/ideas/$id/children');
      final list = (data is Map ? data['ideas'] : null) as List? ?? const [];
      return list.whereType<Map<String, dynamic>>().toList();
    } catch (_) { return const []; }
  }

  Future<List<Map<String, dynamic>>> _loadReleases(String id) async {
    try {
      final data = await ref.read(apiClientProvider).get('/api/v1/ideas/$id/releases');
      final list = (data is List) ? data : (data is Map ? data['releases'] ?? data['data'] : null);
      if (list is List) return list.whereType<Map<String, dynamic>>().toList();
      return const [];
    } catch (_) { return const []; }
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
              Wrap(spacing: AppSpacing.sm, children: [
                if (app['live']?['state'] != 'running')
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
                    onPressed: () => showDialog<void>(context: context, builder: (ctx) => AlertDialog(title: const Text('App URL'), content: SelectableText(app['open_url'].toString()), actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Close'))])),
                    child: const Text('Open app'),
                  ),
                OutlinedButton(
                  onPressed: () => _configureManagedApp(instanceId, idea.id),
                  child: const Text('Update setup'),
                ),
              ]),
              const SizedBox(height: AppSpacing.xs),
              OutlinedButton(
                onPressed: () => _loadLogs(instanceId, app['id'].toString()),
                child: const Text('Refresh logs'),
              ),
            ],
          ],
        );
      },
    );
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

  Future<void> _loadLogs(String instanceId, String appId) async {
    try {
      final data = await ref.read(apiClientProvider).get('/api/v1/instances/$instanceId/managed-apps/$appId/logs');
      final logs = data is Map ? (data['logs'] ?? data['data']) : data;
      if (mounted) {
        showDialog<void>(context: context, builder: (ctx) => AlertDialog(
          title: const Text('Logs'),
          content: SizedBox(width: 600, child: SingleChildScrollView(child: SelectableText(logs?.toString() ?? ''))),
          actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Close'))],
        ));
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
    }
  }

  // ---------- Analysis ----------

  Widget _analysisTab(BuildContext context, IdeaDetail detail) {
    const lifecycle = {'PRD_DOC', 'DESIGN_DOC', 'BUILD_CODE', 'REFINE'};
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
    setState(() => _pipelineRunning = true);
    try {
      await ref.read(apiClientProvider).post('/api/v1/ideas/$id/run-full');
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Full pipeline queued.')));
      await _loadDetail();
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    } finally {
      if (mounted) setState(() => _pipelineRunning = false);
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
      setState(() => _chatError = e.toString());
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
        title: Text(comment.body ?? ''),
        subtitle: Text(comment.author ?? ''),
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