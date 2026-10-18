import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:desktop/core/shell/app_shell.dart';
import 'package:desktop/features/wizard/first_run_wizard.dart';
import 'package:desktop/models/project.dart';
import 'package:desktop/providers/projects_provider.dart';
import 'package:desktop/providers/readiness_provider.dart';
import 'package:desktop/services/readiness_service.dart';
import 'package:desktop/core/theme/tokens.dart';

class _FakeProjectsNotifier extends ProjectsNotifier {
  _FakeProjectsNotifier(this._initialProjects);
  final List<ProjectRecord> _initialProjects;

  @override
  Future<List<ProjectRecord>> build() async => _initialProjects;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final sampleProject = ProjectRecord(
    id: 'proj-1',
    name: 'Sample Project',
    sourcePath: '/path/to/project',
    validationStatus: 'valid',
    validationErrors: const [],
    dependencies: const [],
    isolationReady: true,
    createdAt: DateTime.now(),
    updatedAt: DateTime.now(),
  );

  const greenReport = ReadinessReport([
    ReadinessCheck(name: 'Backend', ok: true, detail: 'Connected'),
  ]);

  const redReport = ReadinessReport([
    ReadinessCheck(name: 'Backend', ok: false, detail: 'Disconnected'),
  ]);

  setUp(() {
    SharedPreferences.setMockInitialValues({});
    AppShell.wizardShownThisLaunch = false;
  });

  Widget buildAppShell({
    required List<ProjectRecord> projects,
    required ReadinessReport readiness,
  }) {
    return ProviderScope(
      overrides: [
        projectsProvider.overrideWith(() => _FakeProjectsNotifier(projects)),
        readinessProvider.overrideWith((ref) async => readiness),
      ],
      child: MaterialApp(
        theme: ThemeData(
          extensions: const [ClairTokens.darkMidnight],
        ),
        home: const AppShell(
          child: Scaffold(body: Text('Child View')),
        ),
      ),
    );
  }

  testWidgets('B3: auto-shows wizard when zero projects exist', (tester) async {
    await tester.pumpWidget(buildAppShell(
      projects: [],
      readiness: greenReport,
    ));
    await tester.pumpAndSettle();

    expect(find.byType(FirstRunWizardDialog), findsOneWidget);
    expect(find.text('Welcome to ClairSec'), findsOneWidget);
  });

  testWidgets('B3: auto-shows wizard when readiness is red', (tester) async {
    await tester.pumpWidget(buildAppShell(
      projects: [sampleProject],
      readiness: redReport,
    ));
    await tester.pumpAndSettle();

    expect(find.byType(FirstRunWizardDialog), findsOneWidget);
    expect(find.text('Welcome to ClairSec'), findsOneWidget);
  });

  testWidgets('B3: does not auto-show wizard when projects exist and readiness is green', (tester) async {
    await tester.pumpWidget(buildAppShell(
      projects: [sampleProject],
      readiness: greenReport,
    ));
    await tester.pumpAndSettle();

    expect(find.byType(FirstRunWizardDialog), findsNothing);
  });

  testWidgets('B3: does not auto-show when "Don\'t show again" is persisted', (tester) async {
    SharedPreferences.setMockInitialValues({
      FirstRunWizardDialog.dontShowAgainPrefKey: true,
    });

    await tester.pumpWidget(buildAppShell(
      projects: [],
      readiness: redReport,
    ));
    await tester.pumpAndSettle();

    expect(find.byType(FirstRunWizardDialog), findsNothing);
  });

  testWidgets('B3: only auto-shows once per launch session', (tester) async {
    await tester.pumpWidget(buildAppShell(
      projects: [],
      readiness: greenReport,
    ));
    await tester.pumpAndSettle();

    expect(find.byType(FirstRunWizardDialog), findsOneWidget);

    // Dismiss dialog
    await tester.tap(find.text('Next: Appearance & Readiness'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Get Started'));
    await tester.pumpAndSettle();

    expect(find.byType(FirstRunWizardDialog), findsNothing);

    // Re-trigger pump with same session — should NOT show again
    await tester.pump();
    await tester.pumpAndSettle();
    expect(find.byType(FirstRunWizardDialog), findsNothing);
  });
}
