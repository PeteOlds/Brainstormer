import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../pipeline/pipeline_status_provider.dart';
import '../theme/tokens.dart';

/// Bottom status strip shared by every routed page. Reads server-backed
/// status, so it survives navigation and a browser refresh.
class PipelineStatusBanner extends ConsumerWidget {
  const PipelineStatusBanner({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final status = ref.watch(pipelineStatusProvider);
    final snapshot = status.valueOrNull;
    if (snapshot == null || snapshot.isEmpty) return const SizedBox.shrink();

    final rows = <Widget>[
      for (final run in snapshot.ideaRuns)
        Padding(
          key: ValueKey('idea_${run.runId}'),
          padding: const EdgeInsets.only(top: 2),
          child: Text(
            ideaPipelineStatusLabel(run),
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ),
      for (final run in snapshot.releaseRuns)
        Padding(
          key: ValueKey('release_${run.releaseId}'),
          padding: const EdgeInsets.only(top: 2),
          child: Text(
            releasePipelineStatusLabel(run),
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ),
    ];

    return Container(
      key: const Key('pipeline_status_banner'),
      width: double.infinity,
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.xs,
      ),
      color: Theme.of(context).colorScheme.primaryContainer,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.pending_actions,
                size: 14,
                color: Theme.of(context).colorScheme.onPrimaryContainer,
              ),
              const SizedBox(width: AppSpacing.xs),
              Text(
                'Pipeline activity',
                style: Theme.of(context).textTheme.labelSmall?.copyWith(
                      color: Theme.of(context).colorScheme.onPrimaryContainer,
                    ),
              ),
            ],
          ),
          ...rows,
        ],
      ),
    );
  }
}
