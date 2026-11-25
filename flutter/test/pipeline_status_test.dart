import 'package:brainstormer/core/pipeline/pipeline_status_provider.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('parses the compact server aggregate', () {
    final snapshot = PipelineStatusSnapshot.fromJson({
      'idea_runs': [
        {
          'run_id': 'r1',
          'idea_id': 'i1',
          'reference_code': 'IDEA-1001',
          'prompt_title': 'Idea',
          'status': 'PENDING',
        },
      ],
      'release_runs': [
        {
          'release_id': 'rel1',
          'parent_idea_id': 'i2',
          'name': 'Release 2.0',
          'status': 'running',
          'phase': 'build',
          'total': 4,
          'counts': {'prd': 4, 'design': 4, 'build': 2},
        },
      ],
    });

    expect(snapshot.ideaRuns.single.referenceCode, 'IDEA-1001');
    expect(snapshot.releaseRuns.single.total, 4);
  });

  test('formats queued, running and stopping labels', () {
    expect(
      ideaPipelineStatusLabel(
        const IdeaPipelineRun(
          runId: 'r',
          ideaId: 'i',
          referenceCode: 'IDEA-1',
          promptTitle: 'Idea',
          status: 'PENDING',
        ),
      ),
      'Full pipeline queued — IDEA-1',
    );
    expect(
      releasePipelineStatusLabel(
        const ReleasePipelineRun(
          releaseId: 'r',
          parentIdeaId: 'i',
          name: 'Release 1.0',
          status: 'running',
          phase: 'prd',
          total: 2,
          counts: {'prd': 1},
        ),
      ),
      'Release pipeline running — Release 1.0 · Brief (1/2)',
    );
    expect(
      releasePipelineStatusLabel(
        const ReleasePipelineRun(
          releaseId: 'r',
          parentIdeaId: 'i',
          name: 'Release 1.0',
          status: 'stopping',
          phase: 'test',
        ),
      ),
      'Release pipeline stopping — Release 1.0 · Test',
    );
  });
}
