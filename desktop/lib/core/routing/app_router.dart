import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../features/dashboard/dashboard_screen.dart';
import '../../features/projects/projects_screen.dart';
import '../../features/scans/scans_screen.dart';
import '../../features/scans/scan_detail_screen.dart';
import '../../features/vulnerabilities/vulnerabilities_screen.dart';
import '../../features/vulnerabilities/finding_detail_screen.dart';
import '../../features/fixes/fix_review_screen.dart';
import '../../features/agents/agents_screen.dart';
import '../../features/reports/reports_screen.dart';
import '../../features/settings/settings_screen.dart';
import '../shell/app_shell.dart';

// ---------------------------------------------------------------------------
// Route path constants
// ---------------------------------------------------------------------------
class AppRoutes {
  const AppRoutes._();

  static const String dashboard = '/';
  static const String projects = '/projects';
  static const String scans = '/scans';
  static String scanDetail(String scanId) => '/scans/$scanId';
  static String findingDetail(String findingId) => '/vulnerabilities/$findingId';
  static const String vulnerabilities = '/vulnerabilities';
  static const String agents = '/agents';
  static const String reports = '/reports';
  static const String research = '/research';
  static const String settings = '/settings';
}

// ---------------------------------------------------------------------------
// Router provider
// ---------------------------------------------------------------------------
final routerProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: AppRoutes.dashboard,
    debugLogDiagnostics: false,
    routes: [
      ShellRoute(
        builder: (context, state, child) => AppShell(child: child),
        routes: [
          GoRoute(
            path: AppRoutes.dashboard,
            pageBuilder: (context, state) => const NoTransitionPage(
              child: DashboardScreen(),
            ),
          ),
          GoRoute(
            path: AppRoutes.projects,
            pageBuilder: (context, state) => const NoTransitionPage(
              child: ProjectsScreen(),
            ),
          ),
          GoRoute(
            path: AppRoutes.scans,
            pageBuilder: (context, state) => const NoTransitionPage(
              child: ScansScreen(),
            ),
          ),
          GoRoute(
            path: '/scans/:scanId',
            pageBuilder: (context, state) => NoTransitionPage(
              child: ScanDetailScreen(scanId: state.pathParameters['scanId']!),
            ),
          ),
          GoRoute(
            path: AppRoutes.vulnerabilities,
            pageBuilder: (context, state) => const NoTransitionPage(
              child: VulnerabilitiesScreen(),
            ),
          ),
          GoRoute(
            path: '/vulnerabilities/:findingId',
            pageBuilder: (context, state) => NoTransitionPage(
              child: FindingDetailScreen(
                findingId: state.pathParameters['findingId']!,
              ),
            ),
          ),
          GoRoute(
            path: '/fixes/:findingId',
            pageBuilder: (context, state) => NoTransitionPage(
              child: FixReviewScreen(
                findingId: state.pathParameters['findingId']!,
              ),
            ),
          ),
          GoRoute(
            path: AppRoutes.agents,
            pageBuilder: (context, state) => const NoTransitionPage(
              child: AgentsScreen(),
            ),
          ),
          GoRoute(
            path: AppRoutes.reports,
            pageBuilder: (context, state) => const NoTransitionPage(
              child: ReportsScreen(),
            ),
          ),
          GoRoute(
            path: AppRoutes.research,
            pageBuilder: (context, state) => const NoTransitionPage(
              child: ResearchScreen(),
            ),
          ),
          GoRoute(
            path: AppRoutes.settings,
            pageBuilder: (context, state) => const NoTransitionPage(
              child: SettingsScreen(),
            ),
          ),
        ],
      ),
    ],
    errorBuilder: (context, state) => _RouteErrorPage(error: state.error),
  );
});

class _RouteErrorPage extends StatelessWidget {
  final Exception? error;
  const _RouteErrorPage({this.error});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Text(
          'Page not found: ${error?.toString() ?? "unknown error"}',
          style: Theme.of(context).textTheme.bodyLarge,
        ),
      ),
    );
  }
}

// Research screen is owned here temporarily (placeholder only)
class ResearchScreen extends StatelessWidget {
  const ResearchScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const _PlaceholderPage(
      icon: Icons.science_outlined,
      title: 'Research',
      description:
          'Experiment results, metric comparisons, and dataset analysis '
          'will appear here when research mode is enabled.',
    );
  }
}

class _PlaceholderPage extends StatelessWidget {
  final IconData icon;
  final String title;
  final String description;

  const _PlaceholderPage({
    required this.icon,
    required this.title,
    required this.description,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 48, color: theme.colorScheme.outline),
            const SizedBox(height: 16),
            Text(title, style: theme.textTheme.headlineMedium),
            const SizedBox(height: 8),
            Text(
              description,
              style: theme.textTheme.bodyMedium,
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}
