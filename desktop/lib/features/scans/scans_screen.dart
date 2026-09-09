import 'package:flutter/material.dart';
import '../../core/theme/app_theme.dart';
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

class _ScansContent extends StatelessWidget {
  const _ScansContent();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // Agent pipeline legend — shown even when empty, so users understand
        // the workflow before running their first scan.
        _PipelineLegend(),
        const SizedBox(height: 24),
        const Expanded(
          child: EmptyState(
            icon: Icons.radar_outlined,
            title: 'No scans yet',
            description:
                'Import a project and start a scan to see the Builder → Attacker → '
                'Evaluator → Fixer pipeline in action.',
          ),
        ),
      ],
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
