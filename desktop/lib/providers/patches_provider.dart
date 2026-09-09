import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/patch.dart';
import 'scans_provider.dart';

/// Patches generated during a scan — `GET /api/scans/{id}/patches`.
final scanPatchesProvider =
    FutureProvider.family<List<Patch>, String>((ref, scanId) async {
  final service = ref.read(scansServiceProvider);
  return service.getPatches(scanId);
});

/// All patches across every scan, keyed lookup for the Fix Review screen.
final allPatchesProvider = FutureProvider<List<Patch>>((ref) async {
  final scans = await ref.watch(scansProvider.future);
  final service = ref.read(scansServiceProvider);

  final results = <Patch>[];
  for (final scan in scans) {
    try {
      results.addAll(await service.getPatches(scan.id));
    } catch (_) {
      continue;
    }
  }
  return results;
});

/// The patch for a given finding, if one was generated.
final patchForFindingProvider =
    Provider.family<Patch?, String>((ref, findingId) {
  final patches = ref.watch(allPatchesProvider).maybeWhen(
        data: (p) => p,
        orElse: () => const <Patch>[],
      );
  for (final p in patches) {
    if (p.findingId == findingId) return p;
  }
  return null;
});
