import 'package:flutter/material.dart';
import '../../shared/stat_card.dart';
import '../../../models/scan_detail.dart';

/// Rollup counters shown below the agent cards (DESIGN.md §6): discovered
/// endpoints, tests executed, findings discovered/confirmed, fixes
/// generated/verified. Reuses [StatCard] for visual consistency with the
/// dashboard rather than introducing a second stat-tile style.
class ScanSummaryStrip extends StatelessWidget {
  final ScanRunSummary summary;

  const ScanSummaryStrip({super.key, required this.summary});

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: [
        StatCard(
          label: 'Endpoints discovered',
          value: '${summary.endpointsDiscovered}',
          icon: Icons.route_outlined,
        ),
        StatCard(
          label: 'Tests executed',
          value: '${summary.testsExecuted}',
          icon: Icons.checklist_outlined,
        ),
        StatCard(
          label: 'Findings discovered',
          value: '${summary.findingsDiscovered}',
          icon: Icons.report_gmailerrorred_outlined,
          severity: summary.findingsDiscovered > 0 ? SeverityLevel.medium : SeverityLevel.none,
        ),
        StatCard(
          label: 'Findings confirmed',
          value: '${summary.findingsConfirmed}',
          icon: Icons.verified_outlined,
          severity: summary.findingsConfirmed > 0 ? SeverityLevel.high : SeverityLevel.none,
        ),
        StatCard(
          label: 'Fixes generated',
          value: '${summary.fixesGenerated}',
          icon: Icons.build_circle_outlined,
        ),
        StatCard(
          label: 'Fixes verified',
          value: '${summary.fixesVerified}',
          icon: Icons.task_alt_outlined,
        ),
      ],
    );
  }
}
