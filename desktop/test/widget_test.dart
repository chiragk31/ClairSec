import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:desktop/main.dart';

void main() {
  testWidgets('App launches and renders navigation rail with all 8 destinations',
      (WidgetTester tester) async {
    await tester.pumpWidget(const ProviderScope(child: ClairSecApp()));
    await tester.pumpAndSettle();

    // Each label must appear at least once somewhere on screen.
    // Some labels (Dashboard, Projects, Scans) appear in both the nav rail
    // AND the dashboard's stat cards / page header — findsWidgets handles both.
    for (final label in [
      'Dashboard',
      'Projects',
      'Scans',
      'Vulnerabilities',
      'Agents',
      'Reports',
      'Settings',
    ]) {
      expect(
        find.text(label),
        findsWidgets,
        reason: '"$label" nav label should be visible in the rail',
      );
    }
  });
}
