import '../models/finding.dart';
import '../models/patch.dart';
import '../models/scan_summary.dart';
import 'api_client.dart';

/// Client for the scans API (ARCHITECTURE.md §4).
class ScansService {
  /// Queue a full pipeline scan. Returns the new scan id (202 Accepted).
  Future<String> createScan(String projectId) async {
    final response = await apiClient.post('/api/scans', data: {
      'project_id': projectId,
    });
    return (response.data['scan_id'] ?? response.data['scanId']) as String;
  }

  Future<List<ScanSummary>> listScans() async {
    final response = await apiClient.get('/api/scans');
    final List<dynamic> data = response.data as List<dynamic>;
    return data
        .map((json) => ScanSummary.fromJson(json as Map<String, dynamic>))
        .toList();
  }

  Future<ScanSummary> getScan(String scanId) async {
    final response = await apiClient.get('/api/scans/$scanId');
    return ScanSummary.fromJson(response.data as Map<String, dynamic>);
  }

  Future<List<Finding>> getFindings(String scanId) async {
    final response = await apiClient.get('/api/scans/$scanId/findings');
    final List<dynamic> data = response.data as List<dynamic>;
    return data
        .map((json) => Finding.fromJson(json as Map<String, dynamic>))
        .toList();
  }

  Future<List<Patch>> getPatches(String scanId) async {
    final response = await apiClient.get('/api/scans/$scanId/patches');
    final List<dynamic> data = response.data as List<dynamic>;
    return data
        .map((json) => Patch.fromJson(json as Map<String, dynamic>))
        .toList();
  }
}
