import 'api_client.dart';

enum BackendStatus {
  connected,
  tokenMissing,
  disconnected,
}

class HealthService {
  Future<BackendStatus> checkBackendStatus() async {
    try {
      final response = await apiClient.get('/api/health');
      if (response.statusCode != 200) {
        return BackendStatus.disconnected;
      }
      final token = readAuthToken();
      if (token == null || token.isEmpty) {
        return BackendStatus.tokenMissing;
      }
      return BackendStatus.connected;
    } catch (_) {
      return BackendStatus.disconnected;
    }
  }

  Future<bool> checkHealth() async {
    try {
      final response = await apiClient.get('/api/health');
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }
}
