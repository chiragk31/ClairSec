import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/app_theme.dart';
import '../../models/finding.dart';
import '../../models/scan_summary.dart';
import '../../providers/projects_provider.dart';
import '../../providers/findings_provider.dart';
import '../../providers/scans_provider.dart';
import '../shared/page_header.dart';
import '../shared/stat_card.dart';
import '../shared/empty_state.dart';
import '../vulnerabilities/widgets/finding_list_tile.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const PageHeader(
            title: 'Dashboard',
            subtitle: 'Overview of your security scan activity',
          ),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const _SummaryStats(),
                  const SizedBox(height: 32),
                  Text('Recent Scans', style: Theme.of(context).textTheme.headlineMedium),
                  const SizedBox(height: 12),
                  const _RecentScansSection(),
                  const SizedBox(height: 32),
                  Text('High-Priority Findings', style: Theme.of(context).textTheme.headlineMedium),
                  const SizedBox(height: 12),
                  const _FindingsSection(),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SummaryStats extends ConsumerWidget {
  const _SummaryStats();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // All three are live backend data: projects (Phase 2), scans and findings
    // (scans API). Each renders an honest zero/empty state while loading or on
    // error rather than implying data is definitely on the way.
    final projectsAsync = ref.watch(projectsProvider);
    final scans = ref.watch(scanListProvider);
    final findings = ref.watch(findingsProvider);

    final confirmedFindings = findings.where((f) => f.status == FindingStatus.confirmed);
    final fixedCount = confirmedFindings
        .where((f) => f.remediationStatus == RemediationStatus.fixVerified)
        .length;
    final criticalHighCount = confirmedFindings
        .where((f) => f.severity == FindingSeverity.critical || f.severity == FindingSeverity.high)
        .length;

    final projectsValue = projectsAsync.when(
      data: (list) => '${list.length}',
      loading: () => '—',
      error: (err, st) => '—',
    );

    return Wrap(
      spacing: 16,
      runSpacing: 16,
      children: [
        StatCard(
          label: 'Projects',
          value: projectsValue,
          icon: Icons.folder_outlined,
          tooltip: projectsAsync.hasError
              ? 'Could not reach the backend'
              : 'Total imported projects',
        ),
        StatCard(
          label: 'Scans',
          value: '${scans.length}',
          icon: Icons.radar_outlined,
          tooltip: 'Total scans run',
        ),
        StatCard(
          label: 'Vulnerabilities Found',
          value: '${confirmedFindings.length}',
          icon: Icons.bug_report_outlined,
          tooltip: 'Findings confirmed across all scans',
        ),
        StatCard(
          label: 'Vulnerabilities Fixed',
          value: '$fixedCount',
          icon: Icons.check_circle_outline,
          tooltip: 'Fixes verified by re-test',
        ),
        StatCard(
          label: 'Critical / High',
          value: '$criticalHighCount',
          icon: Icons.warning_amber_outlined,
          severity: criticalHighCount > 0 ? SeverityLevel.critical : SeverityLevel.none,
          tooltip: 'Confirmed findings with Critical or High severity',
        ),
      ],
    );
  }
}

class _RecentScansSection extends ConsumerWidget {
  const _RecentScansSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scans = ref.watch(scanListProvider);

    if (scans.isEmpty) {
      return const EmptyState(
        icon: Icons.radar_outlined,
        title: 'No scans yet',
        description:
            'Import a FastAPI project from the Projects page to run your first scan.',
      );
    }

    return Column(
      children: [
        for (final scan in scans.take(5)) ...[
          _ScanRow(scan: scan),
          const SizedBox(height: 8),
        ],
      ],
    );
  }
}

class _ScanRow extends StatelessWidget {
  final ScanSummary scan;
  const _ScanRow({required this.scan});

  Color get _stateColor => switch (scan.state) {
        ScanState.running => AppColors.accent,
        ScanState.completed => SeverityColors.success,
        ScanState.failed => SeverityColors.error,
        ScanState.cancelled => AppColors.textDisabled,
        ScanState.partial => SeverityColors.warning,
      };

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: () => context.go('/scans/${scan.id}'),
      borderRadius: BorderRadius.circular(8),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: AppColors.border),
        ),
        child: Row(
          children: [
            Icon(Icons.circle, size: 8, color: _stateColor),
            const SizedBox(width: 10),
            Expanded(
              child: Text(scan.projectName, style: Theme.of(context).textTheme.bodyLarge),
            ),
            Text(
              scan.state.label,
              style: Theme.of(context).textTheme.labelMedium?.copyWith(color: _stateColor),
            ),
          ],
        ),
      ),
    );
  }
}

class _FindingsSection extends ConsumerWidget {
  const _FindingsSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final findings = ref.watch(findingsProvider);
    final highPriority = findings
        .where((f) =>
            f.status == FindingStatus.confirmed &&
            (f.severity == FindingSeverity.critical || f.severity == FindingSeverity.high))
        .toList();

    if (highPriority.isEmpty) {
      return const EmptyState(
        icon: Icons.shield_outlined,
        title: 'No high-priority findings',
        description:
            'Critical and High severity vulnerabilities will appear here once a scan is complete.',
      );
    }

    return Column(
      children: [
        for (final finding in highPriority.take(5)) ...[
          FindingListTile(
            finding: finding,
            onTap: () => context.go('/vulnerabilities/${finding.id}'),
          ),
          const SizedBox(height: 8),
        ],
      ],
    );
  }
}
