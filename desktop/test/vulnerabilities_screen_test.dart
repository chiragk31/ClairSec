import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:desktop/core/theme/app_theme.dart';
import 'package:desktop/features/vulnerabilities/vulnerabilities_screen.dart';
import 'package:desktop/features/vulnerabilities/finding_detail_screen.dart';
import 'package:desktop/models/finding.dart';
import 'package:desktop/providers/findings_provider.dart';

final _sampleFindings = [
  Finding(
    id: 'finding_1',
    scanId: 'scan_1',
    title: 'Broken Object Level Authorization on document read',
    category: 'BOLA',
    cwe: 'CWE-639',
    severity: FindingSeverity.critical,
    confidence: ConfidenceLevel.high,
    routeTemplate: '/documents/{doc_id}',
    method: 'GET',
    description: 'Principal A can read documents owned by Principal B.',
    impact: 'Full read access to any user\'s documents.',
    runtimeConfirmed: true,
    status: FindingStatus.confirmed,
    statusReason: 'Reproduced 3 times; oracle fired on distinct owner_id.',
    createdAt: DateTime(2026, 1, 1),
    remediationStatus: RemediationStatus.fixVerified,
  ),
  Finding(
    id: 'finding_2',
    scanId: 'scan_1',
    title: 'Mass assignment via profile update',
    category: 'BOPLA_MASS_ASSIGN',
    cwe: 'CWE-915',
    severity: FindingSeverity.high,
    confidence: ConfidenceLevel.medium,
    routeTemplate: '/users/{user_id}/profile',
    method: 'PUT',
    description: 'Privileged fields are persisted from an unfiltered payload.',
    impact: 'Privilege escalation to admin role.',
    runtimeConfirmed: true,
    status: FindingStatus.confirmed,
    createdAt: DateTime(2026, 1, 1),
  ),
];

Widget _wrapList({List<Finding> findings = const []}) {
  return ProviderScope(
    overrides: [findingsProvider.overrideWithValue(findings)],
    child: MaterialApp.router(
      theme: AppTheme.dark,
      routerConfig: GoRouter(
        initialLocation: '/',
        routes: [
          GoRoute(path: '/', builder: (context, state) => const VulnerabilitiesScreen()),
          GoRoute(
            path: '/vulnerabilities/:findingId',
            builder: (_, state) => FindingDetailScreen(
              findingId: state.pathParameters['findingId']!,
            ),
          ),
        ],
      ),
    ),
  );
}

void main() {
  testWidgets('shows honest empty state when there are no findings', (tester) async {
    await tester.pumpWidget(_wrapList());
    await tester.pumpAndSettle();

    expect(find.text('No vulnerabilities found yet'), findsOneWidget);
  });

  testWidgets('renders a list tile per finding with severity and status',
      (tester) async {
    await tester.pumpWidget(_wrapList(findings: _sampleFindings));
    await tester.pumpAndSettle();

    expect(find.text('No vulnerabilities found yet'), findsNothing);
    expect(
      find.text('Broken Object Level Authorization on document read'),
      findsOneWidget,
    );
    expect(find.text('Mass assignment via profile update'), findsOneWidget);
    // findsWidgets, not findsOneWidget: the page's always-visible severity
    // legend also renders "Critical" and "High" as labels.
    expect(find.text('Critical'), findsWidgets);
    expect(find.text('High'), findsWidgets);
    expect(find.text('Runtime confirmed'), findsNWidgets(2));
  });

  testWidgets('tapping a finding navigates to its detail screen', (tester) async {
    await tester.pumpWidget(_wrapList(findings: _sampleFindings));
    await tester.pumpAndSettle();

    await tester.tap(
      find.text('Broken Object Level Authorization on document read'),
    );
    await tester.pumpAndSettle();

    expect(
      find.text('Principal A can read documents owned by Principal B.'),
      findsOneWidget,
    );
    expect(
      find.text('Reproduced 3 times; oracle fired on distinct owner_id.'),
      findsOneWidget,
    );
    expect(find.text('Fix verified'), findsOneWidget);
  });

  testWidgets('detail screen shows honest not-found state for an unknown id',
      (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [findingsProvider.overrideWithValue(_sampleFindings)],
        child: const MaterialApp(
          home: FindingDetailScreen(findingId: 'does_not_exist'),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Finding not found'), findsOneWidget);
  });
}
