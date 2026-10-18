import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../services/readiness_service.dart';

final readinessServiceProvider = Provider((ref) => ReadinessService());

class AppVisibilityNotifier extends Notifier<bool> {
  @override
  bool build() => true;

  void setVisible(bool visible) {
    state = visible;
  }
}

/// Tracks whether the desktop app window is currently visible/resumed.
final isAppVisibleProvider =
    NotifierProvider<AppVisibilityNotifier, bool>(() {
  return AppVisibilityNotifier();
});

/// Platform readiness. Auto re-checks every 10 s while any check is red;
/// stops when green and when the app is not visible (B4).
final readinessProvider = FutureProvider<ReadinessReport>((ref) async {
  final service = ref.watch(readinessServiceProvider);
  final isVisible = ref.watch(isAppVisibleProvider);
  final report = await service.check();

  // Auto re-check every 10 s while any check is red.
  // Stops when green (report.ready == true) or when the app is not visible.
  if (!report.ready && isVisible) {
    final timer = Timer(const Duration(seconds: 10), () {
      ref.invalidateSelf();
    });
    ref.onDispose(timer.cancel);
  }

  return report;
});
