import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:desktop/core/theme/app_theme.dart';
import 'package:desktop/features/scans/scan_detail_screen.dart';
import 'package:desktop/models/scan_detail.dart';
import 'package:desktop/providers/scan_detail_provider.dart';

const _scanId = 'scan_test_001';

Widget _wrap(Widget child, {ScanDetailState? override}) {
  return ProviderScope(
    overrides: [
      scanDetailProvider(_scanId).overrideWithValue(override),
    ],
    child: MaterialApp(theme: AppTheme.dark, home: child),
  );
}

void main() {
  testWidgets('shows an honest not-connected state when no live scan data exists',
      (tester) async {
    await tester.pumpWidget(
      _wrap(const ScanDetailScreen(scanId: _scanId), override: null),
    );
    await tester.pumpAndSettle();

    expect(find.text('No live connection to this scan'), findsOneWidget);
    // No fabricated agent cards or progress should render in this state.
    expect(find.text('Builder'), findsNothing);
  });

  testWidgets('renders all four agent cards with distinct statuses', (tester) async {
    final state = ScanDetailState(
      scanId: _scanId,
      agentCards: {
        AgentRole.builder: const AgentCardState(
          role: AgentRole.builder,
          status: AgentStatus.completed,
          currentTask: 'Route inventory complete',
          eventCount: 12,
          elapsed: Duration(seconds: 34),
        ),
        AgentRole.attacker: const AgentCardState(
          role: AgentRole.attacker,
          status: AgentStatus.running,
          currentTask: 'Testing /documents/{doc_id} for BOLA',
          progress: 0.4,
          eventCount: 8,
          elapsed: Duration(seconds: 12),
        ),
        AgentRole.evaluator: AgentCardState.idleFor(AgentRole.evaluator),
        AgentRole.fixer: AgentCardState.idleFor(AgentRole.fixer),
      },
      events: [
        ScanEventEntry(
          seq: 1,
          timestamp: DateTime(2026, 1, 1, 12, 0, 0),
          agent: AgentRole.attacker,
          message: 'Testing endpoint /documents/{doc_id}',
        ),
      ],
      summary: const ScanRunSummary(
        endpointsDiscovered: 6,
        testsExecuted: 8,
        findingsDiscovered: 1,
      ),
    );

    await tester.pumpWidget(
      _wrap(const ScanDetailScreen(scanId: _scanId), override: state),
    );
    await tester.pumpAndSettle();

    for (final label in ['Builder', 'Attacker', 'Evaluator', 'Fixer']) {
      // findsWidgets, not findsOneWidget: a role label legitimately appears
      // twice for Attacker here (its card title, and its event-row label).
      expect(find.text(label), findsWidgets);
    }
    expect(find.text('Completed'), findsOneWidget);
    expect(find.text('Running'), findsOneWidget);
    expect(find.text('Waiting'), findsNWidgets(2));
    expect(find.text('Testing endpoint /documents/{doc_id}'), findsOneWidget);
    expect(find.text('No live connection to this scan'), findsNothing);
  });

  testWidgets('event stream shows an empty message when no events have arrived yet',
      (tester) async {
    final state = ScanDetailState(
      scanId: _scanId,
      agentCards: {
        for (final role in AgentRole.values) role: AgentCardState.idleFor(role),
      },
    );

    await tester.pumpWidget(
      _wrap(const ScanDetailScreen(scanId: _scanId), override: state),
    );
    await tester.pumpAndSettle();

    expect(find.text('No events yet'), findsOneWidget);
  });
}
