import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/app_theme.dart';
import '../../core/theme/tokens.dart';
import '../../models/scan_summary.dart';
import '../../providers/scans_provider.dart';
import '../shared/page_header.dart';
import '../shared/empty_state.dart';
import 'widgets/recorded_run_dialog.dart';

class ScansScreen extends ConsumerWidget {
  const ScansScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tokens = context.tokens;

    return Scaffold(
      backgroundColor: tokens.bg,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          PageHeader(
            title: 'Scans',
            subtitle: 'Security scan history and active sessions',
            actions: [
              TextButton.icon(
                onPressed: () => RecordedRunDialog.show(context),
                icon: const Icon(Icons.history, size: 17),
                label: const Text('Watch a recorded run'),
              ),
              IconButton(
                onPressed: () => ref.invalidate(scansProvider),
                icon: const Icon(Icons.refresh, size: 19),
                tooltip: 'Refresh',
              ),
            ],
          ),
          const Expanded(
            child: Padding(
              padding: EdgeInsets.all(ClairSpacing.xl),
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
    final scansAsync = ref.watch(scansProvider);

    return scansAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (err, _) => EmptyState(
        icon: Icons.error_outline,
        title: 'Failed to load scans',
        description: err.toString(),
        action: ElevatedButton(
          onPressed: () => ref.invalidate(scansProvider),
          child: const Text('Retry'),
        ),
      ),
      data: (scans) {
        if (scans.isEmpty) {
          return EmptyState(
            icon: Icons.radar_outlined,
            title: 'No scans yet',
            description:
                'Run a security scan against an imported project to see '
                'agent attack logs and confirmed vulnerabilities.',
            action: ElevatedButton.icon(
              onPressed: () => context.go('/projects'),
              icon: const Icon(Icons.folder_open, size: 16),
              label: const Text('Go to Projects'),
            ),
          );
        }

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const _ScanPipelineOverview(),
            const SizedBox(height: ClairSpacing.xl),
            Expanded(
              child: ListView.separated(
                itemCount: scans.length,
                separatorBuilder: (context, i) => const SizedBox(height: ClairSpacing.sm),
                itemBuilder: (context, i) => _ScanCard(scan: scans[i]),
              ),
            ),
          ],
        );
      },
    );
  }
}

class _ScanCard extends StatelessWidget {
  final ScanSummary scan;
  const _ScanCard({required this.scan});

  Color _stateColor(ClairTokens tokens) => switch (scan.state) {
        ScanState.running => tokens.accent,
        ScanState.completed => tokens.success,
        ScanState.failed => tokens.critical,
        ScanState.cancelled => tokens.textMuted,
        ScanState.partial => tokens.warning,
      };

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    final stateColor = _stateColor(tokens);

    return InkWell(
      onTap: () => context.go('/scans/${scan.id}'),
      borderRadius: BorderRadius.circular(ClairRadius.md),
      child: Container(
        padding: const EdgeInsets.all(ClairSpacing.lg),
        decoration: BoxDecoration(
          color: tokens.surface,
          borderRadius: BorderRadius.circular(ClairRadius.md),
          border: Border.all(color: tokens.border),
        ),
        child: Row(
          children: [
            Icon(Icons.circle, size: 9, color: stateColor),
            const SizedBox(width: ClairSpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    scan.projectName,
                    style: Theme.of(context).textTheme.headlineMedium,
                  ),
                  const SizedBox(height: ClairSpacing.xs),
                  Text(
                    scan.id,
                    style: AppTheme.monoStyle(
                        fontSize: ClairTypography.caption, color: tokens.textMuted),
                  ),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  scan.state.label,
                  style: Theme.of(context).textTheme.labelMedium?.copyWith(
                        color: stateColor,
                        fontWeight: FontWeight.w600,
                      ),
                ),
                const SizedBox(height: ClairSpacing.xs),
                Text(
                  '${scan.findingsCount} findings',
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: tokens.textMuted,
                      ),
                ),
              ],
            ),
            const SizedBox(width: ClairSpacing.md),
            Icon(Icons.chevron_right, size: 16, color: tokens.textMuted),
          ],
        ),
      ),
    );
  }
}

class _ScanPipelineOverview extends StatelessWidget {
  const _ScanPipelineOverview();

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;

    const agents = [
      _AgentChip(label: 'Builder', icon: Icons.search_outlined, description: 'Analyzes AST, routes, auth schemes'),
      _AgentChip(label: 'Attacker', icon: Icons.bolt_outlined, description: 'Executes controlled security tests'),
      _AgentChip(label: 'Evaluator', icon: Icons.fact_check_outlined, description: 'Independently validates findings'),
      _AgentChip(label: 'Fixer', icon: Icons.build_outlined, description: 'Generates minimal source patches'),
    ];

    return Container(
      padding: const EdgeInsets.all(ClairSpacing.lg),
      decoration: BoxDecoration(
        color: tokens.surface,
        borderRadius: BorderRadius.circular(ClairRadius.md),
        border: Border.all(color: tokens.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Scan pipeline',
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  color: tokens.textSecondary,
                  letterSpacing: 0.5,
                ),
          ),
          const SizedBox(height: ClairSpacing.md),
          Wrap(
            spacing: ClairSpacing.sm,
            runSpacing: ClairSpacing.sm,
            children: [
              for (int i = 0; i < agents.length; i++) ...[
                agents[i],
                if (i < agents.length - 1)
                  Padding(
                    padding: ClairInsets.y6,
                    child: Icon(Icons.arrow_forward, size: 14, color: tokens.textMuted),
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
    final tokens = context.tokens;

    return Tooltip(
      message: description,
      child: Container(
        padding: const EdgeInsets.symmetric(
          horizontal: ClairSpacing.md,
          vertical: ClairSpacing.sm - 1,
        ),
        decoration: BoxDecoration(
          color: tokens.surfaceRaised,
          borderRadius: BorderRadius.circular(ClairRadius.sm),
          border: Border.all(color: tokens.border),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 14, color: tokens.textSecondary),
            const SizedBox(width: ClairSpacing.xs + 2),
            Text(label, style: Theme.of(context).textTheme.labelLarge),
          ],
        ),
      ),
    );
  }
}
