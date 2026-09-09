import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/isolation.dart';
import '../services/isolation_service.dart';

final isolationServiceProvider = Provider((ref) => IsolationService());

/// Current isolation status for a project.
///
/// The projects list endpoint does not include isolation state, so this is
/// fetched per project from `GET /api/projects/{id}/status`. Invalidate this
/// provider after any lifecycle action to refresh the card.
final isolationStatusProvider =
    FutureProvider.family<IsolationStatus, String>((ref, projectId) async {
  final service = ref.read(isolationServiceProvider);
  return service.getStatus(projectId);
});
