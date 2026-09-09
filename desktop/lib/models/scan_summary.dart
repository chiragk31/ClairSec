/// Coarse scan state for list/summary views (dashboard, scan history).
/// Mirrors the terminal/non-terminal states in ARCHITECTURE.md §5 — this is
/// intentionally a smaller vocabulary than the full agent-by-agent state
/// machine, which belongs to [ScanDetailState] instead.
enum ScanState { running, completed, failed, cancelled, partial }

extension ScanStateX on ScanState {
  String get label => switch (this) {
        ScanState.running => 'Running',
        ScanState.completed => 'Completed',
        ScanState.failed => 'Failed',
        ScanState.cancelled => 'Cancelled',
        ScanState.partial => 'Partial',
      };
}

/// A row in a scan list (dashboard "recent scans", future scan history).
/// Deliberately minimal — the full live detail lives in [ScanDetailState].
class ScanSummary {
  final String id;
  final String projectName;
  final ScanState state;
  final DateTime startedAt;
  final int findingsConfirmed;

  final String projectId;
  final String stage;

  const ScanSummary({
    required this.id,
    required this.projectName,
    required this.state,
    required this.startedAt,
    this.findingsConfirmed = 0,
    this.projectId = '',
    this.stage = '',
  });

  factory ScanSummary.fromJson(Map<String, dynamic> json) {
    return ScanSummary(
      id: json['id'] as String,
      projectId: (json['projectId'] ?? json['project_id'] ?? '') as String,
      projectName:
          (json['projectName'] ?? json['project_name'] ?? 'Unknown project') as String,
      state: _stateFrom(json['state'] as String?),
      stage: json['stage'] as String? ?? '',
      findingsConfirmed:
          (json['findingsConfirmed'] ?? json['findings_confirmed'] ?? 0) as int,
      startedAt: DateTime.tryParse((json['startedAt'] ??
                  json['started_at'] ??
                  json['createdAt'] ??
                  json['created_at'] ??
                  '') as String) ??
          DateTime.now(),
    );
  }

  static ScanState _stateFrom(String? raw) => switch (raw?.toLowerCase()) {
        'completed' => ScanState.completed,
        'failed' => ScanState.failed,
        'cancelled' => ScanState.cancelled,
        'partial' => ScanState.partial,
        _ => ScanState.running,
      };

  bool get isTerminal =>
      state == ScanState.completed ||
      state == ScanState.failed ||
      state == ScanState.cancelled ||
      state == ScanState.partial;
}
