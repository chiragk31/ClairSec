/// Security posture score computed by platform code (FEATURES.md F6, `posture_v1`).
/// The app only displays it — it never recomputes it.
class PostureMove {
  const PostureMove({
    required this.title,
    required this.severity,
    required this.penalty,
    required this.isFixed,
    this.findingId,
    this.verificationOutcome = 'unverified',
  });

  final String? findingId;
  final String title;
  final String severity;
  final int penalty;
  final bool isFixed;
  final String verificationOutcome;

  factory PostureMove.fromJson(Map<String, dynamic> json) => PostureMove(
        findingId: json['finding_id'] as String?,
        title: (json['title'] ?? 'Finding') as String,
        severity: (json['severity'] ?? 'unscored') as String,
        penalty: (json['penalty'] as num?)?.toInt() ?? 0,
        isFixed: json['is_fixed'] == true,
        verificationOutcome: (json['verification_outcome'] ?? 'unverified') as String,
      );
}

class Posture {
  const Posture({
    required this.before,
    required this.after,
    required this.gradeBefore,
    required this.gradeAfter,
    required this.coverage,
    required this.limitedCoverage,
    required this.basis,
    this.version = 'posture_v1',
    this.countsBySeverity = const {},
    this.moves = const [],
  });

  final String version;
  final int before;
  final int after;
  final String gradeBefore;
  final String gradeAfter;
  final double coverage;
  final bool limitedCoverage;
  final String basis;
  final Map<String, int> countsBySeverity;
  final List<PostureMove> moves;

  bool get improved => after > before;

  static Posture? tryParse(Object? raw) {
    if (raw is! Map) return null;
    final json = raw.cast<String, dynamic>();
    if (json['before'] == null || json['after'] == null) return null;
    final inputs = (json['inputs'] as Map?)?.cast<String, dynamic>() ?? const {};
    final counts = (inputs['confirmed_counts'] as Map?)?.map(
          (k, v) => MapEntry(k.toString(), (v as num).toInt()),
        ) ??
        const <String, int>{};
    return Posture(
      version: (json['version'] ?? 'posture_v1') as String,
      before: (json['before'] as num).toInt(),
      after: (json['after'] as num).toInt(),
      gradeBefore: (json['grade_before'] ?? '?') as String,
      gradeAfter: (json['grade_after'] ?? '?') as String,
      coverage: (json['coverage'] as num?)?.toDouble() ?? 0,
      limitedCoverage: json['limited_coverage'] == true,
      basis: (json['basis'] ?? '') as String,
      countsBySeverity: counts,
      moves: [
        for (final m in (json['what_moved'] as List? ?? const []))
          if (m is Map) PostureMove.fromJson(m.cast<String, dynamic>()),
      ],
    );
  }
}
