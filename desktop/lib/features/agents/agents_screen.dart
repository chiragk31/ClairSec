import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/app_theme.dart';
import '../../core/theme/tokens.dart';
import '../../models/scan_summary.dart';
import '../../providers/scans_provider.dart';
import '../shared/page_header.dart';
import '../shared/empty_state.dart';

class AgentsScreen extends StatelessWidget {
  const AgentsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;

    return Scaffold(
      backgroundColor: tokens.bg,
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

    return SingleChildScrollView(
      padding: const EdgeInsets.all(ClairSpacing.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _AgentRoleCards(),
          const SizedBox(height: ClairSpacing.xxl),
          if (scans.isEmpty)
            const EmptyState(
              icon: Icons.smart_toy_outlined,
              title: 'No scan activity yet',
              description:
                  'Once a scan runs, the activity log and per-agent progress will be recorded here.',
            )
          else ...[
            _RecentScanCard(scan: scans.first),
          ],
        ],
      ),
    );
  }
}

class _RecentScanCard extends StatelessWidget {
  final ScanSummary scan;
  const _RecentScanCard({required this.scan});

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(ClairSpacing.lg),
      decoration: BoxDecoration(
        color: tokens.surface,
        borderRadius: BorderRadius.circular(ClairRadius.md),
        border: Border.all(color: tokens.border),
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
            style: AppTheme.monoStyle(fontSize: ClairTypography.caption, color: tokens.textMuted),
          ),
          const SizedBox(height: ClairSpacing.lg),
          Divider(height: 1, color: tokens.border),
          const SizedBox(height: ClairSpacing.lg),
          _Row(label: 'Pipeline state', value: scan.state.label),
          _Row(
            label: 'Findings recorded',
            value: '${scan.findingsCount} candidate(s)',
          ),
          _Row(
            label: 'Fixes applied',
            value: '${scan.fixesAppliedCount} patch(es)',
          ),
        ],
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
    final tokens = context.tokens;

    return Padding(
      padding: const EdgeInsets.only(bottom: ClairSpacing.sm),
      child: Row(
        children: [
          SizedBox(
            width: 160,
            child: Text(
              label,
              style: Theme.of(context).textTheme.labelMedium?.copyWith(
                    color: tokens.textMuted,
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
      spacing: ClairSpacing.md,
      runSpacing: ClairSpacing.md,
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
    final tokens = context.tokens;

    return SizedBox(
      width: 240,
      child: Container(
        padding: const EdgeInsets.all(ClairSpacing.lg),
        decoration: BoxDecoration(
          color: tokens.surface,
          borderRadius: BorderRadius.circular(ClairRadius.md),
          border: Border.all(color: tokens.border),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, size: 16, color: tokens.accent),
                const SizedBox(width: ClairSpacing.sm),
                Text(name, style: Theme.of(context).textTheme.headlineMedium),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              role.toUpperCase(),
              style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: tokens.accent,
                    letterSpacing: 0.8,
                  ),
            ),
            const SizedBox(height: ClairSpacing.sm),
            Text(description, style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}
