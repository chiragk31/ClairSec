import 'package:flutter/material.dart';
import '../../core/theme/app_theme.dart';
import '../shared/page_header.dart';
import '../shared/stat_card.dart';
import '../shared/empty_state.dart';

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
                  // ── Summary stats row ──────────────────────────────────
                  const _SummaryStats(),
                  const SizedBox(height: 32),

                  // ── Recent scans ───────────────────────────────────────
                  Text(
                    'Recent Scans',
                    style: Theme.of(context).textTheme.headlineMedium,
                  ),
                  const SizedBox(height: 12),
                  const _RecentScansSection(),
                  const SizedBox(height: 32),

                  // ── Critical & High findings ───────────────────────────
                  Text(
                    'High-Priority Findings',
                    style: Theme.of(context).textTheme.headlineMedium,
                  ),
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

class _SummaryStats extends StatelessWidget {
  const _SummaryStats();

  @override
  Widget build(BuildContext context) {
    // No data yet — all show zero / empty state to be honest about state.
    return Wrap(
      spacing: 16,
      runSpacing: 16,
      children: const [
        StatCard(
          label: 'Projects',
          value: '0',
          icon: Icons.folder_outlined,
          tooltip: 'Total imported projects',
        ),
        StatCard(
          label: 'Scans',
          value: '0',
          icon: Icons.radar_outlined,
          tooltip: 'Total scans run',
        ),
        StatCard(
          label: 'Vulnerabilities Found',
          value: '0',
          icon: Icons.bug_report_outlined,
          tooltip: 'Findings confirmed across all scans',
        ),
        StatCard(
          label: 'Vulnerabilities Fixed',
          value: '0',
          icon: Icons.check_circle_outline,
          tooltip: 'Fixes verified by re-test',
        ),
        StatCard(
          label: 'Critical / High',
          value: '0',
          icon: Icons.warning_amber_outlined,
          severity: SeverityLevel.critical,
          tooltip: 'Open findings with Critical or High severity',
        ),
      ],
    );
  }
}

class _RecentScansSection extends StatelessWidget {
  const _RecentScansSection();

  @override
  Widget build(BuildContext context) {
    return const EmptyState(
      icon: Icons.radar_outlined,
      title: 'No scans yet',
      description:
          'Import a FastAPI project from the Projects page to run your first scan.',
    );
  }
}

class _FindingsSection extends StatelessWidget {
  const _FindingsSection();

  @override
  Widget build(BuildContext context) {
    return const EmptyState(
      icon: Icons.shield_outlined,
      title: 'No high-priority findings',
      description:
          'Critical and High severity vulnerabilities will appear here once a scan is complete.',
    );
  }
}
