import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/finding.dart';
import '../models/scan_detail.dart';
import '../models/scan_summary.dart';
import 'findings_provider.dart';
import 'scans_provider.dart';

/// Live scan state for [scanId], assembled from the scan record and its
/// findings.
///
/// Agent card states are derived from the backend's reported stage and
/// counters — never invented client-side. Returns null while loading or if the
/// scan cannot be read, which renders as an honest "not connected" state.
final scanDetailProvider =
    Provider.family<ScanDetailState?, String>((ref, scanId) {
  final scanAsync = ref.watch(scanProvider(scanId));
  final findingsAsync = ref.watch(scanFindingsProvider(scanId));

  final scan = scanAsync.asData?.value;
  if (scan == null) return null;

  final findings = findingsAsync.asData?.value ?? const <Finding>[];
  final confirmed =
      findings.where((f) => f.status == FindingStatus.confirmed).toList();
  final verified = confirmed
      .where((f) => f.remediationStatus == RemediationStatus.fixVerified)
      .length;
  final patched = confirmed
      .where((f) => f.remediationStatus != RemediationStatus.notStarted)
      .length;

  return ScanDetailState(
    scanId: scanId,
    agentCards: _cardsForStage(scan, confirmedCount: confirmed.length),
    events: const [],
    summary: ScanRunSummary(
      findingsDiscovered: findings.length,
      findingsConfirmed: confirmed.length,
      fixesGenerated: patched,
      fixesVerified: verified,
    ),
  );
});

/// Order the pipeline executes in — used to decide which agents are done.
const _pipelineOrder = <AgentRole>[
  AgentRole.builder,
  AgentRole.attacker,
  AgentRole.evaluator,
  AgentRole.fixer,
];

/// Maps the backend's reported stage onto per-agent card states.
Map<AgentRole, AgentCardState> _cardsForStage(
  ScanSummary scan, {
  required int confirmedCount,
}) {
  final stage = scan.stage.toLowerCase();
  final finished = scan.isTerminal && scan.state == ScanState.completed;
  final failed = scan.state == ScanState.failed;

  int activeIndex = switch (stage) {
    final s when s.contains('build') || s.contains('discover') => 0,
    final s when s.contains('attack') || s.contains('test') => 1,
    final s when s.contains('evaluat') => 2,
    final s when s.contains('fix') || s.contains('patch') || s.contains('verif') => 3,
    _ => finished ? _pipelineOrder.length : 0,
  };
  if (finished) activeIndex = _pipelineOrder.length;

  return {
    for (var i = 0; i < _pipelineOrder.length; i++)
      _pipelineOrder[i]: AgentCardState(
        role: _pipelineOrder[i],
        status: switch (0) {
          _ when finished => AgentStatus.completed,
          _ when failed && i == activeIndex => AgentStatus.failed,
          _ when i < activeIndex => AgentStatus.completed,
          _ when i == activeIndex => AgentStatus.running,
          _ => AgentStatus.idle,
        },
        currentTask: i == activeIndex && !finished
            ? (scan.stage.isEmpty ? null : scan.stage)
            : null,
        eventCount: i == 2 ? confirmedCount : 0,
      ),
  };
}
