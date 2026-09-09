import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/scan_summary.dart';
import '../services/scans_service.dart';

final scansServiceProvider = Provider((ref) => ScansService());

/// All scans, newest first. Backed by `GET /api/scans`.
final scansProvider = FutureProvider<List<ScanSummary>>((ref) async {
  final service = ref.read(scansServiceProvider);
  final scans = await service.listScans();
  scans.sort((a, b) => b.startedAt.compareTo(a.startedAt));
  return scans;
});

/// A single scan's status. Invalidate to poll while a scan is running.
final scanProvider =
    FutureProvider.family<ScanSummary, String>((ref, scanId) async {
  final service = ref.read(scansServiceProvider);
  return service.getScan(scanId);
});

/// Synchronous view for widgets that render a plain list (and for tests to
/// override). Empty while loading or on error — an honest empty state rather
/// than a spinner that implies data is definitely coming.
final scanListProvider = Provider<List<ScanSummary>>((ref) {
  return ref.watch(scansProvider).maybeWhen(
        data: (scans) => scans,
        orElse: () => const <ScanSummary>[],
      );
});
