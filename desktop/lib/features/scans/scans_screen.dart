import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/app_theme.dart';
import '../../models/scan_summary.dart';
import '../../providers/scans_provider.dart';
import '../shared/page_header.dart';
import '../shared/empty_state.dart';

class ScansScreen extends StatelessWidget {
  const ScansScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: const [
          PageHeader(
            title: 'Scans',
            subtitle: 'Security scan history and active sessions',
          ),
          Expanded(
            child: Padding(
              padding: EdgeInsets.all(24),
              child: _ScansContent(),
            ),
          ),
        ],
      ),
    );
  }
}

class _ScansContent extends ConsumerWidget {
  const _ScansContent();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scans = ref.watch(scanListProvider);

    return Column(
      children: [
        // Agent pipeline legend — shown even when empty, so users understand
        // the workflow before running their first scan.
        _PipelineLegend(),
        const SizedBox(height: 24),
        Expanded(
          child: scans.isEmpty
              ? const EmptyState(
                  icon: Icons.radar_outlined,
                  title: 'No scans yet',
                  description:
                      'Import a project and start a scan to see the Builder → Attacker → '
                      'Evaluator → Fixer pipeline in action.',
                )
              : ListView.separated(
                  itemCount: scans.length,
                  separatorBuilder: (context, i) => const SizedBox(height: 12),
                  itemBuilder: (context, i) => _ScanCard(scan: scans[i]),
                ),
        ),
      ],
    );
  }
}

class _ScanCard extends StatelessWidget {
  final ScanSummary scan;
  const _ScanCard({required this.scan});

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
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: AppColors.border),
        ),
        child: Row(
          children: [
            Icon(Icons.circle, size: 9, color: _stateColor),
            const SizedBox(width: 12),
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
                    scan.id,
                    style: AppTheme.monoStyle(
                        fontSize: 11, color: AppColors.textDisabled),
                  ),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  scan.state.label,
                  style: Theme.of(context)
                      .textTheme
                      .labelMedium
                      ?.copyWith(color: _stateColor),
                ),
                const SizedBox(height: 4),
                Text(
                  '${scan.findingsConfirmed} confirmed',
                  style: Theme.of(context).textTheme.labelSmall,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _PipelineLegend extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    const agents = [
      _AgentChip(label: 'Builder', icon: Icons.search_outlined, description: 'Analyses project structure and API surface'),
      _AgentChip(label: 'Attacker', icon: Icons.bolt_outlined, description: 'Executes controlled security tests'),
      _AgentChip(label: 'Evaluator', icon: Icons.fact_check_outlined, description: 'Independently validates findings'),
      _AgentChip(label: 'Fixer', icon: Icons.build_outlined, description: 'Generates minimal source patches'),
    ];

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Scan pipeline',
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  color: AppColors.textSecondary,
                  letterSpacing: 0.5,
                ),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (int i = 0; i < agents.length; i++) ...[
                agents[i],
                if (i < agents.length - 1)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 6),
                    child: Icon(Icons.arrow_forward, size: 14, color: AppColors.textDisabled),
                  ),
              ],
            ],
          ),
        ],
      ),
    );
  }
}

class _AgentChip extends StatelessWidget {
  final String label;
  final IconData icon;
  final String description;

  const _AgentChip({
    required this.label,
    required this.icon,
    required this.description,
  });

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: description,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
        decoration: BoxDecoration(
          color: AppColors.surfaceVariant,
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: AppColors.border),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 14, color: AppColors.textSecondary),
            const SizedBox(width: 6),
            Text(label, style: Theme.of(context).textTheme.labelLarge),
          ],
        ),
      ),
    );
  }
}
