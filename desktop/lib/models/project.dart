class ProjectRecord {
  final String id;
  final String name;
  final String sourcePath;
  final String validationStatus; // 'valid', 'invalid', 'unknown'
  final List<String> validationErrors;
  final String? entryPoint;
  final String? dependencyFile;
  final List<String> dependencies;
  final bool isolationReady;
  final String importSource;
  final String? commitSha;
  final List<String> importNotes;

  /// Credentials found committed in the code: type, file, line and a masked preview.
  final List<Map<String, dynamic>> exposedSecrets;
  final List<Map<String, dynamic>> monorepoCandidates;
  final int fileCount;
  final int repoSizeBytes;
  final DateTime createdAt;
  final DateTime updatedAt;

  ProjectRecord({
    required this.id,
    required this.name,
    required this.sourcePath,
    required this.validationStatus,
    required this.validationErrors,
    this.entryPoint,
    this.dependencyFile,
    required this.dependencies,
    required this.isolationReady,
    this.importSource = 'local',
    this.commitSha,
    this.importNotes = const [],
    this.exposedSecrets = const [],
    this.monorepoCandidates = const [],
    this.fileCount = 0,
    this.repoSizeBytes = 0,
    required this.createdAt,
    required this.updatedAt,
  });

  factory ProjectRecord.fromJson(Map<String, dynamic> json) {
    return ProjectRecord(
      id: json['id'] as String,
      name: json['name'] as String,
      sourcePath: json['source_path'] as String,
      validationStatus: json['validation_status'] as String,
      validationErrors: List<String>.from(json['validation_errors'] ?? []),
      entryPoint: json['entry_point'] as String?,
      dependencyFile: json['dependency_file'] as String?,
      dependencies: List<String>.from(json['dependencies'] ?? []),
      isolationReady: json['isolation_ready'] as bool? ?? false,
      importSource: json['import_source'] as String? ?? 'local',
      commitSha: json['commit_sha'] as String?,
      importNotes: List<String>.from(json['import_notes'] ?? []),
      exposedSecrets: (json['exposed_secrets'] as List<dynamic>? ?? [])
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList(),
      monorepoCandidates: (json['monorepo_candidates'] as List<dynamic>? ?? [])
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList(),
      fileCount: json['file_count'] as int? ?? 0,
      repoSizeBytes: json['repo_size_bytes'] as int? ?? 0,
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }
}
