import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/project.dart';
import '../services/projects_service.dart';
import '../services/health_service.dart';

final projectsServiceProvider = Provider((ref) => ProjectsService());
final healthServiceProvider = Provider((ref) => HealthService());

final projectsProvider = AsyncNotifierProvider<ProjectsNotifier, List<ProjectRecord>>(() {
  return ProjectsNotifier();
});

class ProjectsNotifier extends AsyncNotifier<List<ProjectRecord>> {
  @override
  Future<List<ProjectRecord>> build() async {
    return _fetchProjects();
  }

  Future<List<ProjectRecord>> _fetchProjects() async {
    final service = ref.read(projectsServiceProvider);
    return await service.listProjects();
  }

  Future<void> refresh() async {
    state = const AsyncValue.loading();
    state = await AsyncValue.guard(() => _fetchProjects());
  }

  Future<void> importProject(String path, {String? name}) async {
    final service = ref.read(projectsServiceProvider);
    // Don't set state to loading so we don't clear the UI while importing,
    // but a real app might want an explicit 'importing' state here.
    await service.importProject(path, name: name);
    // Refresh the list after import
    await refresh();
  }
}

// Polling health status (or simple future for now)
final healthProvider = FutureProvider<bool>((ref) async {
  final service = ref.read(healthServiceProvider);
  return await service.checkHealth();
});
