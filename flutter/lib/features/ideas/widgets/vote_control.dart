import 'package:flutter/material.dart';

import '../idea_models.dart';

/// Reusable vote control that mirrors the Jinja implementation: the server
/// is the source of truth, buttons disable while a vote is in flight, and
/// the visible score comes straight from the payload.
class VoteControl extends StatelessWidget {
  const VoteControl({
    super.key,
    required this.idea,
    required this.busy,
    required this.onVote,
  });

  final IdeaSummary idea;
  final bool busy;
  final void Function(int direction) onVote;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        IconButton.filledTonal(
          key: const Key('vote_up'),
          tooltip: 'Upvote',
          onPressed: busy ? null : () => onVote(1),
          icon: const Icon(Icons.thumb_up, size: 18),
          style: IconButton.styleFrom(
            minimumSize: const Size(32, 32),
            padding: const EdgeInsets.all(4),
            backgroundColor:
                idea.userVote == 1 ? cs.primaryContainer : null,
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4),
          child: Semantics(
            label: 'Score ${idea.netScore}',
            child: Text(
              '${idea.netScore}',
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ),
        ),
        IconButton.filledTonal(
          key: const Key('vote_down'),
          tooltip: 'Downvote',
          onPressed: busy ? null : () => onVote(-1),
          icon: const Icon(Icons.thumb_down, size: 18),
          style: IconButton.styleFrom(
            minimumSize: const Size(32, 32),
            padding: const EdgeInsets.all(4),
            backgroundColor:
                idea.userVote == -1 ? cs.errorContainer : null,
          ),
        ),
      ],
    );
  }
}