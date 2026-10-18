import 'api_client.dart';

/// One dependency the platform needs before a scan can run (UI_SYSTEM.md §6, FEATURES.md F0, F4).
class ReadinessCheck {
  const ReadinessCheck({
    required this.name,
    required this.ok,
    required this.detail,
    this.fix,
  });

  final String name;
  final bool ok;
  final String detail;

  /// What the user should do when [ok] is false.
  final String? fix;
}

class ExperienceModeInfo {
  const ExperienceModeInfo({
    required this.id,
    required this.label,
    required this.reason,
  });

  final String id;
  final String label;
  final String reason;

  factory ExperienceModeInfo.fromJson(Map<String, dynamic> json) {
    return ExperienceModeInfo(
      id: json['id'] as String? ?? 'live_offline_ai',
      label: json['label'] as String? ?? 'LIVE · OFFLINE AI',
      reason: json['reason'] as String? ?? '',
    );
  }
}

class ReadinessReport {
  const ReadinessReport(this.checks, {this.mode, this.storage = 'mongodb'});

  final List<ReadinessCheck> checks;
  final ExperienceModeInfo? mode;

  /// 'mongodb' or 'memory' (in-memory fallback — nothing survives a restart).
  final String storage;

  bool get temporaryStorage => storage == 'memory';

  bool get ready => checks.every((c) => c.ok);
}

/// Client for `GET /api/system/preflight` (EXTENDED IN V0).
class ReadinessService {
  Future<ReadinessReport> check() async {
    final Map<String, dynamic> data;
    try {
      final response = await apiClient.get('/api/system/preflight');
      data = response.data as Map<String, dynamic>;
    } catch (_) {
      return const ReadinessReport([
        ReadinessCheck(
          name: 'Backend',
          ok: false,
          detail: 'The ClairSec backend is not reachable.',
          fix: 'Start the backend (uvicorn app.main:app) and refresh.',
        ),
      ]);
    }

    final mongo = (data['mongodb'] as Map?)?.cast<String, dynamic>() ?? {};
    final docker = (data['docker'] as Map?)?.cast<String, dynamic>() ?? {};
    final llm = (data['llm'] as Map?)?.cast<String, dynamic>() ?? {};
    final ollama = (data['ollama'] as Map?)?.cast<String, dynamic>() ?? {};
    final git = (data['git'] as Map?)?.cast<String, dynamic>() ?? {};
    final disk = (data['disk'] as Map?)?.cast<String, dynamic>() ?? {};
    final modeJson = (data['mode'] as Map?)?.cast<String, dynamic>();

    final dockerOk = docker['ready'] == true;
    final dockerVersion = docker['server_version'];

    final llmProvider = llm['provider'] as String? ?? 'mock';
    final keyConfigured = llm['key_configured'] == true;
    final ollamaModelReady = ollama['model_ready'] == true;
    final llmOk = keyConfigured ||
        llmProvider == 'mock' ||
        (llmProvider == 'ollama' && ollamaModelReady);
    final memoryFallback = mongo['fallback'] == 'memory';

    final ollamaReachable = ollama['reachable'] == true;
    final ollamaUrl = ollama['url'] as String? ?? 'http://127.0.0.1:11434';

    final gitAvailable = git['available'] == true;
    final gitVersion = git['version'] as String?;

    final freeGb = (disk['free_gb'] as num?)?.toDouble() ?? 0.0;
    final diskOk = freeGb >= 1.0;

    final checks = <ReadinessCheck>[
      const ReadinessCheck(name: 'Backend', ok: true, detail: 'Connected'),
      ReadinessCheck(
        name: 'MongoDB',
        ok: mongo['ok'] == true,
        detail: mongo['ok'] == true
            ? 'Connected'
            : memoryFallback
                ? 'Not reachable — using temporary in-memory storage (results vanish on restart)'
                : (mongo['error'] as String? ?? 'Not reachable'),
        fix: 'Start the MongoDB service (net start MongoDB), then restart the backend to keep results.',
      ),
      ReadinessCheck(
        name: 'Docker',
        ok: dockerOk,
        detail: dockerOk
            ? 'Engine running${dockerVersion != null ? ' (v$dockerVersion)' : ''}'
            : (docker['hint'] as String? ?? 'Not reachable'),
        fix: 'Open Docker Desktop and wait until it says "Engine running".',
      ),
      ReadinessCheck(
        name: 'LLM API',
        ok: llmOk,
        detail: keyConfigured
            ? 'Configured ($llmProvider)'
            : (llmProvider == 'mock' ? 'Mock provider active' : 'API key not configured ($llmProvider)'),
        fix: 'Set LLM_API_KEY environment variable or switch to Ollama.',
      ),
      ReadinessCheck(
        name: 'Ollama',
        ok: ollamaReachable,
        detail: ollamaReachable ? 'Running at $ollamaUrl' : 'Not reachable at $ollamaUrl',
        fix: 'Start Ollama service (ollama serve) for local AI generation.',
      ),
      ReadinessCheck(
        name: 'Git',
        ok: gitAvailable,
        detail: gitAvailable ? 'Available${gitVersion != null ? ' ($gitVersion)' : ''}' : 'git not found',
        fix: 'Install Git and add to system PATH.',
      ),
      ReadinessCheck(
        name: 'Disk Space',
        ok: diskOk,
        detail: '${freeGb.toStringAsFixed(1)} GB free in workspace',
        fix: 'Ensure at least 1.0 GB free disk space in workspace root.',
      ),
    ];

    return ReadinessReport(
      checks,
      mode: modeJson != null ? ExperienceModeInfo.fromJson(modeJson) : null,
      storage: data['storage'] as String? ?? 'mongodb',
    );
  }
}
