/// Typed model for Agent Event (DATA_MODEL.md §3, FEATURES.md F5).
class AgentEvent {
  final String id;
  final String scanId;
  final int seq;
  final DateTime timestamp;
  final String agent;
  final String kind;
  final String title;
  final String detail;
  final String plain;
  final String? severity;
  final Map<String, dynamic> refs;
  final Map<String, dynamic>? budget;
  final int schemaVersion;

  const AgentEvent({
    required this.id,
    required this.scanId,
    required this.seq,
    required this.timestamp,
    required this.agent,
    required this.kind,
    required this.title,
    this.detail = '',
    this.plain = '',
    this.severity,
    this.refs = const {},
    this.budget,
    this.schemaVersion = 1,
  });

  factory AgentEvent.fromJson(Map<String, dynamic> json) {
    return AgentEvent(
      id: json['id'] as String? ?? '',
      scanId: (json['scanId'] ?? json['scan_id']) as String? ?? '',
      seq: json['seq'] as int? ?? 0,
      timestamp: json['timestamp'] != null
          ? DateTime.parse(json['timestamp'] as String)
          : DateTime.now(),
      agent: json['agent'] as String? ?? 'system',
      kind: json['kind'] as String? ?? 'info',
      title: json['title'] as String? ?? '',
      detail: json['detail'] as String? ?? '',
      plain: json['plain'] as String? ?? '',
      severity: json['severity'] as String?,
      refs: (json['refs'] as Map?)?.cast<String, dynamic>() ?? const {},
      budget: (json['budget'] as Map?)?.cast<String, dynamic>(),
      schemaVersion: json['schema_version'] as int? ?? 1,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'scanId': scanId,
      'seq': seq,
      'timestamp': timestamp.toIso8601String(),
      'agent': agent,
      'kind': kind,
      'title': title,
      'detail': detail,
      'plain': plain,
      if (severity != null) 'severity': severity,
      'refs': refs,
      if (budget != null) 'budget': budget,
      'schema_version': schemaVersion,
    };
  }
}
