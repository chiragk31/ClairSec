import 'dart:async';
import 'dart:convert';
import 'package:web_socket_channel/web_socket_channel.dart';
import '../models/agent_event.dart';
import 'api_client.dart';

/// WebSocket + REST client with auto-reconnect and gap fill (FEATURES.md F5).
class EventStreamClient {
  EventStreamClient({
    this.wsBaseUrl = 'ws://127.0.0.1:8000',
  });

  final String wsBaseUrl;
  WebSocketChannel? _channel;
  StreamSubscription? _sub;
  Timer? _reconnectTimer;
  bool _disposed = false;
  int _lastSeq = 0;

  final _controller = StreamController<AgentEvent>.broadcast();
  Stream<AgentEvent> get stream => _controller.stream;
  int get lastSeq => _lastSeq;

  /// Starts listening to events for [scanId], filling gaps from [afterSeq].
  Future<void> connect(String scanId, {int afterSeq = 0}) async {
    _lastSeq = afterSeq;
    _disposed = false;

    // 1. Initial REST catch-up
    await _catchUpViaRest(scanId);

    // 2. Open WebSocket for live events
    _connectWebSocket(scanId);
  }

  Future<void> _catchUpViaRest(String scanId) async {
    if (_disposed) return;
    try {
      final response = await apiClient.get(
        '/api/scans/$scanId/events',
        queryParameters: {'after_seq': _lastSeq, 'limit': 500},
      );
      if (response.data is List) {
        final list = response.data as List;
        for (final item in list) {
          if (item is Map) {
            final event = AgentEvent.fromJson(item.cast<String, dynamic>());
            if (event.seq > _lastSeq) {
              _lastSeq = event.seq;
              _controller.add(event);
            }
          }
        }
      }
    } catch (_) {
      // Offline or network error handled by caller / reconnect loop
    }
  }

  void _connectWebSocket(String scanId) {
    if (_disposed) return;

    final token = readAuthToken() ?? '';
    final uri = Uri.parse(
      '$wsBaseUrl/api/scans/$scanId/events/ws?after_seq=$_lastSeq',
    );

    try {
      _channel = WebSocketChannel.connect(
        uri,
        protocols: token.isNotEmpty ? [token] : null,
      );
      _sub = _channel!.stream.listen(
        (data) {
          try {
            final decoded = jsonDecode(data as String) as Map<String, dynamic>;
            // Ignore heartbeat frames
            if (decoded['type'] == 'heartbeat') return;

            final event = AgentEvent.fromJson(decoded);
            if (event.seq > _lastSeq) {
              _lastSeq = event.seq;
              _controller.add(event);
            }
          } catch (_) {}
        },
        onError: (err) {
          _scheduleReconnect(scanId);
        },
        onDone: () {
          _scheduleReconnect(scanId);
        },
      );
    } catch (_) {
      _scheduleReconnect(scanId);
    }
  }

  void _scheduleReconnect(String scanId) {
    if (_disposed) return;
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 2), () async {
      if (_disposed) return;
      await _catchUpViaRest(scanId);
      _connectWebSocket(scanId);
    });
  }

  void dispose() {
    _disposed = true;
    _reconnectTimer?.cancel();
    _sub?.cancel();
    _channel?.sink.close();
    _controller.close();
  }
}
