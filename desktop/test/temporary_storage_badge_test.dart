import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:desktop/core/shell/app_shell.dart';
import 'package:desktop/core/theme/tokens.dart';
import 'package:desktop/models/project.dart';
import 'package:desktop/providers/projects_provider.dart';
import 'package:desktop/providers/readiness_provider.dart';
import 'package:desktop/services/readiness_service.dart';
import 'package:desktop/ui/components/cs_badge.dart';

class _OneProject extends ProjectsNotifier {
  @override
  Future<List<ProjectRecord>> build() async => [
        ProjectRecord(
          id: 'p1',
          name: 'P',
          sourcePath: '/p',
          validationStatus: 'valid',
          validationErrors: const [],
          dependencies: const [],
          isolationReady: true,
          createdAt: DateTime(2026),
          updatedAt: DateTime(2026),
        ),
      ];
}

Widget _shell(ReadinessReport report) => ProviderScope(
      overrides: [
        projectsProvider.overrideWith(() => _OneProject()),
        readinessProvider.overrideWith((ref) async => report),
      ],
      child: MaterialApp(
        theme: ThemeData(extensions: const [ClairTokens.darkMidnight]),
        home: const AppShell(child: Scaffold(body: Text('child'))),
      ),
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() {
    SharedPreferences.setMockInitialValues({'clairsec_wizard_dont_show': true});
    AppShell.wizardShownThisLaunch = true;
  });

  const ok = [ReadinessCheck(name: 'Backend', ok: true, detail: 'Connected')];

  testWidgets('D3: shows TEMPORARY STORAGE badge on the memory fallback', (tester) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(_shell(const ReadinessReport(ok, storage: 'memory')));
    await tester.pumpAndSettle();
    expect(find.text(TemporaryStorageBadge.label), findsOneWidget);
  });

  testWidgets('D3: no storage badge when MongoDB is connected', (tester) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(_shell(const ReadinessReport(ok)));
    await tester.pumpAndSettle();
    expect(find.text(TemporaryStorageBadge.label), findsNothing);
  });
}
