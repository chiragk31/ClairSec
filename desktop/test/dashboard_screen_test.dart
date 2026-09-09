import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:desktop/core/theme/app_theme.dart';
import 'package:desktop/features/dashboard/dashboard_screen.dart';
import 'package:desktop/features/vulnerabilities/finding_detail_screen.dart';
import 'package:desktop/models/finding.dart';
import 'package:desktop/models/scan_summary.dart';
import 'package:desktop/providers/findings_provider.dart';
import 'package:desktop/providers/scans_provider.dart';

Finding _finding({
  required String id,
  required FindingSeverity severity,
  FindingStatus status = FindingStatus.confirmed,
  RemediationStatus remediation = RemediationStatus.notStarted,
}) {
  return Finding(
    id: id,
    scanId: 'scan_1',
    title: 'Finding $id',
    category: 'BOLA',
    cwe: 'CWE-639',
    severity: severity,
    confidence: ConfidenceLevel.high,
    routeTemplate: '/x/{id}',
    method: 'GET',
    description: 'desc',
    impact: 'impact',
    runtimeConfirmed: true,
    status: status,
    createdAt: DateTime(2026, 1, 1),
    remediationStatus: remediation,
  );
}

Widget _wrap({List<Finding> findings = const [], List<ScanSummary> scans = const []}) {
  return ProviderScope(
    overrides: [
      findingsProvider.overrideWithValue(findings),
      scanListProvider.overrideWithValue(scans),
    ],
    child: MaterialApp.router(
      theme: AppTheme.dark,
      routerConfig: GoRouter(
        initialLocation: '/',
        routes: [
          GoRoute(path: '/', builder: (context, state) => const DashboardScreen()),
          GoRoute(
            path: '/scans/:scanId',
            builder: (context, state) =>
                Scaffold(body: Text('scan ${state.pathParameters['scanId']}')),
          ),
          GoRoute(
            path: '/vulnerabilities/:findingId',
            builder: (context, state) => FindingDetailScreen(
              findingId: state.pathParameters['findingId']!,
            ),
          ),
        ],
      ),
    ),
  );
}

void main() {
  testWidgets('shows honest zero/empty state with no data', (tester) async {
    await tester.pumpWidget(_wrap());
    await tester.pumpAndSettle();

    expect(find.text('No scans yet'), findsOneWidget);
    expect(find.text('No high-priority findings'), findsOneWidget);
  });

  testWidgets(
      'counts only confirmed findings, and only critical/high toward the priority tile',
      (tester) async {
    final findings = [
      _finding(id: 'f1', severity: FindingSeverity.critical),
      _finding(id: 'f2', severity: FindingSeverity.low), // confirmed but low — excluded from crit/high
      _finding(
        id: 'f3',
        severity: FindingSeverity.high,
        status: FindingStatus.rejected, // rejected — must not count as "found"
      ),
      _finding(
        id: 'f4',
        severity: FindingSeverity.high,
        remediation: RemediationStatus.fixVerified,
      ),
    ];

    await tester.pumpWidget(_wrap(findings: findings));
    await tester.pumpAndSettle();

    // Vulnerabilities Found: 3 confirmed (f1, f2, f4) — f3 is rejected.
    expect(find.text('3'), findsOneWidget);
    // Vulnerabilities Fixed: only f4 is fixVerified.
    expect(find.text('1'), findsOneWidget);
    // Critical/High confirmed: f1 (critical) + f4 (high) = 2. f2 is low, f3 is rejected.
    expect(find.text('2'), findsOneWidget);
  });

  testWidgets('high-priority findings list only shows confirmed critical/high',
      (tester) async {
    final findings = [
      _finding(id: 'f1', severity: FindingSeverity.critical),
      _finding(id: 'f2', severity: FindingSeverity.low),
    ];

    await tester.pumpWidget(_wrap(findings: findings));
    await tester.pumpAndSettle();

    expect(find.text('Finding f1'), findsOneWidget);
    expect(find.text('Finding f2'), findsNothing);
    expect(find.text('No high-priority findings'), findsNothing);
  });

  testWidgets('tapping a high-priority finding navigates to its detail screen',
      (tester) async {
    await tester.pumpWidget(
      _wrap(findings: [_finding(id: 'f1', severity: FindingSeverity.critical)]),
    );
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.text('Finding f1'));
    await tester.tap(find.text('Finding f1'));
    await tester.pumpAndSettle();

    expect(find.text('desc'), findsOneWidget); // detail screen's description field
  });

  testWidgets('tapping a recent scan navigates to its scan detail route',
      (tester) async {
    await tester.pumpWidget(
      _wrap(scans: [
        ScanSummary(
          id: 'scan_abc',
          projectName: 'demo-api',
          state: ScanState.running,
          startedAt: DateTime(2026, 1, 1),
        ),
      ]),
    );
    await tester.pumpAndSettle();

    expect(find.text('demo-api'), findsOneWidget);
    expect(find.text('Running'), findsOneWidget);

    await tester.ensureVisible(find.text('demo-api'));
    await tester.tap(find.text('demo-api'));
    await tester.pumpAndSettle();

    expect(find.text('scan scan_abc'), findsOneWidget);
  });
}
