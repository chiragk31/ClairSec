import 'package:flutter_test/flutter_test.dart';
import 'package:fake_async/fake_async.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:desktop/services/readiness_service.dart';
import 'package:desktop/providers/readiness_provider.dart';

class _FakeReadinessService extends ReadinessService {
  _FakeReadinessService(this._responses);

  final List<ReadinessReport> _responses;
  int callCount = 0;

  @override
  Future<ReadinessReport> check() async {
    final report = _responses[callCount < _responses.length ? callCount : _responses.length - 1];
    callCount++;
    return report;
  }
}

void main() {
  const redReport = ReadinessReport([
    ReadinessCheck(name: 'Docker', ok: false, detail: 'Not running'),
    ReadinessCheck(name: 'Backend', ok: true, detail: 'Connected'),
  ]);

  const greenReport = ReadinessReport([
    ReadinessCheck(name: 'Docker', ok: true, detail: 'Running'),
    ReadinessCheck(name: 'Backend', ok: true, detail: 'Connected'),
  ]);

  test('B4: auto re-checks every 10 s while red, stops when green', () {
    fakeAsync((async) {
      final fakeService = _FakeReadinessService([
        redReport,
        redReport,
        greenReport,
      ]);

      final container = ProviderContainer(
        overrides: [
          readinessServiceProvider.overrideWithValue(fakeService),
        ],
      );
      addTearDown(container.dispose);

      // Initial read
      final sub = container.listen(readinessProvider, (_, _) {});
      async.flushMicrotasks();

      expect(fakeService.callCount, 1);
      expect(sub.read().value?.ready, isFalse);

      // Advance 9 seconds — should NOT have rechecked yet
      async.elapse(const Duration(seconds: 9));
      expect(fakeService.callCount, 1);

      // Advance 1 more second (total 10 s) — should recheck
      async.elapse(const Duration(seconds: 1));
      async.flushMicrotasks();
      expect(fakeService.callCount, 2);
      expect(sub.read().value?.ready, isFalse);

      // Advance another 10 seconds (total 20 s) — should recheck and receive greenReport
      async.elapse(const Duration(seconds: 10));
      async.flushMicrotasks();
      expect(fakeService.callCount, 3);
      expect(sub.read().value?.ready, isTrue);

      // Advance another 30 seconds — should STOP because it is now green
      async.elapse(const Duration(seconds: 30));
      async.flushMicrotasks();
      expect(fakeService.callCount, 3, reason: 'Must stop auto-polling once green');
    });
  });

  test('B4: pauses auto re-check when app is not visible', () {
    fakeAsync((async) {
      final fakeService = _FakeReadinessService([
        redReport,
        redReport,
      ]);

      final container = ProviderContainer(
        overrides: [
          readinessServiceProvider.overrideWithValue(fakeService),
        ],
      );
      addTearDown(container.dispose);

      // Mark app as not visible
      container.read(isAppVisibleProvider.notifier).setVisible(false);

      container.listen(readinessProvider, (_, _) {});
      async.flushMicrotasks();

      expect(fakeService.callCount, 1);

      // Advance 30 seconds while not visible — should NOT recheck
      async.elapse(const Duration(seconds: 30));
      async.flushMicrotasks();
      expect(fakeService.callCount, 1, reason: 'Must not auto-recheck when app is not visible');

      // Now make app visible again
      container.read(isAppVisibleProvider.notifier).setVisible(true);
      async.elapse(const Duration(milliseconds: 50));
      async.flushMicrotasks();

      // Triggered recheck due to visibility change
      expect(fakeService.callCount, 2, reason: 'Must recheck when app becomes visible again');
    });
  });
}
