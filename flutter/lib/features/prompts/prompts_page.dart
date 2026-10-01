import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../core/theme/tokens.dart';
import '../../core/widgets/app_shell.dart';
import 'prompt_models.dart';
import 'prompts_repository.dart';

/// Prompt list: title, provider/model, active toggle state, run-now.
class PromptsPage extends ConsumerWidget {
  const PromptsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final prompts = ref.watch(promptsListProvider);
    final user = ref.watch(currentUserProvider);
    final isAdmin = (user?['role'] as String?) == 'ADMIN';
    return AppShell(
      title: 'Prompts',
      child: Column(
        children: [
          if (isAdmin)
            Padding(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  key: const Key('prompt_create'),
                  icon: const Icon(Icons.add),
                  label: const Text('Create Prompt'),
                  onPressed: () => Navigator.of(context)
                      .pushNamed('/prompts/form')
                      .then((_) => ref.invalidate(promptsListProvider)),
                ),
              ),
            ),
          Expanded(
            child: prompts.when(
              loading: () =>
                  const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(child: Text('Failed to load: $e')),
              data: (items) => ListView.builder(
                itemCount: items.length,
                itemBuilder: (context, i) =>
                    _PromptTile(prompt: items[i], isAdmin: isAdmin),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _PromptTile extends ConsumerWidget {
  const _PromptTile({required this.prompt, required this.isAdmin});

  final PromptSummary prompt;
  final bool isAdmin;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Card(
      margin: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md, vertical: AppSpacing.xs),
      child: ListTile(
        title: Text(prompt.title),
        subtitle: Text(
            '${prompt.provider} · ${prompt.modelName} · ${prompt.isActive ? 'active' : 'paused'}'),
        trailing: isAdmin
            ? PopupMenuButton<String>(
                onSelected: (v) => _act(context, ref, v),
                itemBuilder: (context) => const [
                  PopupMenuItem(value: 'run', child: Text('Run Now')),
                  PopupMenuItem(value: 'edit', child: Text('Edit')),
                  PopupMenuItem(value: 'delete', child: Text('Delete')),
                ],
              )
            : null,
      ),
    );
  }

  Future<void> _act(
      BuildContext context, WidgetRef ref, String action) async {
    final repo = ref.read(promptsRepositoryProvider);
    try {
      switch (action) {
        case 'run':
          await repo.runNow(prompt.id);
          if (context.mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('Run enqueued')),
            );
          }
        case 'edit':
          if (context.mounted) {
            Navigator.of(context).pushNamed('/prompts/form',
                arguments: prompt.id);
          }
        case 'delete':
          final confirm = await showDialog<bool>(
            context: context,
            builder: (context) => AlertDialog(
              title: const Text('Delete prompt?'),
              actions: [
                TextButton(
                    onPressed: () =>
                        Navigator.of(context).pop(false),
                    child: const Text('Cancel')),
                FilledButton(
                    onPressed: () =>
                        Navigator.of(context).pop(true),
                    child: const Text('Delete')),
              ],
            ),
          );
          if (confirm == true) {
            await repo.remove(prompt.id);
            ref.invalidate(promptsListProvider);
          }
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed: $e')),
        );
      }
    }
  }
}
