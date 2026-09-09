import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/finding.dart';
import 'scans_provider.dart';

/// Findings for a single scan — `GET /api/scans/{id}/findings`.
final scanFindingsProvider =
    FutureProvider.family<List<Finding>, String>((ref, scanId) async {
  final service = ref.read(scansServiceProvider);
  return service.getFindings(scanId);
});

/// Findings across every scan, for the Vulnerabilities screen and dashboard.
///
/// Fans out over the scan list. Fine at demo scale; if scan counts grow this
/// should become a dedicated backend endpoint rather than N+1 requests.
final allFindingsProvider = FutureProvider<List<Finding>>((ref) async {
  final scans = await ref.watch(scansProvider.future);
  final service = ref.read(scansServiceProvider);

  final results = <Finding>[];
  for (final scan in scans) {
    try {
      results.addAll(await service.getFindings(scan.id));
    } catch (_) {
      // A single unreadable scan must not blank the whole list.
      continue;
    }
  }
  results.sort((a, b) => b.createdAt.compareTo(a.createdAt));
  return results;
});

/// Synchronous view used by widgets that render a plain list.
final findingsProvider = Provider<List<Finding>>((ref) {
  return ref.watch(allFindingsProvider).maybeWhen(
        data: (findings) => findings,
        orElse: () => const <Finding>[],
      );
});

final findingByIdProvider = Provider.family<Finding?, String>((ref, id) {
  for (final f in ref.watch(findingsProvider)) {
    if (f.id == id) return f;
  }
  return null;
});
