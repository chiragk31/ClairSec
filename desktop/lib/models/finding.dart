import 'package:flutter/material.dart';
import '../core/theme/tokens.dart';

/// Verification state of a candidate finding (PRD.md §8, SECURITY.md §11).
/// This is about whether the finding IS a real vulnerability — not about
/// whether it has been fixed. See [RemediationStatus] for that axis.
enum FindingStatus { candidate, confirmed, rejected, inconclusive }

extension FindingStatusX on FindingStatus {
  String get label => switch (this) {
        FindingStatus.candidate => 'Candidate',
        FindingStatus.confirmed => 'Confirmed',
        FindingStatus.rejected => 'Rejected',
        FindingStatus.inconclusive => 'Inconclusive',
      };

  IconData get icon => switch (this) {
        FindingStatus.candidate => Icons.hourglass_empty,
        FindingStatus.confirmed => Icons.gpp_bad_outlined,
        FindingStatus.rejected => Icons.block_outlined,
        FindingStatus.inconclusive => Icons.help_outline,
      };

  /// Rejected is deliberately NOT rendered as "success" green — SECURITY.md
  /// §11 warns against implying "Secure" merely because a candidate was
  /// dismissed. It gets a neutral, not a reassuring, colour.
  Color color(ClairTokens tokens) => switch (this) {
        FindingStatus.candidate => tokens.accent,
        FindingStatus.confirmed => tokens.critical,
        FindingStatus.rejected => tokens.textSecondary,
        FindingStatus.inconclusive => tokens.warning,
      };
}

/// Post-confirmation remediation lifecycle (SECURITY.md §11 + Phase 8 states).
enum RemediationStatus {
  notStarted,
  fixProposed,
  fixApplied,
  fixVerified,
  fixFailed,
  regressed,
  verificationUnavailable,
}

extension RemediationStatusX on RemediationStatus {
  String get label => switch (this) {
        RemediationStatus.notStarted => 'Not started',
        RemediationStatus.fixProposed => 'Fix proposed',
        RemediationStatus.fixApplied => 'Fix applied',
        RemediationStatus.fixVerified => 'Fix verified',
        RemediationStatus.fixFailed => 'Fix failed',
        RemediationStatus.regressed => 'Regressed',
        RemediationStatus.verificationUnavailable => 'Verification unavailable',
      };

  IconData get icon => switch (this) {
        RemediationStatus.notStarted => Icons.radio_button_unchecked,
        RemediationStatus.fixProposed => Icons.lightbulb_outline,
        RemediationStatus.fixApplied => Icons.build_outlined,
        RemediationStatus.fixVerified => Icons.verified_outlined,
        RemediationStatus.fixFailed => Icons.error_outline,
        RemediationStatus.regressed => Icons.warning_amber_outlined,
        RemediationStatus.verificationUnavailable => Icons.help_outline,
      };

  Color color(ClairTokens tokens) => switch (this) {
        RemediationStatus.notStarted => tokens.textMuted,
        RemediationStatus.fixProposed => tokens.accent,
        RemediationStatus.fixApplied => tokens.accent,
        RemediationStatus.fixVerified => tokens.success,
        RemediationStatus.fixFailed => tokens.critical,
        RemediationStatus.regressed => tokens.warning,
        RemediationStatus.verificationUnavailable => tokens.warning,
      };
}

enum ConfidenceLevel { high, medium, low }

extension ConfidenceLevelX on ConfidenceLevel {
  String get label => switch (this) {
        ConfidenceLevel.high => 'High confidence',
        ConfidenceLevel.medium => 'Medium confidence',
        ConfidenceLevel.low => 'Low confidence',
      };
}

/// Severity band. Re-derives the semantic token mapping rather than importing AppColors.
enum FindingSeverity { critical, high, medium, low, informational }

extension FindingSeverityX on FindingSeverity {
  String get label => switch (this) {
        FindingSeverity.critical => 'Critical',
        FindingSeverity.high => 'High',
        FindingSeverity.medium => 'Medium',
        FindingSeverity.low => 'Low',
        FindingSeverity.informational => 'Informational',
      };

  IconData get icon => switch (this) {
        FindingSeverity.critical => Icons.cancel_outlined,
        FindingSeverity.high => Icons.error_outline,
        FindingSeverity.medium => Icons.warning_amber_outlined,
        FindingSeverity.low => Icons.info_outline,
        FindingSeverity.informational => Icons.circle_outlined,
      };

  Color color(ClairTokens tokens) => switch (this) {
        FindingSeverity.critical => tokens.critical,
        FindingSeverity.high => tokens.high,
        FindingSeverity.medium => tokens.medium,
        FindingSeverity.low => tokens.low,
        FindingSeverity.informational => tokens.info,
      };
}

class SourceLocation {
  final String file;
  final int lineStart;
  final int lineEnd;

  const SourceLocation({
    required this.file,
    required this.lineStart,
    required this.lineEnd,
  });

  String get display => lineStart == lineEnd ? '$file:$lineStart' : '$file:$lineStart-$lineEnd';

  factory SourceLocation.fromJson(Map<String, dynamic> json) {
    final start = (json['lineStart'] ?? json['line_start'] ?? 1) as int;
    return SourceLocation(
      file: (json['file'] ?? json['path'] ?? '') as String,
      lineStart: start,
      lineEnd: (json['lineEnd'] ?? json['line_end'] ?? start) as int,
    );
  }
}

/// Client-side finding record. Field set mirrors PRD.md §8 and
/// DATA_MODEL.md §3 (`findings`) — kept to what the Vulnerabilities screen
/// (DESIGN.md §7) actually displays; full evidence payloads stay server-side
/// and are fetched separately when a user drills into evidence detail.
class Finding {
  final String id;
  final String scanId;
  final String title;
  final String category; // VULN_TAXONOMY.md §2 category id, e.g. "BOLA"
  final String cwe;
  final FindingSeverity severity;
  final ConfidenceLevel confidence;
  final String routeTemplate;
  final String method;
  final String description;
  final String impact;
  final bool runtimeConfirmed;
  final FindingStatus status;
  final bool hasOracleEvidence;
  final String? statusReason;
  final String? evidenceSummary;
  final String? reproductionSummary;
  final List<SourceLocation> sourceLocations;
  final RemediationStatus remediationStatus;
  final DateTime createdAt;

  const Finding({
    required this.id,
    required this.scanId,
    required this.title,
    required this.category,
    required this.cwe,
    required this.severity,
    required this.confidence,
    required this.routeTemplate,
    required this.method,
    required this.description,
    required this.impact,
    required this.runtimeConfirmed,
    required this.status,
    required this.createdAt,
    this.hasOracleEvidence = true,
    this.statusReason,
    this.evidenceSummary,
    this.reproductionSummary,
    this.sourceLocations = const [],
    this.remediationStatus = RemediationStatus.notStarted,
  });

  bool get isConfirmed =>
      status == FindingStatus.confirmed && runtimeConfirmed && hasOracleEvidence;

  factory Finding.fromJson(Map<String, dynamic> json) {
    final hasOracleRaw = json['hasOracleEvidence'] ?? json['has_oracle_evidence'];
    final bool hasOracle = hasOracleRaw != null
        ? (hasOracleRaw as bool)
        : ((json['oracle_result'] != null ||
            json['oracle_evaluation'] != null ||
            (json['oracle_rule_id'] != null &&
                json['oracle_rule_id'].toString().isNotEmpty) ||
            (json['status'] == 'confirmed' &&
                (json['runtimeConfirmed'] == true ||
                    json['runtime_confirmed'] == true))));

    return Finding(
      id: json['id'] as String,
      scanId: (json['scanId'] ?? json['scan_id'] ?? '') as String,
      title: json['title'] as String? ?? 'Untitled finding',
      category: json['category'] as String? ?? '',
      cwe: json['cwe'] as String? ?? '',
      severity: _severityFrom(json['severity'] as String?),
      confidence: _confidenceFrom(json['confidence'] as String?),
      routeTemplate:
          (json['routeTemplate'] ?? json['route_template'] ?? '') as String,
      method: json['method'] as String? ?? '',
      description: json['description'] as String? ?? '',
      impact: json['impact'] as String? ?? '',
      runtimeConfirmed:
          (json['runtimeConfirmed'] ?? json['runtime_confirmed'] ?? false) as bool,
      status: _statusFrom(json['status'] as String?),
      hasOracleEvidence: hasOracle,
      statusReason: (json['statusReason'] ?? json['status_reason']) as String?,
      evidenceSummary:
          (json['evidenceSummary'] ?? json['evidence_summary']) as String?,
      reproductionSummary:
          (json['reproductionSummary'] ?? json['reproduction_summary']) as String?,
      sourceLocations: ((json['sourceLocations'] ?? json['source_locations'])
                  as List<dynamic>? ??
              const [])
          .map((e) => SourceLocation.fromJson(e as Map<String, dynamic>))
          .toList(),
      remediationStatus: _remediationFrom(
          (json['remediationStatus'] ?? json['remediation_status']) as String?),
      createdAt: DateTime.tryParse(
              (json['createdAt'] ?? json['created_at'] ?? '') as String) ??
          DateTime.now(),
    );
  }

  static FindingSeverity _severityFrom(String? raw) => switch (raw?.toLowerCase()) {
        'critical' => FindingSeverity.critical,
        'high' => FindingSeverity.high,
        'medium' => FindingSeverity.medium,
        'low' => FindingSeverity.low,
        _ => FindingSeverity.informational,
      };

  static ConfidenceLevel _confidenceFrom(String? raw) => switch (raw?.toLowerCase()) {
        'high' => ConfidenceLevel.high,
        'medium' => ConfidenceLevel.medium,
        _ => ConfidenceLevel.low,
      };

  static FindingStatus _statusFrom(String? raw) => switch (raw?.toLowerCase()) {
        'confirmed' => FindingStatus.confirmed,
        'rejected' => FindingStatus.rejected,
        'inconclusive' => FindingStatus.inconclusive,
        _ => FindingStatus.candidate,
      };

  static RemediationStatus _remediationFrom(String? raw) => switch (raw) {
        'fixProposed' => RemediationStatus.fixProposed,
        'fixApplied' => RemediationStatus.fixApplied,
        'fixVerified' => RemediationStatus.fixVerified,
        'fixFailed' => RemediationStatus.fixFailed,
        'regressed' => RemediationStatus.regressed,
        'verificationUnavailable' => RemediationStatus.verificationUnavailable,
        _ => RemediationStatus.notStarted,
      };
}
