import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:desktop/core/theme/tokens.dart';
import 'package:desktop/features/dashboard/dashboard_screen.dart';
import 'package:desktop/features/projects/projects_screen.dart';
import 'package:desktop/features/scans/scan_detail_screen.dart';
import 'package:desktop/features/vulnerabilities/finding_detail_screen.dart';
import 'package:desktop/features/settings/settings_screen.dart';
import 'package:desktop/models/finding.dart';
import 'package:desktop/models/project.dart';
import 'package:desktop/models/scan_detail.dart';
import 'package:desktop/models/scan_summary.dart';
import 'package:desktop/providers/findings_provider.dart';
import 'package:desktop/providers/projects_provider.dart';
import 'package:desktop/providers/scans_provider.dart';
import 'package:desktop/providers/scan_detail_provider.dart';
import 'package:desktop/providers/readiness_provider.dart';
import 'package:desktop/services/health_service.dart';
import 'package:desktop/services/readiness_service.dart';

const _testScanId = 'scan_resp_test_001';
const _testFindingId = 'finding_resp_test_001';

final _sampleFinding = Finding(
  id: _testFindingId,
  scanId: _testScanId,
  title: 'BOLA vulnerability on object read endpoint',
  category: 'BOLA',
  cwe: 'CWE-639',
  severity: FindingSeverity.critical,
  confidence: ConfidenceLevel.high,
  routeTemplate: '/documents/{doc_id}',
  method: 'GET',
  description: 'Principal A can read documents owned by Principal B without authorization.',
  impact: 'Confidentiality breach across multi-tenant user accounts.',
  runtimeConfirmed: true,
  status: FindingStatus.confirmed,
  statusReason: 'Deterministic oracle fired on 2 distinct tenant boundaries.',
  createdAt: DateTime(2026, 1, 1),
  remediationStatus: RemediationStatus.fixVerified,
);

final _sampleScanSummary = ScanSummary(
  id: _testScanId,
  projectName: 'FastAPI Store App',
  state: ScanState.completed,
  startedAt: DateTime(2026, 1, 1),
  findingsConfirmed: 2,
  findingsDiscovered: 4,
  fixesVerified: 1,
);

const _sampleScanRunSummary = ScanRunSummary(
  endpointsDiscovered: 4,
  testsExecuted: 10,
  findingsDiscovered: 2,
  findingsConfirmed: 2,
  fixesGenerated: 1,
  fixesVerified: 1,
);

final _sampleScanDetail = ScanDetailState(
  scanId: _testScanId,
  summary: _sampleScanRunSummary,
  agentCards: {
    for (final role in AgentRole.values)
      role: AgentCardState(
        role: role,
        status: AgentStatus.completed,
        currentTask: 'Task finished',
        eventCount: 5,
        elapsed: const Duration(seconds: 12),
      ),
  },
);

final _sampleProject = ProjectRecord(
  id: 'proj_001',
  name: 'Demo Backend',
  sourcePath: '/tmp/demo_backend',
  validationStatus: 'valid',
  validationErrors: const [],
  dependencies: const [],
  isolationReady: true,
  createdAt: DateTime(2026, 1, 1),
  updatedAt: DateTime(2026, 1, 1),
);

Widget _buildWrapper({required Widget child}) {
  return ProviderScope(
    overrides: [
      findingsProvider.overrideWithValue([_sampleFinding]),
      allFindingsProvider.overrideWith((ref) async => [_sampleFinding]),
      findingByIdProvider(_testFindingId).overrideWithValue(_sampleFinding),
      scanListProvider.overrideWithValue([_sampleScanSummary]),
      scansProvider.overrideWith((ref) async => [_sampleScanSummary]),
      scanDetailProvider(_testScanId).overrideWithValue(_sampleScanDetail),
      scanFindingsProvider(_testScanId).overrideWith((ref) async => [_sampleFinding]),
      projectsProvider.overrideWith(() => _FakeProjectsNotifier([_sampleProject])),
      backendStatusProvider.overrideWith((ref) async => BackendStatus.connected),
      readinessProvider.overrideWith((ref) async => const ReadinessReport([])),
    ],
    child: MaterialApp(
      theme: ThemeData(
        extensions: const [ClairTokens.darkMidnight],
      ),
      home: child,
    ),
  );
}

class _FakeProjectsNotifier extends ProjectsNotifier {
  final List<ProjectRecord> initialList;
  _FakeProjectsNotifier(this.initialList);

  @override
  Future<List<ProjectRecord>> build() async => initialList;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final widths = [400.0, 900.0, 1300.0, 1700.0];

  group('Responsive Shell & Screens Overflow Tests (V1 exit gate)', () {
    for (final width in widths) {
      testWidgets('DashboardScreen renders without overflow at ${width.toInt()}px', (tester) async {
        tester.view.physicalSize = Size(width, 900);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(() => tester.view.resetPhysicalSize());

        await tester.pumpWidget(_buildWrapper(child: const DashboardScreen()));
        await tester.pumpAndSettle();

        expect(
          tester.takeException(),
          isNull,
          reason: 'Overflow occurred on DashboardScreen at width ${width.toInt()}px',
        );
      });

      testWidgets('ProjectsScreen renders without overflow at ${width.toInt()}px', (tester) async {
        tester.view.physicalSize = Size(width, 900);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(() => tester.view.resetPhysicalSize());

        await tester.pumpWidget(_buildWrapper(child: const ProjectsScreen()));
        await tester.pumpAndSettle();

        expect(
          tester.takeException(),
          isNull,
          reason: 'Overflow occurred on ProjectsScreen at width ${width.toInt()}px',
        );
      });

      testWidgets('ScanDetailScreen renders without overflow at ${width.toInt()}px', (tester) async {
        tester.view.physicalSize = Size(width, 900);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(() => tester.view.resetPhysicalSize());

        await tester.pumpWidget(_buildWrapper(child: const ScanDetailScreen(scanId: _testScanId)));
        await tester.pumpAndSettle();

        expect(
          tester.takeException(),
          isNull,
          reason: 'Overflow occurred on ScanDetailScreen at width ${width.toInt()}px',
        );
      });

      testWidgets('FindingDetailScreen renders without overflow at ${width.toInt()}px', (tester) async {
        tester.view.physicalSize = Size(width, 900);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(() => tester.view.resetPhysicalSize());

        await tester.pumpWidget(_buildWrapper(child: const FindingDetailScreen(findingId: _testFindingId)));
        await tester.pumpAndSettle();

        expect(
          tester.takeException(),
          isNull,
          reason: 'Overflow occurred on FindingDetailScreen at width ${width.toInt()}px',
        );
      });

      testWidgets('SettingsScreen renders without overflow at ${width.toInt()}px', (tester) async {
        tester.view.physicalSize = Size(width, 900);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(() => tester.view.resetPhysicalSize());

        await tester.pumpWidget(_buildWrapper(child: const SettingsScreen()));
        await tester.pumpAndSettle();

        expect(
          tester.takeException(),
          isNull,
          reason: 'Overflow occurred on SettingsScreen at width ${width.toInt()}px',
        );
      });
    }
  });
}
