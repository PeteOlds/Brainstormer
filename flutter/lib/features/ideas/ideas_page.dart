import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../core/theme/tokens.dart';
import '../../core/widgets/app_shell.dart';
import 'idea_models.dart';
import 'ideas_controller.dart';

/// Ideas dashboard: server-side filters, list, votes, admin status menu.
class IdeasPage extends ConsumerStatefulWidget {
  const IdeasPage({super.key, this.initialStatus});

  final String? initialStatus;

  @override
  ConsumerState<IdeasPage> createState() => _IdeasPageState();
}

class _IdeasPageState extends ConsumerState<IdeasPage> {
  final _search = TextEditingController();
  bool _selecting = false;
  final Set<String> _selected = {};

  @override
  void initState() {
    super.initState();
    if (widget.initialStatus != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        ref
            .read(ideasControllerProvider.notifier)
            .setFilter(IdeasFilter(status: widget.initialStatus!));
      });
    } else {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        ref.read(ideasControllerProvider.notifier).load();
      });
    }
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(ideasControllerProvider);
    final user = ref.watch(currentUserProvider);
    final isAdmin = (user?['role'] as String?) == 'ADMIN';
    return AppShell(
      title: 'Ideas',
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(AppSpacing.md),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    _selecting
                        ? '${_selected.length} selected'
                        : '${state.total} matching ideas',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                if (isAdmin)
                  IconButton(
                    key: const Key('ideas_select_toggle'),
                    icon: Icon(
                      _selecting ? Icons.close : Icons.checklist_outlined,
                    ),
                    tooltip: _selecting ? 'Cancel selection' : 'Select ideas',
                    onPressed: () => setState(() {
                      _selecting = !_selecting;
                      _selected.clear();
                    }),
                  ),
                if (_selecting)
                  IconButton(
                    key: const Key('ideas_select_all'),
                    icon: const Icon(Icons.select_all),
                    tooltip: 'Select all on this page',
                    onPressed: () => setState(() {
                      final ids = state.items.map((e) => e.id).toSet();
                      if (_selected.length == ids.length) {
                        _selected.clear();
                      } else {
                        _selected
                          ..clear()
                          ..addAll(ids);
                      }
                    }),
                  ),
                IconButton(
                  key: const Key('ideas_refresh'),
                  icon: const Icon(Icons.refresh),
                  tooltip: 'Refresh',
                  onPressed: () =>
                      ref.read(ideasControllerProvider.notifier).load(),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
            child: Row(
              children: [
                Expanded(
                  child: DropdownButtonFormField<String>(
                    initialValue: state.filter.status,
                    decoration: const InputDecoration(labelText: 'Status'),
                    items: [
                      const DropdownMenuItem(
                        value: 'ACTIVE_ONLY',
                        child: Text('Active Only (default)'),
                      ),
                      const DropdownMenuItem(
                        value: '',
                        child: Text('All Statuses'),
                      ),
                      for (final s in ideaStatuses)
                        DropdownMenuItem(value: s, child: Text(s)),
                    ],
                    onChanged: (v) => ref
                        .read(ideasControllerProvider.notifier)
                        .setFilter(
                          state.filter.copyWith(status: v ?? 'ACTIVE_ONLY'),
                        ),
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: TextField(
                    controller: _search,
                    decoration: const InputDecoration(
                      labelText: 'Search',
                      prefixIcon: Icon(Icons.search),
                    ),
                    onSubmitted: (v) => ref
                        .read(ideasControllerProvider.notifier)
                        .setFilter(state.filter.copyWith(search: v)),
                  ),
                ),
              ],
            ),
          ),
          if (state.error != null)
            Padding(
              padding: const EdgeInsets.all(AppSpacing.sm),
              child: Text(
                state.error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
          Expanded(
            child: state.loading && state.items.isEmpty
                ? const Center(child: CircularProgressIndicator())
                : ListView.builder(
                    itemCount: state.items.length,
                    itemBuilder: (context, i) {
                      final idea = state.items[i];
                      return _IdeaCard(
                        idea: idea,
                        isAdmin: isAdmin,
                        selecting: _selecting,
                        selected: _selected.contains(idea.id),
                        onToggle: () => setState(() {
                          if (!_selected.remove(idea.id)) {
                            _selected.add(idea.id);
                          }
                        }),
                      );
                    },
                  ),
          ),
          if (_selecting) _bulkBar(context, state),
        ],
      ),
    );
  }

  /// Bottom action bar for multi-select: change state for every selected
  /// idea in one request (server skips illegal transitions and reports them).
  Widget _bulkBar(BuildContext context, IdeasState state) {
    final targets = <String>{};
    for (final idea in state.items) {
      if (_selected.contains(idea.id)) {
        targets.addAll(allowedTransitions[idea.status] ?? const []);
      }
    }
    return Material(
      elevation: 8,
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md,
            vertical: AppSpacing.sm,
          ),
          child: Row(
            children: [
              Expanded(child: Text('${_selected.length} selected')),
              FilledButton.icon(
                key: const Key('ideas_bulk_status'),
                icon: const Icon(Icons.swap_horiz, size: 18),
                label: const Text('Change status'),
                onPressed: _selected.isEmpty || targets.isEmpty
                    ? null
                    : () => _chooseBulkStatus(targets.toList()),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _chooseBulkStatus(List<String> targets) async {
    final count = _selected.length;
    final status = await showDialog<String>(
      context: context,
      builder: (ctx) => SimpleDialog(
        title: Text('Move $count idea${count == 1 ? '' : 's'} to…'),
        children: [
          for (final s in ideaStatuses.where(targets.contains))
            SimpleDialogOption(
              key: Key('bulk_status_$s'),
              onPressed: () => Navigator.of(ctx).pop(s),
              child: Text(s),
            ),
        ],
      ),
    );
    if (status == null || !mounted) return;

    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Change status?'),
        content: Text(
          'Move $count selected idea${count == 1 ? '' : 's'} to $status?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            key: const Key('bulk_status_confirm'),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Confirm'),
          ),
        ],
      ),
    );
    if (confirm != true || !mounted) return;

    final result = await ref
        .read(ideasControllerProvider.notifier)
        .bulkStatus(_selected.toList(), status);
    if (!mounted) return;
    if (result == null) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Could not change status')));
      return;
    }
    final moved = result['moved'] ?? 0;
    final skipped = (result['skipped'] as List? ?? const []).length;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          'Moved $moved idea${moved == 1 ? '' : 's'} to $status'
          '${skipped > 0 ? ' · $skipped skipped (illegal transition)' : ''}',
        ),
      ),
    );
    setState(() {
      _selecting = false;
      _selected.clear();
    });
  }
}

class _IdeaCard extends ConsumerWidget {
  const _IdeaCard({
    required this.idea,
    required this.isAdmin,
    this.selecting = false,
    this.selected = false,
    this.onToggle,
  });

  final IdeaSummary idea;
  final bool isAdmin;
  final bool selecting;
  final bool selected;
  final VoidCallback? onToggle;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Card(
      margin: const EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.xs,
      ),
      child: ListTile(
        leading: selecting
            ? Checkbox(
                key: Key('idea_select_${idea.id}'),
                value: selected,
                onChanged: (_) => onToggle?.call(),
              )
            : null,
        selected: selecting && selected,
        title: Text(
          idea.summary ?? idea.referenceCode,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
        ),
        subtitle: Wrap(
          spacing: AppSpacing.xs,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Text(
              idea.referenceCode,
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(fontFamily: 'monospace'),
            ),
            StatusPill(status: idea.status),
            Text('💬 ${idea.commentCount}'),
          ],
        ),
        trailing: selecting
            ? null
            : Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  IconButton(
                    icon: const Icon(Icons.arrow_upward, size: 20),
                    color: idea.userVote == 1
                        ? Theme.of(context).colorScheme.primary
                        : null,
                    onPressed: () => ref
                        .read(ideasControllerProvider.notifier)
                        .vote(idea.id, 1),
                  ),
                  Text('${idea.netScore}'),
                  IconButton(
                    icon: const Icon(Icons.arrow_downward, size: 20),
                    color: idea.userVote == -1
                        ? Theme.of(context).colorScheme.error
                        : null,
                    onPressed: () => ref
                        .read(ideasControllerProvider.notifier)
                        .vote(idea.id, -1),
                  ),
                  if (isAdmin)
                    PopupMenuButton<String>(
                      onSelected: (s) => _changeStatus(context, ref, s),
                      itemBuilder: (context) => [
                        for (final s
                            in allowedTransitions[idea.status] ?? <String>[])
                          PopupMenuItem(value: s, child: Text(s)),
                      ],
                    ),
                ],
              ),
        onTap: () {
          if (selecting) {
            onToggle?.call();
            return;
          }
          Navigator.of(context).pushNamed('/ideas/detail', arguments: idea.id);
        },
      ),
    );
  }

  Future<void> _changeStatus(
    BuildContext context,
    WidgetRef ref,
    String status,
  ) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Change status?'),
        content: Text('Move ${idea.referenceCode} to $status?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Confirm'),
          ),
        ],
      ),
    );
    if (confirm != true || !context.mounted) return;
    final ok = await ref
        .read(ideasControllerProvider.notifier)
        .changeStatus(idea.id, status);
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Illegal transition rejected')),
      );
    }
  }
}

/// Status pill shared by list, cards and detail (golden-tested).
class StatusPill extends StatelessWidget {
  const StatusPill({super.key, required this.status});

  final String status;

  @override
  Widget build(BuildContext context) {
    final color = AppColors.statusColor(status);
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: 2,
      ),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        status,
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
          color: color,
          fontWeight: FontWeight.bold,
        ),
      ),
    );
  }
}
