import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers.dart';

class IdeaPipelineRun {
  const IdeaPipelineRun({
    required this.runId,
    required this.ideaId,
    required this.referenceCode,
    required this.promptTitle,
    required this.status,
    this.createdAt,
  });

  final String runId;
  final String ideaId;
  final String referenceCode;
  final String promptTitle;
  final String status;
  final String? createdAt;

  factory IdeaPipelineRun.fromJson(Map<String, dynamic> json) => IdeaPipelineRun(
        runId: json['run_id']?.toString() ?? '',
        ideaId: json['idea_id']?.toString() ?? '',
        referenceCode: json['reference_code']?.toString() ?? '',
        promptTitle: json['prompt_title']?.toString() ?? '',
        status: json['status']?.toString() ?? 'PENDING',
        createdAt: json['created_at']?.toString(),
      );
}

class ReleasePipelineRun {
  const ReleasePipelineRun({
    required this.releaseId,
    required this.parentIdeaId,
    required this.name,
    required this.status,
    this.phase,
    this.error,
    this.total = 0,
    this.counts = const {},
  });

  final String releaseId;
  final String parentIdeaId;
  final String name;
  final String status;
  final String? phase;
  final String? error;
  final int total;
  final Map<String, dynamic> counts;

  factory ReleasePipelineRun.fromJson(Map<String, dynamic> json) =>
      ReleasePipelineRun(
        releaseId: json['release_id']?.toString() ?? '',
        parentIdeaId: json['parent_idea_id']?.toString() ?? '',
        name: json['name']?.toString() ?? 'Release',
        status: json['status']?.toString() ?? 'idle',
        phase: json['phase']?.toString(),
        error: json['error']?.toString(),
        total: (json['total'] as num?)?.toInt() ?? 0,
        counts: (json['counts'] is Map)
            ? Map<String, dynamic>.from(json['counts'] as Map)
            : const {},
      );
}

class PipelineStatusSnapshot {
  const PipelineStatusSnapshot({
    this.ideaRuns = const [],
    this.releaseRuns = const [],
  });

  static const empty = PipelineStatusSnapshot();

  final List<IdeaPipelineRun> ideaRuns;
  final List<ReleasePipelineRun> releaseRuns;

  bool get isEmpty => ideaRuns.isEmpty && releaseRuns.isEmpty;

  factory PipelineStatusSnapshot.fromJson(Map<String, dynamic> json) {
    final ideaRuns = <IdeaPipelineRun>[];
    for (final item in _list(json['idea_runs'])) {
      if (item is Map) {
        ideaRuns.add(
          IdeaPipelineRun.fromJson(Map<String, dynamic>.from(item)),
        );
      }
    }
    final releaseRuns = <ReleasePipelineRun>[];
    for (final item in _list(json['release_runs'])) {
      if (item is Map) {
        releaseRuns.add(
          ReleasePipelineRun.fromJson(Map<String, dynamic>.from(item)),
        );
      }
    }
    return PipelineStatusSnapshot(
      ideaRuns: ideaRuns,
      releaseRuns: releaseRuns,
    );
  }

  static List<dynamic> _list(dynamic value) => value is List ? value : const [];
}

const Map<String, String> _phaseLabels = {
  'prd': 'Brief',
  'design': 'Design',
  'build': 'Build',
  'test': 'Test',
  'done': 'Done',
};

/// Short label for the shell banner. `PENDING` is called "queued" because
/// that is what the user sees in the queue UI.
String ideaPipelineStatusLabel(IdeaPipelineRun run) {
  final state = run.status.toUpperCase() == 'PENDING' ? 'queued' : 'running';
  final reference = run.referenceCode.isNotEmpty
      ? run.referenceCode
      : run.promptTitle;
  return 'Full pipeline $state — $reference';
}

/// Short label for the shell banner, including the current phase and the
/// number of children through it when the release has a child report.
String releasePipelineStatusLabel(ReleasePipelineRun run) {
  final state = run.status == 'stopping' ? 'stopping' : 'running';
  final phaseKey = run.phase ?? '';
  final label = _phaseLabels[phaseKey] ?? (phaseKey.isEmpty ? 'Starting' : phaseKey);
  final done = run.counts[phaseKey] is num
      ? (run.counts[phaseKey] as num).toInt()
      : 0;
  final progress = run.total > 0 && done > 0 ? ' ($done/${run.total})' : '';
  return 'Release pipeline $state — ${run.name} · $label$progress';
}

/// Polls the active pipeline aggregate while signed in. The state comes from
/// the server, so it survives navigation and browser refresh.
final pipelineStatusProvider =
    StreamProvider<PipelineStatusSnapshot>((ref) {
  final api = ref.watch(apiClientProvider);
  final signedIn = ref.watch(
    currentUserProvider.select((user) => user != null),
  );
  final controller = StreamController<PipelineStatusSnapshot>.broadcast();

  if (!signedIn) {
    controller.add(PipelineStatusSnapshot.empty);
    controller.close();
    ref.onDispose(() {
      if (!controller.isClosed) controller.close();
    });
    return controller.stream;
  }

  Future<void> poll() async {
    try {
      final data = await api.get('/api/v1/pipeline/status');
      if (!controller.isClosed && data is Map) {
        controller.add(PipelineStatusSnapshot.fromJson(
          Map<String, dynamic>.from(data),
        ));
      }
    } catch (_) {
      // A transient failure must not blank the page. The last known status
      // stays on screen and the next tick retries.
    }
  }

  unawaited(poll());
  final timer = Timer.periodic(const Duration(seconds: 5), (_) {
    unawaited(poll());
  });
  ref.onDispose(() {
    timer.cancel();
    if (!controller.isClosed) controller.close();
  });
  return controller.stream;
});
