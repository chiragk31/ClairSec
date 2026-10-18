import '../models/finding.dart';
import '../models/patch.dart';
import '../models/scan_summary.dart';
import '../features/scans/widgets/attack_surface_map.dart';
import '../ui/components/provenance_strip.dart';
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

  /// Evidence chain of custody for one finding — `GET /api/findings/{id}/provenance`.
  Future<FindingProvenance> getProvenance(String findingId) async {
    final response = await apiClient.get('/api/findings/$findingId/provenance');
    return FindingProvenance.fromJson(response.data as Map<String, dynamic>);
  }

  /// Attack-surface tree for a scan — `GET /api/scans/{id}/surface`.
  Future<AttackSurface> getSurface(String scanId) async {
    final response = await apiClient.get('/api/scans/$scanId/surface');
    final data = response.data as Map<String, dynamic>;
    return AttackSurface(
      nodes: [
        for (final n in (data['nodes'] as List? ?? const []))
          SurfaceNode.fromJson((n as Map).cast<String, dynamic>()),
      ],
      edges: [
        for (final e in (data['edges'] as List? ?? const []))
          SurfaceEdge.fromJson((e as Map).cast<String, dynamic>()),
      ],
    );
  }

  /// Start an exploit replay (FEATURES.md F8). Returns the replay record.
  Future<Map<String, dynamic>> startReplay(String findingId, String target) async {
    final response = await apiClient.post(
      '/api/findings/$findingId/replay',
      data: {'target': target},
    );
    return (response.data as Map).cast<String, dynamic>();
  }

  Future<Map<String, dynamic>> getReplay(String replayId) async {
    final response = await apiClient.get('/api/replays/$replayId');
    return (response.data as Map).cast<String, dynamic>();
  }

  /// Recorded runs shipped in demo/bundles (FEATURES.md F4).
  Future<List<Map<String, dynamic>>> listBundles() async {
    final response = await apiClient.get('/api/bundles');
    return [for (final b in (response.data as List)) (b as Map).cast<String, dynamic>()];
  }

  /// Load a recorded run into the app; returns the recorded scan id.
  Future<String> replayBundle(String fileName) async {
    final response = await apiClient.post('/api/bundles/${Uri.encodeComponent(fileName)}/replay');
    return (response.data as Map)['scan_id'] as String;
  }

  /// Ask the backend to cancel a running scan.
  Future<void> cancelScan(String scanId) async {
    await apiClient.post('/api/scans/$scanId/cancel');
  }
}

class FindingProvenance {
  const FindingProvenance({required this.badge, required this.lane, required this.steps});

  final String badge;
  final String lane;
  final List<ProvenanceStep> steps;

  factory FindingProvenance.fromJson(Map<String, dynamic> json) => FindingProvenance(
        badge: (json['badge'] ?? '') as String,
        lane: (json['lane'] ?? 'candidates') as String,
        steps: [
          for (final s in (json['steps'] as List? ?? const []))
            ProvenanceStep.fromJson((s as Map).cast<String, dynamic>()),
        ],
      );
}

class AttackSurface {
  const AttackSurface({required this.nodes, required this.edges});

  final List<SurfaceNode> nodes;
  final List<SurfaceEdge> edges;
}
