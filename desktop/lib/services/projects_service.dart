import '../models/project.dart';
import 'api_client.dart';

class ProjectsService {
  Future<List<ProjectRecord>> listProjects() async {
    final response = await apiClient.get('/api/projects');
    final List<dynamic> data = response.data;
    return data.map((json) => ProjectRecord.fromJson(json)).toList();
  }

  Future<ProjectRecord> importProject(String path, {String? name}) async {
    final response = await apiClient.post('/api/projects', data: {
      'path': path,
      if (name != null) 'name': name,
    });
    return ProjectRecord.fromJson(response.data);
  }
}
