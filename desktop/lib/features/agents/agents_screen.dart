import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/app_theme.dart';
import '../../models/scan_summary.dart';
import '../../providers/scans_provider.dart';
import '../shared/page_header.dart';
import '../shared/empty_state.dart';

class AgentsScreen extends StatelessWidget {
  const AgentsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: const [
          PageHeader(
            title: 'Agents',
            subtitle: 'Inspect agent activity across scans',
          ),
          Expanded(child: _AgentsContent()),
        ],
      ),
    );
  }
}

class _AgentsContent extends ConsumerWidget {
  const _AgentsContent();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scans = ref.watch(scanListProvider);
    final latest = scans.isEmpty ? null : scans.first;

    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _AgentRoleCards(),
          const SizedBox(height: 24),
          Expanded(
            child: latest == null
                ? const EmptyState(
                    icon: Icons.smart_toy_outlined,
                    title: 'No agent activity',
                    description:
                        'Structured agent events — tasks, actions, results, and '
                        'durations — will appear here during and after a scan. '
                        'Raw chain-of-thought is not exposed.',
                  )
                : _LatestRunPanel(scan: latest),
          ),
        ],
      ),
    );
  }
}

/// Summary of the most recent pipeline run. Shows the stage the backend
/// reported and the confirmed-finding count — operational detail only, never
/// model reasoning (DESIGN.md §9).
class _LatestRunPanel extends StatelessWidget {
  final ScanSummary scan;
  const _LatestRunPanel({required this.scan});

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      child: Container(
        width: double.infinity,
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
                  child: Text(
                    'Most recent run — ${scan.projectName}',
                    style: Theme.of(context).textTheme.headlineMedium,
                  ),
                ),
                OutlinedButton.icon(
                  onPressed: () => context.go('/scans/${scan.id}'),
                  icon: const Icon(Icons.open_in_new, size: 15),
                  label: const Text('Open scan'),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              scan.id,
              style:
                  AppTheme.monoStyle(fontSize: 11, color: AppColors.textDisabled),
            ),
            const SizedBox(height: 16),
            const Divider(height: 1),
            const SizedBox(height: 16),
            _Row(label: 'Pipeline state', value: scan.state.label),
            _Row(
              label: 'Reported stage',
              value: scan.stage.isEmpty ? '—' : scan.stage,
            ),
            _Row(
              label: 'Findings confirmed',
              value: '${scan.findingsConfirmed}',
            ),
            const SizedBox(height: 12),
            Text(
              'Per-agent progress for this run is shown on the scan view. '
              'Full event-level streaming arrives with the live agent UI.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}

class _Row extends StatelessWidget {
  final String label;
  final String value;
  const _Row({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          SizedBox(
            width: 160,
            child: Text(
              label,
              style: Theme.of(context).textTheme.labelMedium?.copyWith(
                    color: AppColors.textDisabled,
                  ),
            ),
          ),
          Text(value, style: Theme.of(context).textTheme.bodyLarge),
        ],
      ),
    );
  }
}

class _AgentRoleCards extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    const agents = [
      _AgentRoleCard(
        name: 'Builder',
        icon: Icons.search_outlined,
        role: 'Understand the target',
        description: 'Inspects project structure, discovers routes and auth mechanisms, extracts OpenAPI context.',
      ),
      _AgentRoleCard(
        name: 'Attacker',
        icon: Icons.bolt_outlined,
        role: 'Challenge the target',
        description: 'Selects test categories, generates controlled payloads, records request/response evidence.',
      ),
      _AgentRoleCard(
        name: 'Evaluator',
        icon: Icons.fact_check_outlined,
        role: 'Validate independently',
        description: 'Reviews attacker evidence, reproduces candidates, filters false positives, assigns severity.',
      ),
      _AgentRoleCard(
        name: 'Fixer',
        icon: Icons.build_outlined,
        role: 'Remediate findings',
        description: 'Generates minimal source patches, applies them only to the isolated workspace, triggers re-test.',
      ),
    ];

    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: agents,
    );
  }
}

class _AgentRoleCard extends StatelessWidget {
  final String name;
  final IconData icon;
  final String role;
  final String description;

  const _AgentRoleCard({
    required this.name,
    required this.icon,
    required this.role,
    required this.description,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 240,
      child: Container(
        padding: const EdgeInsets.all(16),
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
                Icon(icon, size: 16, color: AppColors.accent),
                const SizedBox(width: 8),
                Text(name, style: Theme.of(context).textTheme.headlineMedium),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              role.toUpperCase(),
              style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: AppColors.accent,
                    letterSpacing: 0.8,
                  ),
            ),
            const SizedBox(height: 8),
            Text(description, style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}
