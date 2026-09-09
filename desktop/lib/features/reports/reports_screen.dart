import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/app_theme.dart';
import '../../models/finding.dart';
import '../../models/scan_summary.dart';
import '../../providers/findings_provider.dart';
import '../../providers/scans_provider.dart';
import '../shared/page_header.dart';
import '../shared/empty_state.dart';

/// Per-scan report summary.
///
/// Full document export is Phase 10; this presents the same underlying data
/// already held for each completed scan — counts by severity, remediation
/// outcome, and a link through to the findings themselves.
class ReportsScreen extends ConsumerWidget {
  const ReportsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scans = ref.watch(scanListProvider);
    final findings = ref.watch(findingsProvider);

    return Scaffold(
      backgroundColor: AppColors.background,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          PageHeader(
            title: 'Reports',
            subtitle: 'Summary of completed scans',
            actions: [
              IconButton(
                onPressed: () {
                  ref.invalidate(scansProvider);
                  ref.invalidate(allFindingsProvider);
                },
                icon: const Icon(Icons.refresh, size: 19),
                tooltip: 'Refresh',
              ),
            ],
          ),
          Expanded(
            child: scans.isEmpty
                ? const Padding(
                    padding: EdgeInsets.all(24),
                    child: EmptyState(
                      icon: Icons.description_outlined,
                      title: 'No reports available',
                      description:
                          'Complete a scan to generate a report. Reports cover '
                          'findings, severity distribution, fix status and '
                          'verification outcomes.',
                    ),
                  )
                : ListView.separated(
                    padding: const EdgeInsets.all(24),
                    itemCount: scans.length,
                    separatorBuilder: (context, i) => const SizedBox(height: 16),
                    itemBuilder: (context, i) => _ReportCard(
                      scan: scans[i],
                      findings: findings
                          .where((f) => f.scanId == scans[i].id)
                          .toList(),
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}

class _ReportCard extends StatelessWidget {
  final ScanSummary scan;
  final List<Finding> findings;

  const _ReportCard({required this.scan, required this.findings});

  @override
  Widget build(BuildContext context) {
    final confirmed =
        findings.where((f) => f.status == FindingStatus.confirmed).toList();
    final verified = confirmed
        .where((f) => f.remediationStatus == RemediationStatus.fixVerified)
        .length;
    final regressed = confirmed
        .where((f) => f.remediationStatus == RemediationStatus.regressed)
        .length;

    int countBy(FindingSeverity s) =>
        confirmed.where((f) => f.severity == s).length;

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      scan.projectName,
                      style: Theme.of(context).textTheme.headlineMedium,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Scan ${scan.id}',
                      style: AppTheme.monoStyle(
                          fontSize: 11, color: AppColors.textDisabled),
                    ),
                  ],
                ),
              ),
              OutlinedButton.icon(
                onPressed: () => context.go('/scans/${scan.id}'),
                icon: const Icon(Icons.open_in_new, size: 15),
                label: const Text('Open scan'),
              ),
            ],
          ),
          const SizedBox(height: 16),
          const Divider(height: 1),
          const SizedBox(height: 16),
          Wrap(
            spacing: 28,
            runSpacing: 12,
            children: [
              _Metric(label: 'Confirmed', value: '${confirmed.length}'),
              _Metric(
                label: 'Critical',
                value: '${countBy(FindingSeverity.critical)}',
                color: SeverityColors.critical,
              ),
              _Metric(
                label: 'High',
                value: '${countBy(FindingSeverity.high)}',
                color: SeverityColors.high,
              ),
              _Metric(
                label: 'Medium',
                value: '${countBy(FindingSeverity.medium)}',
                color: SeverityColors.medium,
              ),
              _Metric(
                label: 'Fixes verified',
                value: '$verified',
                color: SeverityColors.success,
              ),
              _Metric(
                label: 'Regressed',
                value: '$regressed',
                color: regressed > 0
                    ? SeverityColors.error
                    : AppColors.textSecondary,
              ),
            ],
          ),
          if (confirmed.isNotEmpty) ...[
            const SizedBox(height: 16),
            Text(
              'Findings',
              style: Theme.of(context).textTheme.labelMedium?.copyWith(
                    color: AppColors.textDisabled,
                  ),
            ),
            const SizedBox(height: 6),
            for (final f in confirmed)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Row(
                  children: [
                    Icon(f.severity.icon, size: 12, color: f.severity.color),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        f.title,
                        style: Theme.of(context).textTheme.bodySmall,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    Text(
                      f.remediationStatus.label,
                      style: Theme.of(context).textTheme.labelSmall?.copyWith(
                            color: f.remediationStatus.color,
                          ),
                    ),
                  ],
                ),
              ),
          ],
        ],
      ),
    );
  }
}

class _Metric extends StatelessWidget {
  final String label;
  final String value;
  final Color? color;

  const _Metric({required this.label, required this.value, this.color});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          value,
          style: Theme.of(context).textTheme.headlineLarge?.copyWith(
                color: color ?? AppColors.textPrimary,
              ),
        ),
        const SizedBox(height: 2),
        Text(
          label,
          style: Theme.of(context).textTheme.labelSmall,
        ),
      ],
    );
  }
}
