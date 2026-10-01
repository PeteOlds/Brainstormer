import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../core/theme/tokens.dart';
import '../chat/chat_repository.dart';
import 'idea_models.dart';
import 'ideas_controller.dart';
import 'ideas_page.dart';

final _detailProvider =
    FutureProvider.family<IdeaDetail, String>((ref, id) async {
  return ref.watch(ideasRepositoryProvider).detail(id);
});

final _commentsProvider = FutureProvider.family
    .autoDispose<List<IdeaComment>, ({String id, String? phase})>(
        (ref, args) async {
  return ref
      .watch(ideasRepositoryProvider)
      .comments(args.id, phase: args.phase);
});

/// Idea detail: overview, action result tabs, threaded comments with
/// phase filter, voting, admin status change, and the Chat tab.
class IdeaDetailPage extends ConsumerStatefulWidget {
  const IdeaDetailPage({super.key, required this.ideaId});

  final String ideaId;

  @override
  ConsumerState<IdeaDetailPage> createState() => _IdeaDetailPageState();
}

class _IdeaDetailPageState extends ConsumerState<IdeaDetailPage>
    with SingleTickerProviderStateMixin {
  late final TabController _tabs;
  String? _phaseFilter;
  final _commentDraft = TextEditingController();
  final _chatDraft = TextEditingController();

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 3, vsync: this);
  }

  @override
  void dispose() {
    _tabs.dispose();
    _commentDraft.dispose();
    _chatDraft.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final detail = ref.watch(_detailProvider(widget.ideaId));
    final user = ref.watch(currentUserProvider);
    final isAdmin = (user?['role'] as String?) == 'ADMIN';
    return Scaffold(
      appBar: AppBar(
        title: const Text('Idea detail'),
        bottom: TabBar(
          controller: _tabs,
          tabs: const [
            Tab(text: 'Idea'),
            Tab(text: 'Analysis'),
            Tab(text: 'Chat'),
          ],
        ),
      ),
      body: detail.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Failed to load: $e')),
        data: (d) => TabBarView(
          controller: _tabs,
          children: [
            _overviewTab(context, d, isAdmin),
            _analysisTab(context, d),
            _chatTab(context, d),
          ],
        ),
      ),
    );
  }

  Widget _overviewTab(
      BuildContext context, IdeaDetail detail, bool isAdmin) {
    final idea = detail.idea;
    final user = ref.watch(currentUserProvider);
    final canEdit = isAdmin || (idea.createdById != null &&
        idea.createdById == (user?['id']?.toString()));
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.md),
      children: [
        Row(
          children: [
            Text(idea.referenceCode,
                style: Theme.of(context)
                    .textTheme
                    .bodySmall
                    ?.copyWith(fontFamily: 'monospace')),
            const SizedBox(width: AppSpacing.sm),
            StatusPill(status: idea.status),
          ],
        ),
        const SizedBox(height: AppSpacing.sm),
        Text(idea.summary ?? '(no summary)',
            style: Theme.of(context).textTheme.bodyLarge),
        if (canEdit)
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
            IconButton(
              icon: const Icon(Icons.arrow_upward),
              color: idea.userVote == 1
                  ? Theme.of(context).colorScheme.primary
                  : null,
              onPressed: () => _vote(idea.id, 1),
            ),
            Text('${idea.netScore}'),
            IconButton(
              icon: const Icon(Icons.arrow_downward),
              color: idea.userVote == -1
                  ? Theme.of(context).colorScheme.error
                  : null,
              onPressed: () => _vote(idea.id, -1),
            ),
            const Spacer(),
            if (isAdmin)
              DropdownButton<String>(
                value: ideaStatuses.contains(idea.status)
                    ? idea.status
                    : null,
                hint: const Text('Change status'),
                items: [
                  for (final s
                      in allowedTransitions[idea.status] ?? <String>[])
                    DropdownMenuItem(value: s, child: Text(s)),
                ],
                onChanged: (s) =>
                    s == null ? null : _changeStatus(idea.id, s),
              ),
          ],
        ),
        const Divider(),
        Row(
          children: [
            const Text('Comments'),
            const Spacer(),
            DropdownButton<String?>(
              value: _phaseFilter,
              hint: const Text('All phases'),
              items: [
                const DropdownMenuItem(value: null, child: Text('All phases')),
                for (final s in ideaStatuses)
                  DropdownMenuItem(value: s, child: Text(s)),
              ],
              onChanged: (v) => setState(() => _phaseFilter = v),
            ),
          ],
        ),
        _commentsList(),
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _commentDraft,
                decoration:
                    const InputDecoration(labelText: 'Write a comment…'),
                maxLength: 2000,
              ),
            ),
            IconButton(
              key: const Key('comment_post'),
              icon: const Icon(Icons.send),
              onPressed: _postComment,
            ),
          ],
        ),
      ],
    );
  }

  Widget _commentsList() {
    final comments = ref.watch(_commentsProvider(
        (id: widget.ideaId, phase: _phaseFilter)));
    return comments.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Text('Comments failed: $e'),
      data: (items) => Column(
        children: [
          for (final c in items) _commentTile(c, 0),
        ],
      ),
    );
  }

  Widget _commentTile(IdeaComment comment, int depth) {
    return Padding(
      padding: EdgeInsets.only(left: depth * 16.0, top: 4),
      child: Card(
        child: ListTile(
          dense: true,
          title: Text(comment.body),
          subtitle: Wrap(
            spacing: AppSpacing.xs,
            children: [
              if (comment.author != null) Text(comment.author!),
              if (comment.phase != null) Text('[${comment.phase}]'),
              if (comment.isIgnored == true)
                const Text('[ignored]',
                    style: TextStyle(fontStyle: FontStyle.italic)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _analysisTab(BuildContext context, IdeaDetail detail) {
    if (detail.actions.isEmpty) {
      return const Center(child: Text('No analyses yet.'));
    }
    return ListView.builder(
      padding: const EdgeInsets.all(AppSpacing.md),
      itemCount: detail.actions.length,
      itemBuilder: (context, i) {
        final action = detail.actions[i];
        return Card(
          child: ListTile(
            title: Text(
                '${action.actionType} v${action.version}${action.isCurrent ? ' (current)' : ''}'),
            subtitle: Text(
              (action.output?.keys.take(5).join(', ') ?? ''),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        );
      },
    );
  }

  Widget _chatTab(BuildContext context, IdeaDetail detail) {
    final sessions = ref.watch(chatSessionsProvider(widget.ideaId));
    return Column(
      children: [
        Expanded(
          child: sessions.when(
            loading: () =>
                const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(child: Text('Chat failed: $e')),
            data: (items) => items.isEmpty
                ? const Center(
                    child: Text('No messages yet — start the conversation.'))
                : ListView.builder(
                    padding:
                        const EdgeInsets.all(AppSpacing.md),
                    itemCount: items.expand((s) => s.turns).length,
                    itemBuilder: (context, i) {
                      final turn =
                          items.expand((s) => s.turns).toList()[i];
                      final mine = turn.role == 'user';
                      return Align(
                        alignment: mine
                            ? Alignment.centerRight
                            : Alignment.centerLeft,
                        child: Container(
                          margin: const EdgeInsets.symmetric(
                              vertical: AppSpacing.xs),
                          padding: const EdgeInsets.all(AppSpacing.sm),
                          decoration: BoxDecoration(
                            color: mine
                                ? Theme.of(context)
                                    .colorScheme
                                    .primaryContainer
                                : Theme.of(context)
                                    .colorScheme
                                    .surfaceContainerHighest,
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Text(turn.content),
                        ),
                      );
                    },
                  ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _chatDraft,
                  decoration:
                      const InputDecoration(labelText: 'Chat with the AI…'),
                  maxLength: 4000,
                ),
              ),
              IconButton(
                key: const Key('chat_send'),
                icon: const Icon(Icons.send),
                onPressed: _sendChat,
              ),
            ],
          ),
        ),
      ],
    );
  }

  Future<void> _vote(String id, int direction) async {
    await ref.read(ideasControllerProvider.notifier).vote(id, direction);
    ref.invalidate(_detailProvider(widget.ideaId));
  }

  Future<void> _editTitle(IdeaSummary idea) async {
    final controller =
        TextEditingController(text: idea.promptTitle);
    final save = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Edit title'),
        content: TextField(
          controller: controller,
          maxLength: 200,
          decoration: const InputDecoration(labelText: 'Title'),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Save')),
        ],
      ),
    );
    final title = controller.text.trim();
    controller.dispose();
    if (save != true || !mounted) return;
    try {
      await ref
          .read(ideasRepositoryProvider)
          .updateContent(idea.id, {'prompt_title': title});
      ref.invalidate(_detailProvider(widget.ideaId));
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Edit failed: $e')),
        );
      }
    }
  }

  Future<void> _changeStatus(String id, String status) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Change status?'),
        content: Text('Move to $status?'),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Confirm')),
        ],
      ),
    );
    if (confirm != true) return;
    final ok = await ref
        .read(ideasControllerProvider.notifier)
        .changeStatus(id, status);
    if (!ok && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Illegal transition rejected')),
      );
    }
    ref.invalidate(_detailProvider(widget.ideaId));
  }

  Future<void> _postComment() async {
    final text = _commentDraft.text.trim();
    if (text.isEmpty) return;
    try {
      final applied = await ref
          .read(ideasControllerProvider.notifier)
          .postComment(widget.ideaId, text);
      _commentDraft.clear();
      ref.invalidate(
          _commentsProvider((id: widget.ideaId, phase: _phaseFilter)));
      if (!applied && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
              content: Text('Offline — comment queued, will retry.')),
        );
      }
    } on Exception catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Comment failed: $e')),
        );
      }
    }
  }

  Future<void> _sendChat() async {
    final text = _chatDraft.text.trim();
    if (text.isEmpty) return;
    try {
      await ref
          .read(chatRepositoryProvider)
          .send(widget.ideaId, text);
      _chatDraft.clear();
      ref.invalidate(chatSessionsProvider(widget.ideaId));
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Chat failed: $e')),
        );
      }
    }
  }
}
