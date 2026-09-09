/// A single file's unified diff within a patch.
class FileDiff {
  final String path;
  final String diff;

  const FileDiff({required this.path, required this.diff});

  factory FileDiff.fromJson(Map<String, dynamic> json) => FileDiff(
        path: json['path'] as String? ?? '',
        diff: json['diff'] as String? ?? '',
      );

  /// Parsed into renderable lines for the diff viewer.
  List<DiffLine> get lines =>
      diff.split('\n').map(DiffLine.parse).toList(growable: false);
}

enum DiffLineKind { addition, removal, context, hunk, meta }

class DiffLine {
  final DiffLineKind kind;
  final String text;

  const DiffLine(this.kind, this.text);

  static DiffLine parse(String raw) {
    if (raw.startsWith('+++') || raw.startsWith('---')) {
      return DiffLine(DiffLineKind.meta, raw);
    }
    if (raw.startsWith('@@')) return DiffLine(DiffLineKind.hunk, raw);
    if (raw.startsWith('+')) return DiffLine(DiffLineKind.addition, raw);
    if (raw.startsWith('-')) return DiffLine(DiffLineKind.removal, raw);
    return DiffLine(DiffLineKind.context, raw);
  }
}

class DiffStats {
  final int files;
  final int added;
  final int removed;

  const DiffStats({this.files = 0, this.added = 0, this.removed = 0});

  factory DiffStats.fromJson(Map<String, dynamic>? json) => DiffStats(
        files: json?['files'] as int? ?? 0,
        added: json?['added'] as int? ?? 0,
        removed: json?['removed'] as int? ?? 0,
      );
}

class PatchValidation {
  final bool astParsed;
  final bool pathCheckPassed;
  final bool sizeOk;

  const PatchValidation({
    this.astParsed = false,
    this.pathCheckPassed = false,
    this.sizeOk = false,
  });

  factory PatchValidation.fromJson(Map<String, dynamic>? json) => PatchValidation(
        astParsed: json?['astParsed'] as bool? ?? false,
        pathCheckPassed: json?['pathCheckPassed'] as bool? ?? false,
        sizeOk: json?['sizeOk'] as bool? ?? false,
      );

  bool get allPassed => astParsed && pathCheckPassed && sizeOk;
}

/// A generated fix — the Fixer's proposed patch for one finding
/// (DATA_MODEL.md §3 `patches`, DESIGN.md §8 Fix Review).
class Patch {
  final String id;
  final String findingId;
  final String scanId;
  final String findingTitle;
  final String rootCause;
  final String rationale;
  final bool applied;
  final String? applyError;
  final List<FileDiff> files;
  final DiffStats diffStats;
  final PatchValidation validation;

  const Patch({
    required this.id,
    required this.findingId,
    required this.scanId,
    required this.findingTitle,
    required this.rootCause,
    required this.rationale,
    required this.applied,
    required this.files,
    required this.diffStats,
    required this.validation,
    this.applyError,
  });

  factory Patch.fromJson(Map<String, dynamic> json) => Patch(
        id: json['id'] as String,
        findingId: (json['findingId'] ?? json['finding_id'] ?? '') as String,
        scanId: (json['scanId'] ?? json['scan_id'] ?? '') as String,
        findingTitle:
            (json['findingTitle'] ?? json['finding_title'] ?? '') as String,
        rootCause: (json['rootCause'] ?? json['root_cause'] ?? '') as String,
        rationale: json['rationale'] as String? ?? '',
        applied: json['applied'] as bool? ?? false,
        applyError: (json['applyError'] ?? json['apply_error']) as String?,
        files: ((json['files'] as List<dynamic>?) ?? const [])
            .map((e) => FileDiff.fromJson(e as Map<String, dynamic>))
            .toList(),
        diffStats:
            DiffStats.fromJson(json['diffStats'] as Map<String, dynamic>?),
        validation:
            PatchValidation.fromJson(json['validation'] as Map<String, dynamic>?),
      );
}
