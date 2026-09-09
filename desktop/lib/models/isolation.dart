import 'package:flutter/material.dart';
import '../core/theme/app_theme.dart';

/// Mirrors the backend `IsolationStatus` enum (Phase 3).
enum IsolationState {
  pending,
  building,
  ready,
  running,
  stopped,
  importFailed,
  unknown;

  static IsolationState fromApi(String? raw) => switch (raw) {
        'pending' => IsolationState.pending,
        'building' => IsolationState.building,
        'ready' => IsolationState.ready,
        'running' => IsolationState.running,
        'stopped' => IsolationState.stopped,
        'import_failed' => IsolationState.importFailed,
        _ => IsolationState.unknown,
      };

  String get label => switch (this) {
        IsolationState.pending => 'Not isolated',
        IsolationState.building => 'Building',
        IsolationState.ready => 'Ready',
        IsolationState.running => 'Running',
        IsolationState.stopped => 'Stopped',
        IsolationState.importFailed => 'Import failed',
        IsolationState.unknown => 'Unknown',
      };

  IconData get icon => switch (this) {
        IsolationState.pending => Icons.radio_button_unchecked,
        IsolationState.building => Icons.hourglass_top,
        IsolationState.ready => Icons.check_circle_outline,
        IsolationState.running => Icons.play_circle_outline,
        IsolationState.stopped => Icons.stop_circle_outlined,
        IsolationState.importFailed => Icons.error_outline,
        IsolationState.unknown => Icons.help_outline,
      };

  Color get color => switch (this) {
        IsolationState.pending => AppColors.textDisabled,
        IsolationState.building => AppColors.accent,
        IsolationState.ready => SeverityColors.success,
        IsolationState.running => SeverityColors.success,
        IsolationState.stopped => AppColors.textSecondary,
        IsolationState.importFailed => SeverityColors.error,
        IsolationState.unknown => AppColors.textDisabled,
      };

  /// Isolation can be started from these states.
  bool get canIsolate =>
      this == IsolationState.pending ||
      this == IsolationState.stopped ||
      this == IsolationState.importFailed ||
      this == IsolationState.unknown;

  /// A container exists and can be torn down from these states.
  bool get canStop => this == IsolationState.ready || this == IsolationState.running;
}

/// Response of `GET /api/projects/{id}/status`.
class IsolationStatus {
  final String projectId;
  final String name;
  final IsolationState state;
  final String? workspacePath;
  final String? containerId;
  final String? containerName;
  final String? isolationError;

  const IsolationStatus({
    required this.projectId,
    required this.name,
    required this.state,
    this.workspacePath,
    this.containerId,
    this.containerName,
    this.isolationError,
  });

  factory IsolationStatus.fromJson(Map<String, dynamic> json) {
    return IsolationStatus(
      projectId: json['project_id'] as String,
      name: json['name'] as String? ?? '',
      state: IsolationState.fromApi(json['isolation_status'] as String?),
      workspacePath: json['workspace_path'] as String?,
      containerId: json['container_id'] as String?,
      containerName: json['container_name'] as String?,
      isolationError: json['isolation_error'] as String?,
    );
  }
}

/// Background job status — `GET /api/jobs/{job_id}` (Phase 3.5 async discipline).
class JobStatus {
  final String id;
  final String projectId;
  final String status; // pending | running | succeeded | failed | cancelled | interrupted
  final String stage;
  final bool cancelRequested;
  final String? error;

  const JobStatus({
    required this.id,
    required this.projectId,
    required this.status,
    required this.stage,
    required this.cancelRequested,
    this.error,
  });

  factory JobStatus.fromJson(Map<String, dynamic> json) {
    return JobStatus(
      id: json['id'] as String,
      projectId: json['project_id'] as String,
      status: json['status'] as String,
      stage: json['stage'] as String? ?? '',
      cancelRequested: json['cancel_requested'] as bool? ?? false,
      error: json['error'] as String?,
    );
  }

  /// Backend reports `completed` on success; the others are failure/stop
  /// states. Verified against a live isolation run.
  bool get isTerminal =>
      status == 'completed' ||
      status == 'succeeded' ||
      status == 'failed' ||
      status == 'cancelled' ||
      status == 'interrupted';

  bool get succeeded => status == 'completed' || status == 'succeeded';
}
