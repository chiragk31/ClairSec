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
  final int endpointsDiscovered;
  final int testsExecuted;
  final int testsGenerated;
  final int testsSkippedPolicy;
  final int testsFailedError;
  final int findingsDiscovered;
  final int fixesGenerated;
  final int fixesVerified;
  final Map<String, double> stageDurations;

  const ScanSummary({
    required this.id,
    required this.projectName,
    required this.state,
    required this.startedAt,
    this.findingsConfirmed = 0,
    this.projectId = '',
    this.stage = '',
    this.endpointsDiscovered = 0,
    this.testsExecuted = 0,
    this.testsGenerated = 0,
    this.testsSkippedPolicy = 0,
    this.testsFailedError = 0,
    this.findingsDiscovered = 0,
    this.fixesGenerated = 0,
    this.fixesVerified = 0,
    this.stageDurations = const {},
  });

  factory ScanSummary.fromJson(Map<String, dynamic> json) {
    final counters = json['counters'] is Map ? (json['counters'] as Map) : null;
    final durationsRaw = json['stageDurations'] ?? json['stage_durations'];
    final Map<String, double> durations = durationsRaw is Map
        ? durationsRaw.map((k, v) => MapEntry(k.toString(), (v as num).toDouble()))
        : const {};

    return ScanSummary(
      id: json['id'] as String,
      projectId: (json['projectId'] ?? json['project_id'] ?? '') as String,
      projectName:
          (json['projectName'] ?? json['project_name'] ?? 'Unknown project') as String,
      state: _stateFrom(json['state'] as String?),
      stage: json['stage'] as String? ?? '',
      findingsConfirmed:
          (json['findingsConfirmed'] ?? json['findings_confirmed'] ?? counters?['confirmed'] ?? 0) as int,
      endpointsDiscovered: (json['endpointsDiscovered'] ??
          json['endpoints_discovered'] ??
          counters?['endpoints_discovered'] ??
          0) as int,
      testsExecuted: (json['testsExecuted'] ??
          json['tests_executed'] ??
          counters?['tests_executed'] ??
          0) as int,
      testsGenerated: (json['testsGenerated'] ??
          json['tests_generated'] ??
          counters?['tests_generated'] ??
          0) as int,
      testsSkippedPolicy: (json['testsSkippedPolicy'] ??
          json['tests_skipped_policy'] ??
          counters?['tests_skipped_policy'] ??
          0) as int,
      testsFailedError: (json['testsFailedError'] ??
          json['tests_failed_error'] ??
          counters?['tests_failed_error'] ??
          0) as int,
      findingsDiscovered: (json['findingsDiscovered'] ??
          json['findings_discovered'] ??
          counters?['candidates'] ??
          0) as int,
      fixesGenerated: (json['fixesGenerated'] ??
          json['fixes_generated'] ??
          counters?['fixes_proposed'] ??
          0) as int,
      fixesVerified: (json['fixesVerified'] ??
          json['fixes_verified'] ??
          counters?['fixes_verified'] ??
          0) as int,
      stageDurations: durations,
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
