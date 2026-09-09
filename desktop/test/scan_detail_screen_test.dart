import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:desktop/core/theme/app_theme.dart';
import 'package:desktop/features/scans/scan_detail_screen.dart';
import 'package:desktop/models/finding.dart';
import 'package:desktop/models/scan_detail.dart';
import 'package:desktop/providers/findings_provider.dart';
import 'package:desktop/providers/scan_detail_provider.dart';

const _scanId = 'scan_test_001';

Widget _wrap({ScanDetailState? state, List<Finding> findings = const []}) {
  return ProviderScope(
    overrides: [
      scanDetailProvider(_scanId).overrideWithValue(state),
      // Overridden so the widget never issues a real HTTP request in tests.
      scanFindingsProvider(_scanId).overrideWith((ref) async => findings),
    ],
    child: MaterialApp(
      theme: AppTheme.dark,
      home: const ScanDetailScreen(scanId: _scanId),
    ),
  );
}

Finding _finding({
  String id = 'f1',
  FindingStatus status = FindingStatus.confirmed,
  String title = 'BOLA at /documents/{doc_id}',
}) {
  return Finding(
    id: id,
    scanId: _scanId,
    title: title,
    category: 'BOLA',
    cwe: 'CWE-639',
    severity: FindingSeverity.high,
    confidence: ConfidenceLevel.high,
    routeTemplate: '/documents/{doc_id}',
    method: 'GET',
    description: 'desc',
    impact: 'impact',
    runtimeConfirmed: true,
    status: status,
    createdAt: DateTime(2026, 1, 1),
  );
}

ScanDetailState _state({int confirmed = 0}) {
  return ScanDetailState(
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
    summary: ScanRunSummary(
      endpointsDiscovered: 6,
      testsExecuted: 8,
      findingsDiscovered: confirmed,
      findingsConfirmed: confirmed,
    ),
  );
}

void main() {
  testWidgets('shows a loading state when the scan cannot yet be read',
      (tester) async {
    await tester.pumpWidget(_wrap(state: null));
    await tester.pumpAndSettle();

    expect(find.text('Loading scan…'), findsOneWidget);
    // No fabricated agent cards should render in this state.
    expect(find.text('Builder'), findsNothing);
  });

  testWidgets('renders all four agent cards with distinct statuses',
      (tester) async {
    await tester.pumpWidget(_wrap(state: _state()));
    await tester.pumpAndSettle();

    for (final label in ['Builder', 'Attacker', 'Evaluator', 'Fixer']) {
      expect(find.text(label), findsWidgets);
    }
    expect(find.text('Completed'), findsOneWidget);
    expect(find.text('Running'), findsOneWidget);
    expect(find.text('Waiting'), findsNWidgets(2));
    expect(find.text('Loading scan…'), findsNothing);
  });

  testWidgets('shows an empty state when the scan has no confirmed findings',
      (tester) async {
    await tester.pumpWidget(_wrap(state: _state()));
    await tester.pumpAndSettle();

    expect(find.text('No confirmed findings'), findsOneWidget);
  });

  testWidgets('lists confirmed findings inline once they exist',
      (tester) async {
    await tester.pumpWidget(
      _wrap(state: _state(confirmed: 1), findings: [_finding()]),
    );
    await tester.pumpAndSettle();

    expect(find.text('BOLA at /documents/{doc_id}'), findsOneWidget);
    expect(find.text('Confirmed findings (1)'), findsOneWidget);
    expect(find.text('No confirmed findings'), findsNothing);
  });

  testWidgets('excludes non-confirmed findings from the inline list',
      (tester) async {
    await tester.pumpWidget(
      _wrap(
        state: _state(),
        findings: [
          _finding(id: 'f2', status: FindingStatus.rejected, title: 'Rejected item'),
        ],
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Rejected item'), findsNothing);
    expect(find.text('No confirmed findings'), findsOneWidget);
  });
}
