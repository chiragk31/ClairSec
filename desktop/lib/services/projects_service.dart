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
      'name': ?name,
    });
    return ProjectRecord.fromJson(response.data);
  }

  Future<ProjectRecord> importDemoProject({String fixture = 'vulnerable'}) async {
    final response = await apiClient.post('/api/projects/demo', data: {
      'fixture': fixture,
    });
    return ProjectRecord.fromJson(response.data);
  }

  Future<Map<String, dynamic>> importGitProject({
    required String url,
    String? ref,
    String? subdir,
    String? name,
    required bool authorizationAffirmed,
  }) async {
    final response = await apiClient.post('/api/projects/import/git', data: {
      'url': url,
      'ref': ?ref,
      'subdir': ?subdir,
      'name': ?name,
      'authorization_affirmed': authorizationAffirmed,
    });
    return Map<String, dynamic>.from(response.data);
  }

  /// Status of a background job (e.g. a GitHub import) — `GET /api/jobs/{id}`.
  Future<Map<String, dynamic>> getJob(String jobId) async {
    final response = await apiClient.get('/api/jobs/$jobId');
    return (response.data as Map).cast<String, dynamic>();
  }

  /// One project record — `GET /api/projects/{id}`.
  Future<Map<String, dynamic>> getProjectJson(String projectId) async {
    final response = await apiClient.get('/api/projects/$projectId');
    return (response.data as Map).cast<String, dynamic>();
  }

  Future<Map<String, dynamic>> getProjectTree(String projectId, {int depth = 3}) async {
    final response = await apiClient.get('/api/projects/$projectId/tree?depth=$depth');
    return Map<String, dynamic>.from(response.data);
  }

  Future<Map<String, dynamic>> startPipeline({
    String? projectId,
    Map<String, dynamic>? gitImport,
    String? name,
  }) async {
    final response = await apiClient.post('/api/pipelines', data: {
      'project_id': ?projectId,
      'git_import': ?gitImport,
      'name': ?name,
    });
    return Map<String, dynamic>.from(response.data);
  }

  Future<Map<String, dynamic>> getPipeline(String pipelineId) async {
    final response = await apiClient.get('/api/pipelines/$pipelineId');
    return Map<String, dynamic>.from(response.data);
  }
}
