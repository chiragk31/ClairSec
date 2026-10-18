import 'api_client.dart';

/// Where the user is, so the assistant answers about the right records.
class AssistantContext {
  const AssistantContext({this.screen = 'dashboard', this.projectId, this.scanId, this.findingId});

  final String screen;
  final String? projectId;
  final String? scanId;
  final String? findingId;

  /// Derive the context from the current route path.
  factory AssistantContext.fromPath(String path) {
    final seg = Uri.parse(path).pathSegments;
    if (seg.length >= 2 && seg[0] == 'scans') return AssistantContext(screen: 'scan', scanId: seg[1]);
    if (seg.length >= 2 && seg[0] == 'vulnerabilities') {
      return AssistantContext(screen: 'finding', findingId: seg[1]);
    }
    if (seg.length >= 2 && seg[0] == 'fixes') return AssistantContext(screen: 'fix', findingId: seg[1]);
    if (seg.isNotEmpty && seg[0] == 'projects') return const AssistantContext(screen: 'projects');
    if (seg.isNotEmpty && seg[0] == 'reports') return const AssistantContext(screen: 'reports');
    return const AssistantContext();
  }

  Map<String, dynamic> toJson() => {
        'screen': screen,
        'project_id': ?projectId,
        'scan_id': ?scanId,
        'finding_id': ?findingId,
      };
}

class AssistantCitation {
  const AssistantCitation(this.type, this.id, this.label);
  final String type;
  final String id;
  final String label;
}

class AssistantAction {
  const AssistantAction(this.label, this.route);
  final String label;
  final String route;
}

class AssistantReply {
  const AssistantReply({
    required this.answer,
    required this.mode,
    required this.conversationId,
    this.citations = const [],
    this.actions = const [],
  });

  final String answer;
  final String mode; // offline | llm
  final String conversationId;
  final List<AssistantCitation> citations;
  final List<AssistantAction> actions;

  factory AssistantReply.fromJson(Map<String, dynamic> json) => AssistantReply(
        answer: (json['answer'] ?? '') as String,
        mode: (json['mode'] ?? 'offline') as String,
        conversationId: (json['conversation_id'] ?? '') as String,
        citations: [
          for (final c in (json['citations'] as List? ?? const []))
            AssistantCitation((c as Map)['type'].toString(), c['id'].toString(), c['label'].toString()),
        ],
        actions: [
          for (final a in (json['suggested_actions'] as List? ?? const []))
            AssistantAction((a as Map)['label'].toString(), a['route'].toString()),
        ],
      );
}

class AssistantService {
  Future<AssistantReply> ask(
    String message,
    AssistantContext context, {
    bool explainSimply = false,
    String? conversationId,
  }) async {
    final r = await apiClient.post('/api/assistant/ask', data: {
      'message': message,
      'context': context.toJson(),
      'explain_simply': explainSimply,
      'conversation_id': ?conversationId,
    });
    return AssistantReply.fromJson((r.data as Map).cast<String, dynamic>());
  }

  Future<List<String>> suggestions(String screen) async {
    final r = await apiClient.get('/api/assistant/suggestions', queryParameters: {'screen': screen});
    return [for (final q in ((r.data as Map)['questions'] as List? ?? const [])) q.toString()];
  }
}
