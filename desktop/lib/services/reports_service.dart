import 'dart:io';

import 'api_client.dart';

/// A generated report (FEATURES.md F12) as recorded by the backend.
class ReportRecord {
  const ReportRecord({
    required this.id,
    required this.scanId,
    required this.projectName,
    required this.createdAt,
    required this.files,
    required this.summary,
    required this.confirmedCount,
    this.postureBefore,
    this.postureAfter,
    this.gradeBefore,
    this.gradeAfter,
  });

  final String id;
  final String scanId;
  final String projectName;
  final DateTime createdAt;
  final Map<String, String> files;
  final List<String> summary;
  final int confirmedCount;
  final int? postureBefore;
  final int? postureAfter;
  final String? gradeBefore;
  final String? gradeAfter;

  factory ReportRecord.fromJson(Map<String, dynamic> json) {
    final posture = (json['posture'] as Map?)?.cast<String, dynamic>();
    return ReportRecord(
      id: json['id'] as String,
      scanId: json['scan_id'] as String,
      projectName: (json['project_name'] ?? 'Project') as String,
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? '') ?? DateTime.now(),
      files: ((json['files'] as Map?) ?? const {})
          .map((k, v) => MapEntry(k.toString(), v.toString())),
      summary: [for (final s in (json['summary'] as List? ?? const [])) s.toString()],
      confirmedCount: (json['confirmed_count'] as num?)?.toInt() ?? 0,
      postureBefore: (posture?['before'] as num?)?.toInt(),
      postureAfter: (posture?['after'] as num?)?.toInt(),
      gradeBefore: posture?['grade_before'] as String?,
      gradeAfter: posture?['grade_after'] as String?,
    );
  }
}

/// Result of comparing two scans of the same project (FEATURES.md F13).
class ScanDiff {
  const ScanDiff(this.buckets);

  /// new, still_open, came_back, fixed_since_last_scan -> list of findings (maps).
  final Map<String, List<Map<String, dynamic>>> buckets;

  factory ScanDiff.fromJson(Map<String, dynamic> json) => ScanDiff({
        for (final k in const ['new', 'still_open', 'came_back', 'fixed_since_last_scan'])
          k: [
            for (final f in (json[k] as List? ?? const []))
              (f as Map).cast<String, dynamic>(),
          ],
      });
}

class ReportsService {
  Future<ReportRecord> generate(String scanId, {String audience = 'both'}) async {
    final r = await apiClient.post('/api/scans/$scanId/reports', data: {'audience': audience});
    return ReportRecord.fromJson((r.data as Map).cast<String, dynamic>());
  }

  Future<List<ReportRecord>> listAll() async {
    final r = await apiClient.get('/api/reports');
    return [
      for (final j in (r.data as List)) ReportRecord.fromJson((j as Map).cast<String, dynamic>()),
    ];
  }

  Future<ScanDiff> diff(String projectId) async {
    final r = await apiClient.get('/api/projects/$projectId/scan-diff');
    return ScanDiff.fromJson((r.data as Map).cast<String, dynamic>());
  }

  /// Open a report file with the operating system's default app. The backend is
  /// local (127.0.0.1), so its report paths are on this machine.
  Future<void> openFile(String path) async {
    if (Platform.isWindows) {
      await Process.run('explorer', [path]);
    } else if (Platform.isMacOS) {
      await Process.run('open', [path]);
    } else {
      await Process.run('xdg-open', [path]);
    }
  }

  Future<void> openFolder(String path) => openFile(File(path).parent.path);
}
