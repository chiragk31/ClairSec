import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:desktop/core/theme/app_theme.dart';
import 'package:desktop/models/finding.dart';
import 'package:desktop/ui/components/cs_badge.dart';
import 'package:desktop/ui/components/score_gauge.dart';
import 'package:desktop/features/vulnerabilities/widgets/status_badges.dart';
import 'package:desktop/features/scans/widgets/attack_surface_map.dart';

Widget _wrap(Widget child) {
  return MaterialApp(
    theme: AppTheme.dark,
    home: Scaffold(
      body: Center(child: child),
    ),
  );
}

void main() {
  group('V4 Experience Modes - ModeBadge Widget Tests', () {
    testWidgets('renders LIVE mode badge with correct tooltip and label', (tester) async {
      await tester.pumpWidget(_wrap(const ModeBadge(modeId: 'live')));
      await tester.pumpAndSettle();

      expect(find.text('LIVE'), findsOneWidget);
      final tooltip = tester.widget<Tooltip>(find.byType(Tooltip));
      expect(tooltip.message, contains('Docker isolation is ready and cloud LLM provider is configured.'));
    });

    testWidgets('renders LIVE · LOCAL AI mode badge with correct tooltip', (tester) async {
      await tester.pumpWidget(_wrap(const ModeBadge(modeId: 'live_local_ai')));
      await tester.pumpAndSettle();

      expect(find.text('LIVE · LOCAL AI'), findsOneWidget);
      final tooltip = tester.widget<Tooltip>(find.byType(Tooltip));
      expect(tooltip.message, contains('local Ollama model is available'));
    });

    testWidgets('renders LIVE · OFFLINE AI mode badge with correct tooltip', (tester) async {
      await tester.pumpWidget(_wrap(const ModeBadge(modeId: 'live_offline_ai')));
      await tester.pumpAndSettle();

      expect(find.text('LIVE · OFFLINE AI'), findsOneWidget);
      final tooltip = tester.widget<Tooltip>(find.byType(Tooltip));
      expect(tooltip.message, contains('offline mock/replay intelligence'));
    });

    testWidgets('renders DEMO APP mode badge with correct tooltip', (tester) async {
      await tester.pumpWidget(_wrap(const ModeBadge(modeId: 'demo')));
      await tester.pumpAndSettle();

      expect(find.text('DEMO APP'), findsOneWidget);
      final tooltip = tester.widget<Tooltip>(find.byType(Tooltip));
      expect(tooltip.message, contains('trusted fixture isolation'));
    });

    testWidgets('renders RECORDED RUN mode badge with custom date label', (tester) async {
      await tester.pumpWidget(_wrap(const ModeBadge(
        modeId: 'recorded',
        label: 'RECORDED RUN · 2026-10-18',
      )));
      await tester.pumpAndSettle();

      expect(find.text('RECORDED RUN · 2026-10-18'), findsOneWidget);
      final tooltip = tester.widget<Tooltip>(find.byType(Tooltip));
      expect(tooltip.message, contains('recorded scan bundle'));
    });
  });

  group('V5 Trust & Score - Confirmed Badge Guard (F7)', () {
    testWidgets('finding without oracle record cannot render confirmed badge', (tester) async {
      // Finding with runtimeConfirmed = true BUT hasOracleEvidence = false
      final unverifiedFinding = Finding(
        id: 'f-suspicion-1',
        scanId: 'scan-1',
        title: 'Possible SQL injection in user query',
        category: 'SQLI',
        cwe: 'CWE-89',
        severity: FindingSeverity.critical,
        confidence: ConfidenceLevel.high,
        routeTemplate: '/users',
        method: 'GET',
        description: 'Static analysis flagged string concatenation.',
        impact: 'Data leakage.',
        runtimeConfirmed: true,
        status: FindingStatus.confirmed,
        hasOracleEvidence: false, // NO ORACLE RECORD
        createdAt: DateTime(2026, 1, 1),
      );

      await tester.pumpWidget(_wrap(RuntimeConfirmationBadge.forFinding(unverifiedFinding)));
      await tester.pumpAndSettle();

      // MUST NOT render the confirmed badge
      expect(find.text('Runtime-confirmed · oracle-verified'), findsNothing);
      // MUST render source suspicion
      expect(find.text('Source suspicion — not confirmed'), findsOneWidget);
    });

    testWidgets('candidate status cannot render confirmed badge even if runtimeConfirmed is true', (tester) async {
      final candidateFinding = Finding(
        id: 'f-candidate-1',
        scanId: 'scan-1',
        title: 'Unauthenticated debug route candidate',
        category: 'DEBUG',
        cwe: 'CWE-200',
        severity: FindingSeverity.medium,
        confidence: ConfidenceLevel.low,
        routeTemplate: '/debug',
        method: 'GET',
        description: 'Endpoint exists.',
        impact: 'Information disclosure.',
        runtimeConfirmed: true,
        status: FindingStatus.candidate, // NOT CONFIRMED
        hasOracleEvidence: true,
        createdAt: DateTime(2026, 1, 1),
      );

      await tester.pumpWidget(_wrap(RuntimeConfirmationBadge.forFinding(candidateFinding)));
      await tester.pumpAndSettle();

      expect(find.text('Runtime-confirmed · oracle-verified'), findsNothing);
      expect(find.text('Source suspicion — not confirmed'), findsOneWidget);
    });

    testWidgets('finding with oracle evidence and confirmed status renders confirmed badge', (tester) async {
      final confirmedFinding = Finding(
        id: 'f-confirmed-1',
        scanId: 'scan-1',
        title: 'BOLA on document access',
        category: 'BOLA',
        cwe: 'CWE-639',
        severity: FindingSeverity.critical,
        confidence: ConfidenceLevel.high,
        routeTemplate: '/documents/{id}',
        method: 'GET',
        description: 'Unauthorized access verified by oracle.',
        impact: 'Confidentiality breach.',
        runtimeConfirmed: true,
        status: FindingStatus.confirmed,
        hasOracleEvidence: true, // ORACLE VERIFIED
        createdAt: DateTime(2026, 1, 1),
      );

      await tester.pumpWidget(_wrap(RuntimeConfirmationBadge.forFinding(confirmedFinding)));
      await tester.pumpAndSettle();

      expect(find.text('Runtime-confirmed · oracle-verified'), findsOneWidget);
      expect(find.text('Source suspicion — not confirmed'), findsNothing);
    });
  });

  group('V5 Attack Surface Map - Accessibility List Alternative (F10)', () {
    final sampleNodes = [
      const SurfaceNode(
        id: 'node-root',
        path: '/',
        methods: ['GET'],
        auth: 'public',
        worstSeverity: null,
        testsRun: 2,
      ),
      const SurfaceNode(
        id: 'node-users',
        path: '/users',
        methods: ['GET', 'POST'],
        auth: 'login',
        worstSeverity: 'medium',
        testsRun: 12,
      ),
      const SurfaceNode(
        id: 'node-users-id',
        path: '/users/{id}',
        methods: ['GET', 'PUT', 'DELETE'],
        auth: 'login',
        worstSeverity: 'critical',
        testsRun: 35,
      ),
      const SurfaceNode(
        id: 'node-admin-stats',
        path: '/admin/stats',
        methods: ['GET'],
        auth: 'admin',
        worstSeverity: 'high',
        testsRun: 8,
      ),
    ];

    final sampleEdges = [
      const SurfaceEdge(from: 'node-root', to: 'node-users'),
      const SurfaceEdge(from: 'node-users', to: 'node-users-id'),
      const SurfaceEdge(from: 'node-root', to: 'node-admin-stats'),
    ];

    testWidgets('golden-free test: every node is reachable and displayed in list alternative', (tester) async {
      SurfaceNode? selectedNode;

      await tester.pumpWidget(_wrap(
        SizedBox(
          width: 800,
          height: 600,
          child: AttackSurfaceMap(
            nodes: sampleNodes,
            edges: sampleEdges,
            onNodeSelected: (n) => selectedNode = n,
          ),
        ),
      ));
      await tester.pumpAndSettle();

      // Switch to List (Accessible) view via toggle button
      final listButton = find.byKey(const Key('toggle_list_view'));
      expect(listButton, findsOneWidget);
      await tester.tap(listButton);
      await tester.pumpAndSettle();

      // Verify ListView exists
      expect(find.byKey(const Key('attack_surface_list_view')), findsOneWidget);

      // Verify every node in sampleNodes is present in the list view
      for (final node in sampleNodes) {
        final nodeFinder = find.byKey(Key('node_item_${node.id}'));
        expect(nodeFinder, findsOneWidget);
        expect(find.text(node.path), findsOneWidget);
      }

      // Tap on a specific node and verify callback fires
      await tester.tap(find.byKey(const Key('node_item_node-users-id')));
      await tester.pumpAndSettle();

      expect(selectedNode, isNotNull);
      expect(selectedNode!.id, equals('node-users-id'));
      expect(selectedNode!.worstSeverity, equals('critical'));
    });
  });

  group('V5 Posture Gauge & Grade Tests', () {
    test('ScoreGauge grade thresholds conform to F6 formula', () {
      expect(ScoreGauge.scoreToGrade(100), equals('A'));
      expect(ScoreGauge.scoreToGrade(90), equals('A'));
      expect(ScoreGauge.scoreToGrade(89.9), equals('B'));
      expect(ScoreGauge.scoreToGrade(80), equals('B'));
      expect(ScoreGauge.scoreToGrade(79.9), equals('C'));
      expect(ScoreGauge.scoreToGrade(70), equals('C'));
      expect(ScoreGauge.scoreToGrade(69.9), equals('D'));
      expect(ScoreGauge.scoreToGrade(55), equals('D'));
      expect(ScoreGauge.scoreToGrade(54.9), equals('F'));
      expect(ScoreGauge.scoreToGrade(0), equals('F'));
    });

    testWidgets('ScoreGauge displays Limited coverage caption when coverage < 50%', (tester) async {
      await tester.pumpWidget(_wrap(const ScoreGauge(
        score: 95.0,
        coverage: 0.35, // < 50%
        basis: 'Based on 14 tests across 2 of 8 categories.',
        animate: false,
      )));
      await tester.pumpAndSettle();

      expect(find.text('Limited coverage'), findsOneWidget);
      expect(find.text('Based on 14 tests across 2 of 8 categories.'), findsOneWidget);
    });
  });
}
