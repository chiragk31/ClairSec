import '../models/isolation.dart';
import 'api_client.dart';

/// Client for the Phase 3/3.5 isolation lifecycle API.
class IsolationService {
  /// Trigger isolation. Returns the background job id (202 Accepted).
  Future<String> startIsolation(String projectId) async {
    final response = await apiClient.post('/api/projects/$projectId/isolate');
    return response.data['job_id'] as String;
  }

  Future<JobStatus> getJob(String jobId) async {
    final response = await apiClient.get('/api/jobs/$jobId');
    return JobStatus.fromJson(response.data);
  }

  Future<IsolationStatus> getStatus(String projectId) async {
    final response = await apiClient.get('/api/projects/$projectId/status');
    return IsolationStatus.fromJson(response.data);
  }

  Future<IsolationStatus> stop(String projectId) async {
    final response = await apiClient.post('/api/projects/$projectId/stop');
    return IsolationStatus.fromJson(response.data);
  }

  Future<IsolationStatus> cleanup(String projectId) async {
    final response = await apiClient.post('/api/projects/$projectId/cleanup');
    return IsolationStatus.fromJson(response.data);
  }

  Future<String> getLogs(String projectId) async {
    final response = await apiClient.get('/api/projects/$projectId/logs');
    return response.data['logs'] as String? ?? '';
  }
}
