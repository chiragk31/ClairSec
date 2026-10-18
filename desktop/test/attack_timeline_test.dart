import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:desktop/core/theme/tokens.dart';
import 'package:desktop/features/scans/widgets/attack_timeline.dart';
import 'package:desktop/features/scans/widgets/live_scan_stats_panel.dart';
import 'package:desktop/models/agent_event.dart';
import 'package:desktop/providers/event_stream_provider.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final scriptedEvents = [
    AgentEvent(
      id: 'e1',
      scanId: 'scan-1',
      seq: 1,
      timestamp: DateTime(2026, 1, 1, 10, 0, 0),
      agent: 'builder',
      kind: 'stage_started',
      title: 'Builder Agent',
      plain: 'Beginning stage: Builder Agent.',
    ),
    AgentEvent(
      id: 'e2',
      scanId: 'scan-1',
      seq: 2,
      timestamp: DateTime(2026, 1, 1, 10, 0, 5),
      agent: 'builder',
      kind: 'endpoint_discovered',
      title: 'GET /api/users/{id}',
      plain: 'Discovered API endpoint: GET /api/users/{id}.',
    ),
    AgentEvent(
      id: 'e3',
      scanId: 'scan-1',
      seq: 3,
      timestamp: DateTime(2026, 1, 1, 10, 0, 10),
      agent: 'attacker',
      kind: 'request_sent',
      title: 'GET /api/users/999',
      plain: 'Sent test request: GET /api/users/999.',
      refs: {'finding_id': 'f-bola-1'},
    ),
    AgentEvent(
      id: 'e4',
      scanId: 'scan-1',
      seq: 4,
      timestamp: DateTime(2026, 1, 1, 10, 0, 15),
      agent: 'evaluator',
      kind: 'finding_confirmed',
      title: 'BOLA on User Profile',
      plain: 'Vulnerability confirmed by deterministic oracle: BOLA on User Profile.',
      severity: 'high',
      refs: {'finding_id': 'f-bola-1'},
    ),
    AgentEvent(
      id: 'e5',
      scanId: 'scan-1',
      seq: 5,
      timestamp: DateTime(2026, 1, 1, 10, 0, 20),
      agent: 'fixer',
      kind: 'patch_proposed',
      title: 'Patch for BOLA',
      plain: 'Fixer proposed code patch: Patch for BOLA.',
    ),
    AgentEvent(
      id: 'e6',
      scanId: 'scan-1',
      seq: 6,
      timestamp: DateTime(2026, 1, 1, 10, 0, 25),
      agent: 'verifier',
      kind: 'verification_result',
      title: 'Outcome: fixed',
      plain: 'Remediation verification completed: Outcome: fixed.',
      detail: 'Re-test clear, all functional tests pass',
    ),
  ];

  Widget buildTimelineWidget({
    required List<AgentEvent> events,
    void Function(String)? onSelectFinding,
  }) {
    return ProviderScope(
      child: MaterialApp(
        theme: ThemeData(
          extensions: const [ClairTokens.darkMidnight],
        ),
        home: Scaffold(
          body: AttackTimeline(
            events: events,
            onSelectFinding: onSelectFinding,
          ),
        ),
      ),
    );
  }

  testWidgets('V2 exit gate: widget test renders a scripted event list', (tester) async {
    String? selectedFinding;

    await tester.pumpWidget(buildTimelineWidget(
      events: scriptedEvents,
      onSelectFinding: (fid) => selectedFinding = fid,
    ));
    await tester.pumpAndSettle();

    // Verify Attack Timeline title
    expect(find.text('Attack Timeline'), findsOneWidget);

    // Verify scripted events are rendered
    expect(find.text('Builder Agent'), findsOneWidget);
    expect(find.text('GET /api/users/{id}'), findsOneWidget);
    expect(find.text('GET /api/users/999'), findsOneWidget);
    expect(find.text('BOLA on User Profile'), findsOneWidget);
    expect(find.text('Patch for BOLA'), findsOneWidget);
    expect(find.text('Outcome: fixed'), findsOneWidget);

    // Verify plain language descriptions appear
    expect(find.text('Beginning stage: Builder Agent.'), findsOneWidget);
    expect(find.text('Vulnerability confirmed by deterministic oracle: BOLA on User Profile.'), findsOneWidget);

    // Test clicking finding event triggers onSelectFinding
    await tester.tap(find.text('BOLA on User Profile'));
    await tester.pumpAndSettle();
    expect(selectedFinding, 'f-bola-1');

    // Test filtering by agent
    await tester.tap(find.text('Attacker'));
    await tester.pumpAndSettle();

    // Only Attacker event should be visible
    expect(find.text('GET /api/users/999'), findsOneWidget);
    expect(find.text('GET /api/users/{id}'), findsNothing);
  });

  testWidgets('LiveScanStatsPanel renders live counters and budget correctly', (tester) async {
    const counters = LiveCounters(
      endpoints: 5,
      testsExecuted: 12,
      oracleHits: 2,
      confirmed: 1,
      patches: 1,
      fixesVerified: 1,
    );

    const budget = {
      'elapsed_s': 18.5,
      'tokens_in': 1200,
      'tokens_out': 450,
    };

    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData(
          extensions: const [ClairTokens.darkMidnight],
        ),
        home: const Scaffold(
          body: LiveScanStatsPanel(
            counters: counters,
            budget: budget,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Live Scan Telemetry'), findsOneWidget);
    expect(find.text('Endpoints: '), findsOneWidget);
    expect(find.text('5'), findsOneWidget);
    expect(find.text('12'), findsOneWidget);
    expect(find.text('Elapsed: 18.5s'), findsOneWidget);
    expect(find.text('Tokens In: 1200'), findsOneWidget);
  });
}
