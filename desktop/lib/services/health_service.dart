import 'api_client.dart';

class HealthService {
  Future<bool> checkHealth() async {
    try {
      final response = await apiClient.get('/api/health');
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }
}
