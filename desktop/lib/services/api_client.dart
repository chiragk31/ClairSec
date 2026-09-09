import 'dart:io';
import 'package:dio/dio.dart';

class AuthTokenException implements Exception {
  final String message;
  const AuthTokenException(this.message);

  @override
  String toString() => message;
}

String getAuthTokenPath() {
  final sep = Platform.pathSeparator;
  final home = Platform.isWindows
      ? (Platform.environment['USERPROFILE'] ?? '')
      : (Platform.environment['HOME'] ?? '');
  return '$home$sep.clairsec${sep}auth_token';
}

String? readAuthToken() {
  try {
    final file = File(getAuthTokenPath());
    if (!file.existsSync()) {
      return null;
    }
    final content = file.readAsStringSync().trim();
    return content.isNotEmpty ? content : null;
  } catch (_) {
    return null;
  }
}

// Bind to 127.0.0.1 loopback per THREAT_MODEL C7.1
const String _baseUrl = 'http://127.0.0.1:8000';

final Dio apiClient = Dio(
  BaseOptions(
    baseUrl: _baseUrl,
    connectTimeout: const Duration(seconds: 5),
    receiveTimeout: const Duration(seconds: 15),
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
  ),
)..interceptors.add(
    InterceptorsWrapper(
      onRequest: (options, handler) {
        // /api/health is an unauthenticated liveness probe (THREAT_MODEL C7.2)
        if (options.path.endsWith('/api/health') || options.path == '/api/health') {
          return handler.next(options);
        }

        final token = readAuthToken();
        if (token == null || token.isEmpty) {
          return handler.reject(
            DioException(
              requestOptions: options,
              error: AuthTokenException(
                'Authentication token missing at ${getAuthTokenPath()}. '
                'Start the ClairSec backend to generate ~/.clairsec/auth_token.',
              ),
              type: DioExceptionType.cancel,
            ),
          );
        }

        options.headers['Authorization'] = 'Bearer $token';
        return handler.next(options);
      },
    ),
  );
