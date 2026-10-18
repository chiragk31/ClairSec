// End-to-end click-through of the real Windows app against the real local backend.
//
// Prerequisite: the backend is running on http://127.0.0.1:8000
// (cd backend && ..\venv\Scripts\python.exe -m uvicorn app.main:app --port 8000).
// Run: flutter test integration_test/click_through_test.dart -d windows
import 'package:desktop/core/shell/app_shell.dart';
import 'package:desktop/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Pump for a while without waiting for endless animations (spinners) to settle.
Future<void> settle(WidgetTester tester, [int ms = 1500]) async {
  for (var i = 0; i < ms ~/ 100; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

/// Wait until [finder] appears (real network calls take real time).
Future<void> waitFor(WidgetTester tester, Finder finder, {int seconds = 60}) async {
  for (var i = 0; i < seconds * 10; i++) {
    await tester.pump(const Duration(milliseconds: 100));
    if (finder.evaluate().isNotEmpty) return;
  }
  fail('Timed out waiting for $finder');
}

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  // Frames only when the test pumps, so no frame is left pending at teardown.
  binding.framePolicy = LiveTestWidgetsFlutterBindingFramePolicy.onlyPumps;

  testWidgets('real app: every screen, a recorded run, and the assistant', (tester) async {
    SharedPreferences.setMockInitialValues({'clairsec_wizard_dont_show': true});
    AppShell.wizardShownThisLaunch = true;
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(const ProviderScope(child: ClairSecApp()));
    await settle(tester, 3000);
    expect(tester.takeException(), isNull);

    // 1. Visit every screen in the navigation rail.
    for (final label in [
      'Projects', 'Scans', 'Vulnerabilities', 'Fix Review', 'Agents', 'Reports', 'Research',
      'Settings', 'Dashboard',
    ]) {
      final nav = find.text(label);
      expect(nav, findsWidgets, reason: 'nav item $label');
      await tester.tap(nav.first);
      await settle(tester);
      expect(tester.takeException(), isNull, reason: 'screen $label threw');
    }

    // 2. Watch a recorded run (a bundle captured from a real Demo scan).
    await tester.tap(find.text('Scans').first);
    await settle(tester);
    await tester.tap(find.text('Watch a recorded run'));
    await waitFor(tester, find.text('Watch'));
    await tester.tap(find.text('Watch').last);
    await waitFor(tester, find.text('RECORDED RUN'));
    await waitFor(tester, find.text('Security score'));
    expect(tester.takeException(), isNull);

    // 3. Ask the assistant a suggested question and get a grounded answer from the backend.
    await tester.tap(find.byTooltip('Ask ClairSec (Ctrl+J)'));
    await waitFor(tester, find.byType(ActionChip));
    await tester.tap(find.byType(ActionChip).first);
    await waitFor(tester, find.textContaining('Offline assistant'), seconds: 90);
    expect(tester.takeException(), isNull);

    // Unmount the app so its timers and streams are disposed before teardown.
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(milliseconds: 200));
  });
}
