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
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }
}
